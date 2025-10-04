import os
import sys
import asyncio
import shutil
import json
import re
import tempfile
import subprocess

try:
    import yaml  # For YAML-safe edits (FPF)
except Exception:
    yaml = None

# Ensure repo root on sys.path so local imports resolve as before
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# prefer local gpt-researcher when available (side-effect)
import run_gptr_local  # noqa: F401
# Ensure monkey patches are applied in the parent process
from api_cost_multiplier.patches import sitecustomize as _patches  # noqa: F401

from functions import pm_utils, MA_runner
from functions import fpf_runner
from functions import config_parser, file_manager, gpt_researcher_client

"""
runner.py

Centralized orchestration for process_markdown pipelines.
This consolidates duplicated logic from generate.py and generate_gptr_only.py.

Primary entrypoints:
- async main(config_path, run_ma=True, run_fpf=True, num_runs=3, keep_temp=False)
- run(config_path, run_ma=True, run_fpf=True, num_runs=3, keep_temp=False)  # sync wrapper
"""

TEMP_BASE = MA_runner.TEMP_BASE
# Hard timeout for GPT-Researcher programmatic runs (seconds)
GPTR_TIMEOUT_SECONDS = 600


async def run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> list:
    try:
        raw = await asyncio.wait_for(
            gpt_researcher_client.run_concurrent_research(
                query_prompt, num_runs=num_runs, report_type=report_type
            ),
            timeout=GPTR_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print(f"  GPT-Researcher ({report_type}) runs timed out after {GPTR_TIMEOUT_SECONDS}s")
        return []
    except Exception as e:
        print(f"  GPT-Researcher ({report_type}) runs failed: {e}")
        return []
    return pm_utils.normalize_report_entries(raw)


def save_generated_reports(input_md_path: str, input_base_dir: str, output_base_dir: str, generated_paths: dict):
    base_name = os.path.splitext(os.path.basename(input_md_path))[0]
    rel_output_path = os.path.relpath(input_md_path, input_base_dir)
    output_dir_for_file = os.path.dirname(os.path.join(output_base_dir, rel_output_path))
    os.makedirs(output_dir_for_file, exist_ok=True)

    saved = []

    def _unpack(item):
        if isinstance(item, (tuple, list)):
            p = item[0]
            model = item[1] if len(item) > 1 else None
        else:
            p = item
            model = None
        return p, model

    def _unique_dest(kind: str, idx: int, model_label: str, ext: str) -> str:
        """
        Build a unique destination filename by appending a 3-char alphanumeric uid.
        Tries a few random uids; falls back to a counter suffix if necessary.
        """
        # Try random UIDs first
        for _ in range(10):
            uid = pm_utils.uid3()
            candidate = os.path.join(
                output_dir_for_file,
                f"{base_name}.{kind}.{idx}.{model_label}.{uid}.{ext}",
            )
            if not os.path.exists(candidate):
                return candidate
        # Extremely unlikely fallback with a counter
        counter = 1
        while True:
            uid = pm_utils.uid3()
            candidate = os.path.join(
                output_dir_for_file,
                f"{base_name}.{kind}.{idx}.{model_label}.{uid}-{counter}.{ext}",
            )
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    # MA
    for idx, item in enumerate(generated_paths.get("ma", []), start=1):
        p, model = _unpack(item)
        model_label = pm_utils.sanitize_model_for_filename(model)
        # Determine destination extension from source path, preserving original artifact types
        ext = "json"
        try:
            if isinstance(p, str):
                lp = p.lower()
                if lp.endswith(".failed.json"):
                    ext = "failed.json"
                else:
                    _, e = os.path.splitext(p)
                    e = (e or "").lower().lstrip(".")
                    # default to json only if we couldn't detect a useful extension
                    if e in ("md", "docx", "pdf", "json", "txt"):
                        ext = e
        except Exception:
            pass
        dest = _unique_dest("ma", idx, model_label, ext)
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save MA report {p} -> {dest}: {e}")

    # GPT Researcher normal
    for idx, item in enumerate(generated_paths.get("gptr", []), start=1):
        p, model = _unpack(item)
        if not model:
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("gptr", idx, model_label, "md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save GPT-R report {p} -> {dest}: {e}")

    # Deep research
    for idx, item in enumerate(generated_paths.get("dr", []), start=1):
        p, model = _unpack(item)
        if not model:
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("dr", idx, model_label, "md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save Deep research report {p} -> {dest}: {e}")

    # FilePromptForge (FPF)
    for idx, item in enumerate(generated_paths.get("fpf", []), start=1):
        p, model = _unpack(item)
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("fpf", idx, model_label, "txt")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save FPF report {p} -> {dest}: {e}")

    return saved


async def process_file(md_file_path: str, config: dict, run_ma: bool = True, run_fpf: bool = True, num_runs_group: dict | None = None, keep_temp: bool = False):
    input_folder = os.path.abspath(config["input_folder"])
    output_folder = os.path.abspath(config["output_folder"])
    instructions_file = os.path.abspath(config["instructions_file"])

    print(f"\nProcessing file: {md_file_path}")
    output_file_path = file_manager.get_output_path(md_file_path, input_folder, output_folder)

    if file_manager.output_exists(output_file_path):
        print(f"  Output exists at {output_file_path}. Skipping.")
        return

    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except Exception as e:
        print(f"  Error reading {md_file_path}: {e}")
        return

    try:
        with open(instructions_file, "r", encoding="utf-8") as f:
            instructions_content = f.read()
    except Exception as e:
        print(f"  Error reading instructions {instructions_file}: {e}")
        return

    query_prompt = gpt_researcher_client.generate_query_prompt(markdown_content, instructions_content)

    pm_utils.ensure_temp_dir(TEMP_BASE)

    generated = {"ma": [], "gptr": [], "dr": [], "fpf": []}

    # Resolve per-group run counts (fallback to 3 if not provided)
    _default_runs = 3
    ma_runs = num_runs_group.get("ma", _default_runs) if num_runs_group else _default_runs
    gptr_runs = num_runs_group.get("gptr", _default_runs) if num_runs_group else _default_runs
    dr_runs = num_runs_group.get("dr", _default_runs) if num_runs_group else _default_runs
    fpf_runs = num_runs_group.get("fpf", _default_runs) if num_runs_group else _default_runs

    # MA (optional)
    if run_ma:
        print(f"  Generating {ma_runs} Multi-Agent reports (MA) ...")
        try:
            ma_results = await MA_runner.run_multi_agent_runs(query_prompt, num_runs=ma_runs)
            print(f"  MA generated {len(ma_results)} report(s).")
            generated["ma"] = ma_results
        except Exception as e:
            print(f"  MA generation failed: {e}")
            generated["ma"] = []

    # GPT-Researcher (always run) - run groups sequentially
    print(f"  Generating {gptr_runs} GPT-Researcher standard reports ...")
    gptr_results = await run_gpt_researcher_runs(query_prompt, num_runs=gptr_runs, report_type="research_report")
    print(f"  GPT-R standard generated: {len(gptr_results)}")

    print(f"  Generating {dr_runs} GPT-Researcher deep research reports ...")
    dr_results = await run_gpt_researcher_runs(query_prompt, num_runs=dr_runs, report_type="deep")
    print(f"  GPT-R deep generated: {len(dr_results)}")

    # FPF (optional)
    if run_fpf:
        print(f"  Generating {fpf_runs} FilePromptForge reports ...")
        # New FPF contract: pass instructions_file and current input markdown path
        fpf_results = await fpf_runner.run_filepromptforge_runs(instructions_file, md_file_path, num_runs=fpf_runs)
    else:
        fpf_results = []

    print(f"  FilePromptForge generated: {len(fpf_results)}")

    generated["gptr"] = gptr_results
    generated["dr"] = dr_results
    generated["fpf"] = fpf_results

    # Simplified plan: ensure a visible artifact on GPTR/DR failure (timeout or error).
    try:
        base_name = os.path.splitext(os.path.basename(md_file_path))[0]
        rel_output_path = os.path.relpath(md_file_path, input_folder)
        output_dir_for_file = os.path.dirname(os.path.join(output_folder, rel_output_path))
        os.makedirs(output_dir_for_file, exist_ok=True)

        # If no GPT-R outputs but runs were requested, emit a single failed artifact
        if gptr_runs > 0 and not gptr_results:
            failed_path = os.path.join(output_dir_for_file, f"{base_name}.gptr.failed.json")
            with open(failed_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "error": "No GPT-Researcher standard outputs produced (timeout or error).",
                    "runs_requested": gptr_runs
                }, fh, ensure_ascii=False, indent=2)

        # If no DR outputs but runs were requested, emit a single failed artifact
        if dr_runs > 0 and not dr_results:
            failed_path = os.path.join(output_dir_for_file, f"{base_name}.dr.failed.json")
            with open(failed_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "error": "No GPT-Researcher deep research outputs produced (timeout or error).",
                    "runs_requested": dr_runs
                }, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Do not block save if failure-artifact writing has an issue
        pass

    print("  Saving generated reports to output folder (mirroring input structure)...")
    saved_files = save_generated_reports(md_file_path, input_folder, output_folder, generated)
    if saved_files:
        print(f"  Saved {len(saved_files)} report(s) to {os.path.dirname(saved_files[0])}")
    else:
        print(f"  No generated files to save for {md_file_path}")

    # Cleanup
    try:
        if os.path.exists(TEMP_BASE) and not keep_temp:
            shutil.rmtree(TEMP_BASE)
    except Exception as e:
        print(f"  Warning: failed to cleanup temp dir {TEMP_BASE}: {e}")


