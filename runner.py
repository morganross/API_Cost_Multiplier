import os
import sys
import asyncio
import shutil
import json
import re

# Ensure repo root on sys.path so local imports resolve as before
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# prefer local gpt-researcher when available (side-effect)
import run_gptr_local  # noqa: F401

from functions import pm_utils, MA_runner
from functions import fpf_runner
from EXAMPLE_fucntions import config_parser, file_manager, gpt_researcher_client

"""
runner.py

Centralized orchestration for process_markdown pipelines.
This consolidates duplicated logic from generate.py and generate_gptr_only.py.

Primary entrypoints:
- async main(config_path, run_ma=True, run_fpf=True, num_runs=3, keep_temp=False)
- run(config_path, run_ma=True, run_fpf=True, num_runs=3, keep_temp=False)  # sync wrapper
"""

TEMP_BASE = MA_runner.TEMP_BASE


async def run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> list:
    try:
        raw = await gpt_researcher_client.run_concurrent_research(
            query_prompt, num_runs=num_runs, report_type=report_type
        )
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

    # MA
    for idx, item in enumerate(generated_paths.get("ma", []), start=1):
        p, model = _unpack(item)
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = os.path.join(output_dir_for_file, f"{base_name}.ma.{idx}.{model_label}.md")
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
        dest = os.path.join(output_dir_for_file, f"{base_name}.gptr.{idx}.{model_label}.md")
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
        dest = os.path.join(output_dir_for_file, f"{base_name}.dr.{idx}.{model_label}.md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save Deep research report {p} -> {dest}: {e}")

    # FilePromptForge (FPF)
    for idx, item in enumerate(generated_paths.get("fpf", []), start=1):
        p, model = _unpack(item)
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = os.path.join(output_dir_for_file, f"{base_name}.fpf.{idx}.{model_label}.md")
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
        fpf_results = await fpf_runner.run_filepromptforge_runs(query_prompt, num_runs=fpf_runs)
    else:
        fpf_results = []

    print(f"  FilePromptForge generated: {len(fpf_results)}")

    generated["gptr"] = gptr_results
    generated["dr"] = dr_results
    generated["fpf"] = fpf_results

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

    # Determine iteration counts from config (supports per-group overrides)
    iterations_cfg = config.get("iterations") or {}
    default_runs = config.get("iterations_default", num_runs)
    try:
        ma_runs = int(iterations_cfg.get("ma", default_runs))
        gptr_runs = int(iterations_cfg.get("gptr", default_runs))
        dr_runs = int(iterations_cfg.get("dr", default_runs))
        fpf_runs = int(iterations_cfg.get("fpf", default_runs))
    except Exception:
        # Fallback to provided numeric default if parsing fails
        ma_runs = gptr_runs = dr_runs = fpf_runs = int(default_runs)

    num_runs_group = {"ma": ma_runs, "gptr": gptr_runs, "dr": dr_runs, "fpf": fpf_runs}

    markdown_files = file_manager.find_markdown_files(input_folder)
    print(f"Found {len(markdown_files)} markdown files in input folder.")

    if config.get('one_file_only', False) and markdown_files:
        markdown_files = [markdown_files[0]]

    # Run baseline pass for all files
    for md in markdown_files:
        await process_file(md, config, run_ma=run_ma, run_fpf=run_fpf, num_runs_group=num_runs_group, keep_temp=keep_temp)

    # After baseline, process any additional_models listed in config.yaml
    additional = config.get("additional_models", [])
    state_path = os.path.join(config_dir, "additional_runs_state.json")
    completed = set()
    try:
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as sf:
                completed = set(json.load(sf).get("completed", []))
    except Exception:
        completed = set()

    if additional and isinstance(additional, list):
        print(f"Found {len(additional)} additional model run(s) configured. Executing sequentially...")
        for idx, entry in enumerate(additional):
            # Skip if already completed
            if str(idx) in completed:
                print(f"  Skipping already-completed additional run #{idx}")
                continue
            rtype = entry.get("type")
            provider = entry.get("provider")
            model = entry.get("model")
            iterations = int(entry.get("iterations", 1) or 1)

            print(f"  Starting additional run #{idx}: type={rtype}, provider={provider}, model={model}, iterations={iterations}")

            # Backup and write target configs depending on type
            backups = []
            try:
                # GPTR/DR: write SMART_LLM and STRATEGIC_LLM in default.py
                if rtype in ("gptr", "dr", "all"):
                    default_py = os.path.join(config_dir, "gpt-researcher", "gpt_researcher", "config", "variables", "default.py")
                    if os.path.exists(default_py):
                        bpath = default_py + ".pm.bak"
                        shutil.copy2(default_py, bpath)
                        backups.append((default_py, bpath))
                        # naive replace: look for SMART_LLM and STRATEGIC_LLM assignments and replace rhs
                        with open(default_py, "r", encoding="utf-8") as fh:
                            t = fh.read()
                        if model:
                            value = f'"{provider}:{model}"' if provider else f'"{model}"'
                            t = re.sub(r'(SMART_LLM\s*:\s*")[^"]*(")', rf'\1{provider}:{model}\2', t)
                            t = re.sub(r'(SMART_LLM"\s*:\s*)"[^"]*(")', rf'\1{provider}:{model}\2', t)
                            # fallback patterns
                            t = re.sub(r'(SMART_LLM"\s*:\s*)"[^"]*(")', rf'\1{provider}:{model}\2', t)
                            t = re.sub(r'("SMART_LLM"\s*:\s*)"[^"]*(")', rf'\1{provider}:{model}\2', t)
                            # Simple assignment style detection (older format)
                            t = re.sub(r'(SMART_LLM"\s*:\s*)"[^"]*(")', rf'\1{provider}:{model}\2', t)
                            with open(default_py, "w", encoding="utf-8") as fh:
                                fh.write(t)

                # FPF: update FilePromptForge/default_config.yaml
                if rtype in ("fpf", "all"):
                    fpf_yaml = os.path.join(config_dir, "FilePromptForge", "default_config.yaml")
                    if os.path.exists(fpf_yaml):
                        bpath = fpf_yaml + ".pm.bak"
                        shutil.copy2(fpf_yaml, bpath)
                        backups.append((fpf_yaml, bpath))
                        # read YAML-ish file, do simple replacements for provider and provider.model
                        try:
                            import yaml
                            with open(fpf_yaml, "r", encoding="utf-8") as fh:
                                fy = yaml.safe_load(fh) or {}
                            if provider:
                                fy["provider"] = provider
                            if provider and model:
                                if provider not in fy:
                                    fy[provider] = {}
                                fy[provider]["model"] = model
                            with open(fpf_yaml, "w", encoding="utf-8") as fh:
                                yaml.safe_dump(fy, fh)
                        except Exception:
                            # fallback to simple text replacement
                            with open(fpf_yaml, "r", encoding="utf-8") as fh:
                                t = fh.read()
                            if provider:
                                t = re.sub(r'^(provider:\s*).*$', rf'\1{provider}', t, flags=re.MULTILINE)
                            if provider and model:
                                pattern = rf'^({provider}:\s*\n(?:\s+.*\n)*)'
                                if re.search(pattern, t, flags=re.MULTILINE):
                                    t = re.sub(rf'({provider}:\s*\n(?:\s+.*\n)*)', lambda m: re.sub(r'model:\s*.*', f'model: {model}', m.group(0)), t, flags=re.MULTILINE)
                                else:
                                    t += f"\n{provider}:\n  model: {model}\n"
                            with open(fpf_yaml, "w", encoding="utf-8") as fh:
                                fh.write(t)

                # MA: write model to multi_agents/task.json
                if rtype in ("ma", "all"):
                    task_json = os.path.join(config_dir, "gpt-researcher", "multi_agents", "task.json")
                    if os.path.exists(task_json) and model:
                        bpath = task_json + ".pm.bak"
                        shutil.copy2(task_json, bpath)
                        backups.append((task_json, bpath))
                        with open(task_json, "r", encoding="utf-8") as fh:
                            j = json.load(fh)
                        j["model"] = model
                        with open(task_json, "w", encoding="utf-8") as fh:
                            json.dump(j, fh, indent=2)

                # Build per-pass num_runs_group: only the target type(s) get 'iterations', others 0
                if rtype == "all":
                    per_pass = {"ma": iterations, "gptr": iterations, "dr": iterations, "fpf": iterations}
                else:
                    per_pass = {"ma": 0, "gptr": 0, "dr": 0, "fpf": 0}
                    if rtype in per_pass:
                        per_pass[rtype] = iterations

                # Run pipeline once using modified configs
                print(f"    Running pipeline for additional run #{idx} with counts {per_pass} ...")
                for md in markdown_files:
                    await process_file(md, config, run_ma=bool(per_pass.get("ma", 0)), run_fpf=bool(per_pass.get("fpf", 0)), num_runs_group=per_pass, keep_temp=keep_temp)

                # Mark completed
                completed.add(str(idx))
                try:
                    with open(state_path, "w", encoding="utf-8") as sf:
                        json.dump({"completed": list(completed)}, sf)
                except Exception:
                    pass

            except Exception as e:
                print(f"  ERROR during additional run #{idx}: {e}")
                # restore backups on error
                for orig, bkp in backups:
                    try:
                        shutil.copy2(bkp, orig)
                    except Exception:
                        pass
                print("  Restored backups after failure. Aborting additional runs.")
                break
            finally:
                # Restore backups to leave configs as they were
                for orig, bkp in backups:
                    try:
                        shutil.copy2(bkp, orig)
                    except Exception:
                        pass

    # Stop heartbeat
    try:
        hb_stop.set()
    except Exception:
        pass

    print("\nprocess_markdown runner finished.")


def run(config_path: str, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
    asyncio.run(main(config_path, run_ma=run_ma, run_fpf=run_fpf, num_runs=num_runs, keep_temp=keep_temp))


if __name__ == "__main__":
    # Use local package config.yaml by default
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(current_dir, "config.yaml")
    run(cfg)
