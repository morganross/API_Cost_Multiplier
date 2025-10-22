import os
import sys
import asyncio
import shutil
import json
import re
import tempfile
import subprocess
from pathlib import Path
import logging
import logging.handlers
import time
import threading

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
from functions import logging_levels

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

# Dedicated file logger for subprocess output (initialized in main)
SUBPROC_LOGGER: logging.Logger | None = None


def _resolve_gptr_concurrency(cfg: dict) -> tuple[bool, int, float]:
    """
    Resolve GPT‑Researcher concurrency settings from ACM config.yaml with optional policy overlay.

    Returns:
      (enabled, max_concurrent_reports, launch_delay_seconds)
    """
    try:
        # Local defaults
        local_enabled = False
        local_max = 1
        local_delay = 0.0

        # Local config path: concurrency.gpt_researcher.{enabled,max_concurrent_reports,launch_delay_seconds}
        conc = (cfg.get("concurrency") or {})
        gptr_local = (conc.get("gpt_researcher") or {})
        if isinstance(gptr_local, dict):
            local_enabled = bool(gptr_local.get("enabled", local_enabled))
            try:
                local_max = int(gptr_local.get("max_concurrent_reports", local_max))
            except Exception:
                local_max = 1
            try:
                local_delay = float(gptr_local.get("launch_delay_seconds", local_delay))
            except Exception:
                local_delay = 0.0

        # Policy overlay path: policies.concurrency.gpt_researcher with enforce flag
        policies = (cfg.get("policies") or {})
        pol_conc = (policies.get("concurrency") or {})
        gptr_pol = (pol_conc.get("gpt_researcher") or {})
        enforce = bool(gptr_pol.get("enforce", False))

        # Effective values
        eff_max = local_max
        eff_delay = local_delay

        if enforce:
            try:
                cap = gptr_pol.get("max_concurrent_reports_cap", None)
                if cap is not None:
                    cap = int(cap)
                    eff_max = min(local_max, cap) if local_enabled else min(1, cap)
            except Exception:
                pass
            try:
                min_delay = gptr_pol.get("launch_delay_seconds_min", None)
                if min_delay is not None:
                    min_delay = float(min_delay)
                    eff_delay = max(local_delay, min_delay)
            except Exception:
                pass

        # Sanity clamps
        eff_max = max(1, int(eff_max))
        try:
            eff_delay = float(eff_delay)
            if eff_delay < 0.0:
                eff_delay = 0.0
        except Exception:
            eff_delay = 0.0

        return bool(local_enabled), int(eff_max), float(eff_delay)
    except Exception:
        # Safe fallback: disabled/serial
        return False, 1, 0.0


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
        fpf_results = await fpf_runner.run_filepromptforge_runs(
            instructions_file,
            md_file_path,
            num_runs=fpf_runs,
            options={"json": False}
        )
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