async def process_file_run(md_file_path: str, config: dict, run_entry: dict, iterations: int, keep_temp: bool = False):
    """
    Runs exactly one 'run' (type+model+provider) for the given markdown file, repeating 'iterations' times.
    Mutates tool config files on disk per run (with backup/restore), executes, and saves outputs.
    """
    input_folder = os.path.abspath(config["input_folder"])
    output_folder = os.path.abspath(config["output_folder"])
    instructions_file = os.path.abspath(config["instructions_file"])

    print(f"\n[RUN] type={run_entry.get('type')} provider={run_entry.get('provider')} model={run_entry.get('model')} file={md_file_path}")

    # Read inputs
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except Exception as e:
        print(f"  Error reading {md_file_path}: {e}")
        return

    try:
        with open(instructions_file, "r", encoding="utf-8") as f:
            instructions_content = f.read()
    except Exception as e:
        print(f"  Error reading instructions {instructions_file}: {e}")
        return

    query_prompt = gpt_researcher_client.generate_query_prompt(markdown_content, instructions_content)
    pm_utils.ensure_temp_dir(TEMP_BASE)

    # Prepare result buckets
    generated = {"ma": [], "gptr": [], "dr": [], "fpf": []}

    # Useful paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.dirname(os.path.abspath(os.path.join(current_dir, "config.yaml")))
    gptr_default_py = os.path.join(config_dir, "gpt-researcher", "gpt_researcher", "config", "variables", "default.py")
    fpf_yaml_path = os.path.join(config_dir, "FilePromptForge", "fpf_config.yaml")
    ma_task_json = os.path.join(config_dir, "gpt-researcher", "multi_agents", "task.json")

    rtype = (run_entry.get("type") or "").strip().lower()
    provider = (run_entry.get("provider") or "").strip()
    model = (run_entry.get("model") or "").strip()

    if rtype in ("gptr", "dr"):
        if not provider or not model:
            print(f"  ERROR: gptr/dr run requires provider and model. Got provider='{provider}', model='{model}'.")
            return


        # Backup and patch default.py
        default_src = None
        try:
            with open(gptr_default_py, "r", encoding="utf-8") as fh:
                default_src = fh.read()
        except Exception as e:
            print(f"  ERROR: Cannot read {gptr_default_py}: {e}")
            return

        target = f'{provider}:{model}'
        patched = default_src
        # Replace SMART_LLM and STRATEGIC_LLM values (simple string regexes)
        try:
            patched = re.sub(r'("SMART_LLM"\s*:\s*")[^"]*(")', rf'\1{target}\2', patched)
            patched = re.sub(r'("STRATEGIC_LLM"\s*:\s*")[^"]*(")', rf'\1{target}\2', patched)
            # Optionally align FAST_LLM as well for consistency
            patched = re.sub(r'("FAST_LLM"\s*:\s*")[^"]*(")', rf'\1{target}\2', patched)
            with open(gptr_default_py, "w", encoding="utf-8") as fh:
                fh.write(patched)
        except Exception as e:
            print(f"  ERROR: Failed to patch {gptr_default_py}: {e}")
            return

        # Build prompt file once
        try:
            pm_utils.ensure_temp_dir(TEMP_BASE)
            tmp_prompt = tempfile.NamedTemporaryFile(delete=False, dir=TEMP_BASE, suffix=".txt")
            tmp_prompt_path = tmp_prompt.name
            tmp_prompt.write(query_prompt.encode("utf-8"))
            tmp_prompt.close()
        except Exception as e:
            # Restore immediately on failure
            with open(gptr_default_py, "w", encoding="utf-8") as fh:
                fh.write(default_src)
            print(f"  ERROR: Failed to create prompt temp file: {e}")
            return

        # Determine report type
        report_type = "research_report" if rtype == "gptr" else "deep"

        # Run N iterations via subprocess to ensure the patched file is respected
        for i in range(1, int(iterations) + 1):
            print(f"  Running GPT-Researcher ({report_type}) iteration {i}/{iterations} ...")
            cmd = [
                sys.executable,
                "-u",
                os.path.join(current_dir, "functions", "gptr_subprocess.py"),
                "--prompt-file",
                tmp_prompt_path,
                "--report-type",
                report_type,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if proc.returncode != 0:
                    err = proc.stderr.strip() or proc.stdout.strip()
                    print(f"    ERROR: gpt-researcher subprocess failed (rc={proc.returncode}): {err}")
                else:
                    line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
                    data = {}
                    try:
                        data = json.loads(line) if line else {}
                    except Exception:
                        pass
                    out_path = data.get("path")
                    out_model = data.get("model") or target
                    if out_path and os.path.exists(out_path):
                        if rtype == "gptr":
                            generated["gptr"].append((out_path, out_model))
                        else:
                            generated["dr"].append((out_path, out_model))
                        print(f"    OK: {out_path} ({out_model})")
                    else:
                        print(f"    WARN: No output path parsed from subprocess: {line}")
            except Exception as e:
                print(f"    ERROR: Subprocess execution failed: {e}")

        # Cleanup: restore default.py and temp prompt
        try:
            with open(gptr_default_py, "w", encoding="utf-8") as fh:
                fh.write(default_src)
        except Exception as e:
            print(f"  WARN: failed to restore {gptr_default_py}: {e}")
        try:
            if tmp_prompt_path and os.path.exists(tmp_prompt_path):
                os.remove(tmp_prompt_path)
        except Exception:
            pass

    elif rtype == "fpf":
        if not provider or not model:
            print(f"  ERROR: fpf run requires provider and model. Got provider='{provider}', model='{model}'.")
            return

        # Backup + patch YAML
        fpf_src = None
        try:
            with open(fpf_yaml_path, "r", encoding="utf-8") as fh:
                fpf_src = fh.read()
        except Exception as e:
            print(f"  ERROR: Cannot read {fpf_yaml_path}: {e}")
            return

        try:
            if yaml:
                fy = yaml.safe_load(fpf_src) or {}
                fy["provider"] = provider
                fy["model"] = model
                with open(fpf_yaml_path, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(fy, fh)
            else:
                t = fpf_src
                if re.search(r'^provider:\s*.*$', t, flags=re.MULTILINE):
                    t = re.sub(r'^(provider:\s*).*$',
                               rf'\1{provider}', t, flags=re.MULTILINE)
                else:
                    t += f"\nprovider: {provider}\n"
                if re.search(r'^model:\s*.*$', t, flags=re.MULTILINE):
                    t = re.sub(r'^(model:\s*).*$',
                               rf'\1{model}', t, flags=re.MULTILINE)
                else:
                    t += f"\nmodel: {model}\n"
                with open(fpf_yaml_path, "w", encoding="utf-8") as fh:
                    fh.write(t)
        except Exception as e:
            print(f"  ERROR: Failed to patch {fpf_yaml_path}: {e}")
            return

        try:
            fpf_results = await fpf_runner.run_filepromptforge_runs(instructions_file, md_file_path, num_runs=int(iterations))
            generated["fpf"] = fpf_results
        except Exception as e:
            print(f"  FPF run failed: {e}")

        # Restore file
        try:
            with open(fpf_yaml_path, "w", encoding="utf-8") as fh:
                fh.write(fpf_src)
        except Exception as e:
            print(f"  WARN: failed to restore {fpf_yaml_path}: {e}")

    elif rtype == "ma":
        if not model:
            print("  ERROR: ma run requires model.")
            return

        # Strict file-based MA: generate per-run task.json via ACM and pass to MA_CLI
        try:
            ma_results = await MA_runner.run_multi_agent_runs(
                query_text=query_prompt,
                num_runs=int(iterations),
                model=model
            )
            generated["ma"] = ma_results
        except Exception as e:
            print(f"  MA generation failed: {e}")

    else:
        print(f"  ERROR: Unknown run type '{rtype}'. Skipping.")
        return

    # Save outputs (only the populated bucket will be saved)
    try:
        saved_files = save_generated_reports(md_file_path, input_folder, output_folder, generated)
        if saved_files:
            print(f"  Saved {len(saved_files)} report(s) to {os.path.dirname(saved_files[0])}")
        else:
            print(f"  No generated files to save for {md_file_path}")
    except Exception as e:
        print(f"  ERROR: saving outputs failed: {e}")


async def main(config_path: str, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
    config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(config_path)
    config = config_parser.load_config(config_path)

    if not config:
        print("Failed to load configuration. Exiting.")
        return

    hb_stop = pm_utils.start_heartbeat("process_markdown_runner", interval=3.0)

    def resolve_path(p):
        if not p:
            return None
        if os.path.isabs(p):
            return p
        return os.path.abspath(os.path.join(config_dir, p))

    input_folder = resolve_path(config.get('input_folder'))
    output_folder = resolve_path(config.get('output_folder'))
    instructions_file = resolve_path(config.get('instructions_file'))

    if not all([input_folder, output_folder, instructions_file]):
        print("Missing required configuration (input_folder, output_folder, instructions_file). Exiting.")
        return

    config['input_folder'] = input_folder
    config['output_folder'] = output_folder
    config['instructions_file'] = instructions_file

    # runs-only mode: per-type iterations are deprecated; we use iterations_default later

    markdown_files = file_manager.find_markdown_files(input_folder)
    print(f"Found {len(markdown_files)} markdown files in input folder.")

    if config.get('one_file_only', False) and markdown_files:
        markdown_files = [markdown_files[0]]

    # New runs-only path (removes 'baselines' and 'additional_models')
    runs = config.get("runs") or []
    if isinstance(runs, list) and len(runs) > 0:
        iterations_all = int(config.get("iterations_default", num_runs))
        print(f"Executing {len(runs)} configured run(s); iterations per run: {iterations_all}")

        # Simplified plan: minimal provider:model hygiene
        sanitized_runs = []
        for entry in runs:
            e = dict(entry) if isinstance(entry, dict) else {}
            rtype = (e.get("type") or "").strip().lower()
            provider = (e.get("provider") or "").strip()
            model = (e.get("model") or "").strip()
            # If model accidentally contains provider prefix and provider is empty, split it
            if (rtype in ("gptr", "dr")) and (not provider) and (":" in model):
                parts = model.split(":", 1)
                e["provider"] = parts[0].strip()
                e["model"] = parts[1].strip()
            sanitized_runs.append(e)
        runs = sanitized_runs

        for md in markdown_files:
            for idx, entry in enumerate(runs):
                print(f"\n--- Executing run #{idx}: {entry} ---")
                await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp)

        # Stop heartbeat and finish early (skip legacy additional_models)
        try:
            hb_stop.set()
        except Exception:
            pass
        print("\nprocess_markdown runner finished.")
        return

    # No legacy path: require explicit 'runs' configuration
    print("ERROR: config.yaml must define a 'runs' array (baselines/additional_models are no longer supported).")
    try:
        hb_stop.set()
    except Exception:
        pass
    print("\nprocess_markdown runner finished.")
    return


def run(config_path: str, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
    asyncio.run(main(config_path, run_ma=run_ma, run_fpf=run_fpf, num_runs=num_runs, keep_temp=keep_temp))


if __name__ == "__main__":
    # Use local package config.yaml by default
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(current_dir, "config.yaml")
    run(cfg)