async def process_file_run(md_file_path: str, config: dict, run_entry: dict, iterations: int, keep_temp: bool = False, forward_subprocess_output: bool = True):
    """
    Runs exactly one 'run' (type+model+provider) for the given markdown file, repeating 'iterations' times.
    Mutates tool config files on disk per run (with backup/restore), executes, and saves outputs.
    """
    input_folder = os.path.abspath(config["input_folder"])
    output_folder = os.path.abspath(config["output_folder"])
    instructions_file = os.path.abspath(config["instructions_file"])

    print(f"\n[RUN] type={run_entry.get('type')} provider={run_entry.get('provider')} model={run_entry.get('model')} file={md_file_path}")
    # Emit standardized RUN_START event via ACM logger
    try:
        logging.getLogger("acm").info(
            "[RUN_START] type=%s provider=%s model=%s file=%s",
            run_entry.get('type'), run_entry.get('provider'), run_entry.get('model'), md_file_path
        )
    except Exception:
        pass

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

        # Select model/provider for this subprocess without editing shared files
        target = f'{provider}:{model}'

        # Build prompt file once
        try:
            pm_utils.ensure_temp_dir(TEMP_BASE)
            tmp_prompt = tempfile.NamedTemporaryFile(delete=False, dir=TEMP_BASE, suffix=".txt")
            tmp_prompt_path = tmp_prompt.name
            tmp_prompt.write(query_prompt.encode("utf-8"))
            tmp_prompt.close()
        except Exception as e:
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
                # Ensure child Python process uses UTF-8 for stdio (Windows cp1252 default causes decode/encode errors).
                env = os.environ.copy()
                env.setdefault("PYTHONIOENCODING", "utf-8")
                env.setdefault("PYTHONUTF8", "1")
                # Inject provider/model for this subprocess only (no shared file edits)
                env["SMART_LLM"] = target
                env["STRATEGIC_LLM"] = target
                env["FAST_LLM"] = target
                # Spawn subprocess and stream stdout/stderr so progress is visible in parent console.
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                out_lines = []

                def _stream(pipe, prefix):
                    try:
                        for raw_line in iter(pipe.readline, ''):
                            if raw_line == '':
                                break
                            line = raw_line.rstrip("\n")
                            # Always write child output to file logger (if configured)
                            try:
                                if SUBPROC_LOGGER is not None:
                                    if prefix == "ERR":
                                        SUBPROC_LOGGER.warning("[%s] %s", prefix, line)
                                    else:
                                        SUBPROC_LOGGER.info("[%s] %s", prefix, line)
                            except Exception:
                                # Do not let logging failures disrupt the run
                                pass

                            # Respect forwarding toggle to console/logger
                            if forward_subprocess_output:
                                try:
                                    acm_logger = logging.getLogger("acm")
                                    if prefix == "ERR":
                                        acm_logger.warning("[%s] %s", prefix, line)
                                    else:
                                        acm_logger.info("[%s] %s", prefix, line)
                                except Exception:
                                    print(f"    [{prefix}] {line}")
                                    sys.stdout.flush()
                            # Regardless of forwarding, preserve logic that needs OUT lines for JSON parsing
                            if prefix == "OUT":
                                out_lines.append(line)
                    finally:
                        try:
                            pipe.close()
                        except Exception:
                            pass

                import threading as _threading
                t_out = _threading.Thread(target=_stream, args=(proc.stdout, "OUT"), daemon=True)
                t_err = _threading.Thread(target=_stream, args=(proc.stderr, "ERR"), daemon=True)
                t_out.start()
                t_err.start()

                proc.wait()
                t_out.join(timeout=1)
                t_err.join(timeout=1)

                if proc.returncode != 0:
                    print(f"    ERROR: gpt-researcher subprocess failed (rc={proc.returncode})")
                else:
                    # Try to parse the last JSON line emitted by the child (if any).
                    last_line = ""
                    for l in reversed(out_lines):
                        s = l.strip()
                        if s.startswith("{") and s.endswith("}"):
                            last_line = s
                            break
                    if not last_line and out_lines:
                        last_line = out_lines[-1]
                    data = {}
                    try:
                        data = json.loads(last_line) if last_line else {}
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
                        print(f"    WARN: No output path parsed from subprocess: {last_line}")
            except Exception as e:
                print(f"    ERROR: Subprocess execution failed: {e}")

        # Cleanup: remove temp prompt
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
            try:
                logging.getLogger("acm").info("[FILES_WRITTEN] count=%s paths=%s", len(saved_files), saved_files)
            except Exception:
                pass
        else:
            print(f"  No generated files to save for {md_file_path}")
            try:
                logging.getLogger("acm").info("[FILES_WRITTEN] count=0 paths=[]")
            except Exception:
                pass
    except Exception as e:
        print(f"  ERROR: saving outputs failed: {e}")


async def process_file_fpf_batch(md_file_path: str, config: dict, fpf_entries: list[dict], iterations: int, keep_temp: bool = False):
    """
    Aggregate all FPF runs for a single markdown file and execute them in one batch via stdin -> FPF.
    """
    input_folder = os.path.abspath(config["input_folder"])
    output_folder = os.path.abspath(config["output_folder"])
    instructions_file = os.path.abspath(config["instructions_file"])

    # Build stdin JSON array for FPF
    batch_runs = []
    run_counter = 0
    for idx, entry in enumerate(fpf_entries):
        provider = (entry.get("provider") or "").strip()
        model = (entry.get("model") or "").strip()
        if not provider or not model:
            print(f"  ERROR: fpf run requires provider and model. Got provider='{provider}', model='{model}'. Skipping.")
            continue
        for rep in range(1, int(iterations) + 1):
            run_counter += 1
            run_id = f"fpf-{idx+1}-{rep}"
            batch_runs.append({
                "id": run_id,
                "provider": provider,
                "model": model,
                "file_a": instructions_file,
                "file_b": md_file_path,
                "out": os.path.join(output_folder, f"{Path(md_file_path).stem}.{model}.{run_id}.fpf.response.txt")
            })

    if not batch_runs:
        print("  No valid FPF runs to execute in batch.")
        return

    try:
        fpf_results = await fpf_runner.run_filepromptforge_batch(batch_runs, options={"json": False})
    except Exception as e:
        print(f"  FPF batch failed: {e}")
        fpf_results = []

    # Save only FPF outputs for this file
    generated = {"ma": [], "gptr": [], "dr": [], "fpf": fpf_results}
    print("  Saving FPF batch reports to output folder (mirroring input structure)...")
    try:
        saved_files = save_generated_reports(md_file_path, input_folder, output_folder, generated)
        if saved_files:
            print(f"  Saved {len(saved_files)} FPF report(s) to {os.path.dirname(saved_files[0])}")
        else:
            print(f"  No FPF outputs to save for {md_file_path}")
    except Exception as e:
        print(f"  ERROR: saving FPF batch outputs failed: {e}")

    # Cleanup temp dir (consistent with other paths)
    try:
        if os.path.exists(TEMP_BASE) and not keep_temp:
            shutil.rmtree(TEMP_BASE)
    except Exception as e:
        print(f"  Warning: failed to cleanup temp dir {TEMP_BASE}: {e}")


async def main(config_path: str, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
    config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(config_path)
    config = config_parser.load_config(config_path)

    if not config:
        print("Failed to load configuration. Exiting.")
        return

    # Resolve log levels and build ACM logger (no basicConfig; named logger only)
    console_name, file_name, console_level, file_level = logging_levels.resolve_levels(config)
    acm_logger = logging_levels.build_logger("acm", console_level, file_level)
    # Map normalized console level to GPT‑R 'research' logger level
    research_level = (
        logging.WARNING if str(console_name).lower() == "low"
        else (logging.INFO if str(console_name).lower() == "medium" else logging.DEBUG)
    )
    try:
        logging.getLogger("research").setLevel(research_level)
    except Exception:
        # If the logger doesn't exist yet, GPT‑R will create it; we keep ACM logger configured regardless.
        pass
    logging_levels.emit_health(acm_logger, console_name, file_name, console_level, file_level)

    # Configure dedicated file-only logger for subprocess output
    try:
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        subproc_log_path = os.path.join(logs_dir, "acm_subprocess.log")
        subproc_handler = logging.handlers.RotatingFileHandler(
            subproc_log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        subproc_formatter = logging.Formatter("%(asctime)s - acm.subproc - %(levelname)s - %(message)s")
        subproc_handler.setFormatter(subproc_formatter)
        subproc_logger = logging.getLogger("acm.subproc")
        subproc_logger.setLevel(logging.INFO)
        # Avoid duplicate handlers on repeated runs
        if not any(isinstance(h, logging.handlers.RotatingFileHandler) and getattr(h, "baseFilename", None) == getattr(subproc_handler, "baseFilename", None) for h in subproc_logger.handlers):
            subproc_logger.addHandler(subproc_handler)
        # Do not propagate to root/ACM logger to keep console quiet; file-only
        subproc_logger.propagate = False
        # Expose globally for _stream
        global SUBPROC_LOGGER
        SUBPROC_LOGGER = subproc_logger
    except Exception:
        # If file logger setup fails, continue without file-only capture
        SUBPROC_LOGGER = None

    # Resolve forward_subprocess_output flag (env > config > default)
    def _coerce_bool(val, default=True):
        if val is None:
            return default
        s = str(val).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
        return default

    cfg_log = ((config or {}).get("acm") or {}).get("log") or {}
    forward_subproc_default = True
    forward_subproc_cfg = cfg_log.get("forward_subprocess_output", forward_subproc_default)
    forward_subproc_env = os.environ.get("ACM_FORWARD_SUBPROC", None)
    forward_subprocess_output = _coerce_bool(forward_subproc_env, _coerce_bool(forward_subproc_cfg, forward_subproc_default))

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

    # Heartbeat: batch + active runs with mm:ss every 30 seconds
    batch_start_ts = time.time()
    active_runs: dict[str, float] = {}
    active_lock = threading.Lock()
    hb_stop = threading.Event()

    def _format_mmss(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def _snapshot_runs() -> list[str]:
        with active_lock:
            items = list(active_runs.items())
        now = time.time()
        return [f"{rid}={_format_mmss(now - ts)}" for rid, ts in items]

    def _hb():
        while not hb_stop.is_set():
            now = time.time()
            batch_elapsed = _format_mmss(now - batch_start_ts)
            runs_list = _snapshot_runs()
            msg = f"[HEARTBEAT ACM] batch={batch_elapsed} active={len(runs_list)} runs=[{', '.join(runs_list)}]"
            print(msg, flush=True)
            hb_stop.wait(30.0)

    t_hb = threading.Thread(target=_hb, daemon=True)
    t_hb.start()

    def _register_run(run_id: str):
        with active_lock:
            active_runs[run_id] = time.time()

    def _deregister_run(run_id: str):
        with active_lock:
            active_runs.pop(run_id, None)

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
            # Split FPF vs non-FPF runs. Execute non-FPF individually as before; batch all FPF at once.
            fpf_entries = []
            other_entries = []
            for idx, entry in enumerate(runs):
                rtype = (entry.get("type") or "").strip().lower()
                if rtype == "fpf":
                    fpf_entries.append(entry)
                else:
                    other_entries.append((idx, entry))

            # Split other entries into MA vs GPT‑R (gptr/dr)
            ma_entries: list[tuple[int, dict]] = []
            gptr_dr_entries: list[tuple[int, dict]] = []
            for idx, entry in other_entries:
                rtype = (entry.get("type") or "").strip().lower()
                if rtype == "ma":
                    ma_entries.append((idx, entry))
                else:
                    # Only gptr/dr should be in this bucket; unknowns still run sequentially
                    gptr_dr_entries.append((idx, entry))

            # Split GPT‑R into standard vs deep research for ordered execution
            gptr_entries: list[tuple[int, dict]] = []
            dr_entries: list[tuple[int, dict]] = []
            for idx, entry in gptr_dr_entries:
                rtype2 = (entry.get("type") or "").strip().lower()
                if rtype2 == "dr":
                    dr_entries.append((idx, entry))
                else:
                    gptr_entries.append((idx, entry))

            # Execute all FPF runs in a single batch invocation (FIRST)
            if fpf_entries:
                print(f"\n--- Executing FPF batch ({len(fpf_entries)} run templates x {iterations_all} iteration(s)) ---")
                batch_id = f"fpf-batch-{Path(md).stem}"
                _register_run(batch_id)
                try:
                    await process_file_fpf_batch(md, config, fpf_entries, iterations_all, keep_temp=keep_temp)
                finally:
                    _deregister_run(batch_id)

            # Next: Run GPT‑R (standard) with report-level concurrency and launch pacing
            enabled, max_conc, launch_delay = _resolve_gptr_concurrency(config)
            if not enabled:
                # Fall back to sequential behavior
                for idx, entry in gptr_entries:
                    print(f"\n--- Executing GPT‑R (standard) run #{idx} (sequential): {entry} ---")
                    run_id = f"gptr-std-{idx}"
                    _register_run(run_id)
                    try:
                        await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                    finally:
                        _deregister_run(run_id)
            else:
                print(f"\n[GPT‑R Concurrency] (standard) enabled=True max_concurrent_reports={max_conc} launch_delay_seconds={launch_delay}")
                sem = asyncio.Semaphore(max_conc)
                tasks: list[asyncio.Task] = []

                async def _limited_std(idx0: int, e0: dict):
                    async with sem:
                        print(f"    [GPT‑R queue std] scheduling run #{idx0}: {e0}")
                        run_id0 = f"gptr-std-{idx0}"
                        _register_run(run_id0)
                        try:
                            await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                        finally:
                            _deregister_run(run_id0)

                for j, (idx, entry) in enumerate(gptr_entries):
                    tasks.append(asyncio.create_task(_limited_std(idx, entry)))
                    if j < len(gptr_entries) - 1 and launch_delay > 0:
                        await asyncio.sleep(launch_delay)

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=False)

            # Then: Run GPT‑R Deep Research with the same concurrency controls
            if not enabled:
                for idx, entry in dr_entries:
                    print(f"\n--- Executing GPT‑R (deep) run #{idx} (sequential): {entry} ---")
                    run_id = f"gptr-deep-{idx}"
                    _register_run(run_id)
                    try:
                        await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                    finally:
                        _deregister_run(run_id)
            else:
                print(f"\n[GPT‑R Concurrency] (deep) enabled=True max_concurrent_reports={max_conc} launch_delay_seconds={launch_delay}")
                sem_dr = asyncio.Semaphore(max_conc)
                tasks_dr: list[asyncio.Task] = []

                async def _limited_dr(idx0: int, e0: dict):
                    async with sem_dr:
                        print(f"    [GPT‑R queue deep] scheduling run #{idx0}: {e0}")
                        run_id0 = f"gptr-deep-{idx0}"
                        _register_run(run_id0)
                        try:
                            await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                        finally:
                            _deregister_run(run_id0)

                for j, (idx, entry) in enumerate(dr_entries):
                    tasks_dr.append(asyncio.create_task(_limited_dr(idx, entry)))
                    if j < len(dr_entries) - 1 and launch_delay > 0:
                        await asyncio.sleep(launch_delay)

                if tasks_dr:
                    await asyncio.gather(*tasks_dr, return_exceptions=False)

            # Finally: Run MA entries sequentially
            for idx, entry in ma_entries:
                print(f"\n--- Executing MA run #{idx}: {entry} ---")
                run_id = f"ma-{idx}"
                _register_run(run_id)
                try:
                    await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                finally:
                    _deregister_run(run_id)

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
