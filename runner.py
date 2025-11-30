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
from functions.fpf_inflight import FpfInflightTracker

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
    Resolve GPTâ€‘Researcher concurrency settings from ACM config.yaml with optional policy overlay.

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


def _resolve_ma_concurrency(cfg: dict) -> tuple[bool, int, float]:
    """
    Resolve Multi-Agent concurrency settings from ACM config.yaml.
    
    Returns:
      (enabled, max_concurrent_runs, launch_delay_seconds)
    """
    try:
        # Local defaults
        local_enabled = False
        local_max = 1
        local_delay = 0.0

        # Local config path: concurrency.multi_agent.{enabled,max_concurrent_runs,launch_delay_seconds}
        conc = (cfg.get("concurrency") or {})
        ma_local = (conc.get("multi_agent") or {})
        if isinstance(ma_local, dict):
            local_enabled = bool(ma_local.get("enabled", local_enabled))
            try:
                local_max = int(ma_local.get("max_concurrent_runs", local_max))
            except Exception:
                local_max = 1
            try:
                local_delay = float(ma_local.get("launch_delay_seconds", local_delay))
            except Exception:
                local_delay = 0.0

        # Sanity clamps
        eff_max = max(1, int(local_max))
        try:
            eff_delay = float(local_delay)
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
    seen_src = set()

    # Honor one_file_only policy for MA artifacts (align with output_manager)
    one_file_only = False
    try:
        # Prefer repo-local config.yaml
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cfg_path = os.path.join(repo_root, "config.yaml")
        if os.path.isfile(cfg_path) and (yaml is not None):
            with open(cfg_path, "r", encoding="utf-8") as _fh:
                _cfg = yaml.safe_load(_fh) or {}
                one_file_only = bool(_cfg.get("one_file_only", False))
    except Exception:
        # Best-effort: default to False if config cannot be read
        pass

    # Prepare MA list with optional reduction to a single preferred artifact
    ma_items = list(generated_paths.get("ma", [])) if isinstance(generated_paths.get("ma", []), list) else []
    if ma_items: # Always apply this logic for MA outputs
        preferred_exts = [".md", ".docx", ".pdf"]
        _selected = None
        for _ext in preferred_exts:
            for _it in ma_items:
                _p = _it[0] if isinstance(_it, (tuple, list)) and _it else _it
                if isinstance(_p, str) and os.path.splitext(_p)[1].lower() == _ext:
                    _selected = [_it]
                    break
            if _selected:
                break
        ma_items = _selected or [ma_items[0]] # If no preferred ext found, default to the first item.

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
                f"{base_name}.{kind}.{idx}.{model_label}.{uid}-{counter}.ext",
            )
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    # MA
    # This loop will now only run once if ma_items has been reduced to a single item
    for idx, item in enumerate(ma_items, start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
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
            # The original code had an `except Exception: pass` here, but it was misplaced.
            # The `ext = "json"` line should be outside the try block if it's a default.
            # The try block should only cover the logic that might raise an exception.
            # I'm moving the `ext = "json"` outside the try block and keeping the try block for the splitext logic.
        except Exception:
            pass # Keep the pass for the splitext logic
        dest = _unique_dest("ma", idx, model_label, ext)
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            print(f"    Failed to save MA report {p} -> {dest}: {e}")

    # GPT Researcher normal
    for idx, item in enumerate(generated_paths.get("gptr", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        if not model:
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("gptr", idx, model_label, "md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            print(f"    Failed to save GPT-R report {p} -> {dest}: {e}")

    # Deep research
    for idx, item in enumerate(generated_paths.get("dr", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        if not model:
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("dr", idx, model_label, "md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            print(f"    Failed to save Deep research report {p} -> {dest}: {e}")

    # FilePromptForge (FPF)
    # FPF files now created with standardized names from batch runner.
    # Just verify they exist and are in the correct output directory.
    for idx, item in enumerate(generated_paths.get("fpf", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        try:
            # Files should already be in output directory with standardized names
            # If file is in a different directory (e.g., temp), move it to output
            if os.path.dirname(p) != output_dir_for_file:
                # Generate destination with same basename but in correct directory
                dest = os.path.join(output_dir_for_file, os.path.basename(p))
                # Use move instead of copy to avoid duplicates
                if os.path.exists(dest):
                    # If destination exists, remove source to avoid duplicate
                    os.remove(p)
                    final_dest = dest
                else:
                    shutil.move(p, dest)
                    final_dest = dest
            else:
                # Already in correct location
                final_dest = p
            saved.append(final_dest)
            seen_src.add(p)
        except Exception as e:
            print(f"    Failed to save FPF report {p}: {e}")

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

    # NOTE: Evaluation trigger removed - now centralized in main() after ALL processing completes
    # This prevents partial evaluations that waste API costs on incomplete file sets

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
            try:
                tmp_prompt.flush()
                os.fsync(tmp_prompt.fileno())
            except Exception:
                # Best-effort: ensure prompt contents are persisted before child reads
                pass
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
                if SUBPROC_LOGGER:
                    SUBPROC_LOGGER.info(f"[GPTR_START] pid={proc.pid} type={report_type} model={target}")

                out_lines = []
                missing_prompt_err = False
                had_retry = False

                def _stream(pipe, prefix):
                    nonlocal missing_prompt_err
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

                            # Detect prompt-file missing error for single auto-retry
                            if prefix == "ERR" and "Prompt file not found:" in line:
                                missing_prompt_err = True

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

                # Do not block the asyncio event loop while waiting for the child to exit
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, proc.wait)
                t_out.join(timeout=1)
                t_err.join(timeout=1)

                if proc.returncode != 0:
                    print(f"    ERROR: gpt-researcher subprocess failed (rc={proc.returncode})")
                    # One-time auto-retry if the prompt file was reported missing
                    if missing_prompt_err and not had_retry:
                        try:
                            # Recreate prompt file contents defensively
                            with open(tmp_prompt_path, "w", encoding="utf-8") as _fh:
                                _fh.write(query_prompt)
                                try:
                                    _fh.flush()
                                    os.fsync(_fh.fileno())
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            if SUBPROC_LOGGER:
                                SUBPROC_LOGGER.info("[GPTR_RETRY] reason=missing_prompt_file")
                            proc2 = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL,
                                env=env,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                            )
                            out2, err2 = proc2.communicate(timeout=GPTR_TIMEOUT_SECONDS)
                            had_retry = True
                            if proc2.returncode == 0:
                                # Parse last JSON line from stdout
                                last_line2 = ""
                                for l2 in reversed(out2.splitlines() if out2 else []):
                                    s2 = l2.strip()
                                    if s2.startswith("{") and s2.endswith("}"):
                                        last_line2 = s2
                                        break
                                if not last_line2 and out2:
                                    last_line2 = out2.splitlines()[-1]
                                data2 = {}
                                try:
                                    data2 = json.loads(last_line2) if last_line2 else {}
                                except Exception:
                                    data2 = {}
                                out_path2 = data2.get("path")
                                out_model2 = data2.get("model") or target
                                if out_path2 and os.path.exists(out_path2):
                                    if rtype == "gptr":
                                        generated["gptr"].append((out_path2, out_model2))
                                    else:
                                        generated["dr"].append((out_path2, out_model2))
                                    print(f"    OK (retry): {out_path2} ({out_model2})")
                                    if SUBPROC_LOGGER:
                                        SUBPROC_LOGGER.info(f"[GPTR_END] pid={proc2.pid} result=success")
                                    continue
                        except Exception:
                            pass
                    if SUBPROC_LOGGER:
                        SUBPROC_LOGGER.info(f"[GPTR_END] pid={proc.pid} result=failure")
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
                        if SUBPROC_LOGGER:
                            SUBPROC_LOGGER.info(f"[GPTR_END] pid={proc.pid} result=success")
                    else:
                        print(f"    WARN: No output path parsed from subprocess: {last_line}")
                        if SUBPROC_LOGGER:
                            SUBPROC_LOGGER.info(f"[GPTR_END] pid={proc.pid} result=failure")
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
        # Emit standardized MA events with a unique id for robust timeline parsing
        uid = pm_utils.uid3()
        try:
            if SUBPROC_LOGGER:
                SUBPROC_LOGGER.info(f"[MA_START] id={uid} model={model}")
                SUBPROC_LOGGER.info(f"[MA run {iterations}] Starting research for query: {query_prompt[:100]}...")  # Legacy start marker for compatibility

            ma_results = await MA_runner.run_multi_agent_runs(
                query_text=query_prompt,
                num_runs=int(iterations),
                model=model
            )
            generated["ma"] = ma_results
            
            if SUBPROC_LOGGER:
                for path, model_name in ma_results:
                    SUBPROC_LOGGER.info(f"[MA run {iterations}] Multi-agent report (Markdown) written to {path} model={model_name}")  # Legacy per-artifact line
                # Emit a single canonical END for the run
                SUBPROC_LOGGER.info(f"[MA_END] id={uid} model={model} result=success")
        except Exception as e:
            print(f"  MA generation failed: {e}")
            try:
                if SUBPROC_LOGGER:
                    SUBPROC_LOGGER.info(f"[MA_END] id={uid} model={model} result=failure")
            except Exception:
                pass

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


def _fpf_event_handler(event: dict):
    """
    Translate FPF events into structured logs for the subprocess logger.
    """
    if not SUBPROC_LOGGER or not isinstance(event, dict):
        return
    
    event_type = event.get("type")
    data = event.get("data", {})
    
    if event_type == "run_start":
        SUBPROC_LOGGER.info(
            "[FPF RUN_START] id=%s kind=%s provider=%s model=%s",
            data.get("id"), data.get("kind"), data.get("provider"), data.get("model")
        )
    elif event_type == "run_complete":
        SUBPROC_LOGGER.info(
            "[FPF RUN_COMPLETE] id=%s kind=%s provider=%s model=%s ok=%s",
            data.get("id"), data.get("kind"), data.get("provider"), data.get("model"), str(data.get("ok", "false")).lower()
        )


async def trigger_evaluation_for_all_files(
    output_folder: str, 
    config: dict, 
    generated_files: list[str] = None,
    timeout_seconds: int = 1800,
    is_combined_run: bool = False,
    save_winner: bool = False,
    winners_dir: str = None,
    timeline_json_path: str = None,
    master_html_path_holder: dict = None
):
    """
    Centralized evaluation trigger with explicit file list passing.
    
    Args:
        output_folder: Directory containing generated files (for reference/logging)
        config: ACM configuration dict
        generated_files: EXPLICIT list of absolute file paths to evaluate (NEW)
        timeout_seconds: Maximum time to wait for evaluation (default: 30 minutes)
        is_combined_run: Whether this is the secondary "Playoffs" run (default: False)
        save_winner: Whether to save the winning report (default: False)
        winners_dir: Directory to save the winner (required if save_winner is True)
        timeline_json_path: Path to timeline JSON file for HTML report (optional)
        master_html_path_holder: Dict holder for master HTML path, set when unified report is generated (optional)
    
    Usage in main():
        # After all processing completes for a markdown file:
        if config.get('eval', {}).get('auto_run', False):
            await trigger_evaluation_for_all_files(output_folder, config, generated_files=all_generated_files)
    """
    import datetime
    import re
    
    print("\n=== EVALUATION TRIGGER DEBUG ===")
    print(f"  Function: trigger_evaluation_for_all_files()")
    print(f"  Output folder: {output_folder}")
    print(f"  Time: {datetime.datetime.now()}")
    print(f"  Is Combined Run: {is_combined_run}")
    
    eval_config = config.get('eval', {})
    if not eval_config.get('auto_run', False):
        print("  âŒ Evaluation disabled in config (auto_run=False)")
        return
    
    if generated_files is None:
        generated_files = []
    
    print(f"  Generated files count: {len(generated_files)}")
    
    if not generated_files:
        print("  âŒ ERROR: No files to evaluate. Skipping.")
        return
    
    # Validate ALL files exist before proceeding
    print(f"\n=== PRE-EVALUATION FILE VALIDATION ===")
    valid_files = []
    for idx, fpath in enumerate(generated_files, 1):
        print(f"  {idx}. {os.path.basename(fpath)}")
        if os.path.isfile(fpath):
            fsize = os.path.getsize(fpath)
            fmtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            print(f"      âœ… EXISTS: {fsize} bytes, modified {fmtime}")
            valid_files.append(fpath)
        else:
            print(f"      âŒ MISSING: File does not exist!")
    
    if len(valid_files) != len(generated_files):
        print(f"  âš ï¸  WARNING: {len(generated_files) - len(valid_files)} files went missing between collection and evaluation!")
    
    if not valid_files:
        print(f"  âŒ ERROR: No valid files to evaluate. Aborting.")
        return
    
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        eval_script_path = os.path.join(repo_root, "api_cost_multiplier", "evaluate.py")
        
        print(f"\n=== SUBPROCESS COMMAND ===")
        print(f"  Eval script: {eval_script_path}")
        print(f"  Python executable: {sys.executable}")
        print(f"  Working directory: {os.getcwd()}")
        
        if not os.path.exists(eval_script_path):
            print(f"  âŒ ERROR: evaluate.py not found at {eval_script_path}. Skipping evaluation.")
            return
        
        # Use --target-files to pass EXPLICIT file list (not directory!)
        cmd = [sys.executable, "-u", eval_script_path, "--target-files"] + valid_files
        
        if save_winner:
            cmd.append("--save-winner")
            if winners_dir:
                cmd.extend(["--winners-dir", winners_dir])
        
        # Pass timeline JSON path if available
        if timeline_json_path and os.path.isfile(timeline_json_path):
            cmd.extend(["--timeline-json", timeline_json_path])
            print(f"  Timeline JSON: {timeline_json_path}")
        
        # Pass eval phase set based on whether this is a combined/playoffs run
        if is_combined_run:
            cmd.extend(["--eval-phase-set", "postcombine"])
            print(f"  Eval Phase Set: postcombine (playoffs)")
        else:
            cmd.extend(["--eval-phase-set", "precombine"])
            print(f"  Eval Phase Set: precombine")
        
        print(f"  Command (first 3 args): {cmd[:3]}")
        print(f"  File arguments ({len(valid_files)} files):")
        for idx, f in enumerate(valid_files, 1):
            print(f"    {idx}. {f}")
        
        # Log command to subprocess logger
        if SUBPROC_LOGGER:
            SUBPROC_LOGGER.info("[EVAL_START] Evaluating %d files: %s (Combined: %s)", 
                              len(valid_files), 
                              [os.path.basename(f) for f in valid_files],
                              is_combined_run)
        
        # Execute evaluation subprocess
        print(f"\n=== STARTING EVALUATION SUBPROCESS ===")
        print(f"  Time: {datetime.datetime.now()}")
        
        # Ensure child Python process uses UTF-8 for stdio to avoid charmap errors on Windows
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        # STREAMING FIX: Read output line-by-line instead of blocking with communicate()
        stdout_lines = []
        stderr_lines = []

        def _stream_eval(pipe, lines_list):
            try:
                for line in iter(pipe.readline, ''):
                    if not line: break
                    print(line, end='', flush=True)
                    lines_list.append(line)
            except Exception:
                pass
            finally:
                pipe.close()

        t_out = threading.Thread(target=_stream_eval, args=(proc.stdout, stdout_lines), daemon=True)
        t_err = threading.Thread(target=_stream_eval, args=(proc.stderr, stderr_lines), daemon=True)
        t_out.start()
        t_err.start()

        # Wait for process to finish
        proc.wait()
        
        t_out.join(timeout=5)
        t_err.join(timeout=5)

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        
        print(f"\n=== SUBPROCESS COMPLETED ===")
        print(f"  Time: {datetime.datetime.now()}")
        print(f"  Return code: {proc.returncode}")
        print(f"  Stdout length: {len(stdout)} chars")
        print(f"  Stderr length: {len(stderr)} chars")
        
        if proc.returncode != 0:
            print(f"  âŒ ERROR: Evaluation subprocess failed (rc={proc.returncode})")
            if stderr:
                print(f"\n=== EVALUATION STDERR ===")
                print(stderr)
            if SUBPROC_LOGGER:
                SUBPROC_LOGGER.error("[EVAL_ERROR] Evaluation failed: rc=%d stderr=%s", 
                                    proc.returncode, stderr[:500])
        else:
            print(f"  âœ… SUCCESS: Evaluation completed without errors")
            if stdout:
                print(f"\n=== EVALUATION STDOUT ===")
                print(stdout)
            
            # Log success
            if SUBPROC_LOGGER:
                SUBPROC_LOGGER.info("[EVAL_COMPLETE] Successfully evaluated %d files in %s", 
                                  len(valid_files), output_folder)
            
            # --- GENERATE EVAL TIMELINE ---
            # Extract DB path and export dir from stdout to generate eval timeline
            pre_db_path = None
            pre_export_dir = None
            match = re.search(r"\\[EVAL_SUMMARY\\] Database path: (.*)", stdout)
            if match:
                pre_db_path = match.group(1).strip()
            match_export = re.search(r"\\[EVAL_EXPORTS\\] dir=(.*)", stdout)
            if match_export:
                pre_export_dir = match_export.group(1).strip()
            
            # Generate pre-combiner eval timeline JSON
            pre_eval_timeline_path = None
            if pre_db_path and os.path.exists(pre_db_path):
                try:
                    # Add tools directory to path
                    import sys as _sys
                    tools_path = os.path.join(os.path.dirname(__file__), "tools")
                    if tools_path not in _sys.path:
                        _sys.path.insert(0, tools_path)
                    from eval_timeline_from_db import generate_eval_timeline
                    import json as _json
                    
                    acm_log_path = os.path.join(os.path.dirname(__file__), "logs", "acm_session.log")
                    eval_timeline = generate_eval_timeline(
                        db_path=pre_db_path,
                        log_path=acm_log_path if os.path.exists(acm_log_path) else None,
                        export_dir=pre_export_dir,
                        eval_type_label="pre_combiner" if not is_combined_run else "playoffs"
                    )
                    
                    # Save to export dir if available, else logs
                    if pre_export_dir and os.path.isdir(pre_export_dir):
                        pre_eval_timeline_path = os.path.join(pre_export_dir, "eval_timeline.json")
                    else:
                        pre_eval_timeline_path = os.path.join(os.path.dirname(__file__), "logs", f"eval_timeline_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                    
                    with open(pre_eval_timeline_path, "w", encoding="utf-8") as f:
                        _json.dump(eval_timeline, f, indent=2)
                    print(f"  Generated eval timeline: {pre_eval_timeline_path}")
                except Exception as e:
                    print(f"  Warning: Failed to generate eval timeline: {e}")

            # --- COMBINE & REVISE LOGIC ---
            # Only run if enabled, not already a combined run, and evaluation succeeded
            combine_config = config.get('combine', {})
            if not is_combined_run and combine_config.get('enabled', False):
                print("\n=== COMBINE & REVISE TRIGGERED ===")
                
                # 1. Extract DB Path from stdout
                db_path = None
                # Look for: [EVAL_SUMMARY] Database path: ...
                match = re.search(r"\[EVAL_SUMMARY\] Database path: (.*)", stdout)
                if match:
                    db_path = match.group(1).strip()
                    print(f"  Found DB Path: {db_path}")
                else:
                    print("  âš ï¸  WARNING: Could not find DB path in evaluation output. Skipping combine.")
                
                if db_path and os.path.exists(db_path):
                    try:
                        # Import Combiner here to avoid circular imports
                        try:
                            from api_cost_multiplier.combiner import ReportCombiner
                        except ImportError:
                            from combiner import ReportCombiner

                        combiner = ReportCombiner(config)
                        
                        # 2. Get Top 2 Reports
                        top_reports = combiner.get_top_reports(db_path, output_folder, limit=2)
                        print(f"  Top Reports selected: {len(top_reports)}")
                        for tr in top_reports:
                            print(f"    - {os.path.basename(tr)}")
                        
                        if len(top_reports) >= 2:
                            # 3. Run Combination
                            instructions_file = config.get('instructions_file')
                            print(f"  Running Combiner...")
                            
                            # Determine base_name from the first top report
                            # Assuming filename format: {base_name}.{type}.{idx}.{model}.{uid}.md
                            # We'll take the first part as base_name
                            first_report_name = os.path.basename(top_reports[0])
                            base_name = first_report_name.split('.')[0]
                            
                            combined_files = await combiner.combine(
                                top_reports, 
                                instructions_file, 
                                output_folder,
                                base_name=base_name
                            )
                            
                            print(f"  Combined Files generated: {len(combined_files)}")
                            for cf in combined_files:
                                print(f"    - {os.path.basename(cf)}")
                            
                            if combined_files:
                                # 4. Trigger "Playoffs" Evaluation
                                # Pool: Top 2 Parents + Combined Challengers
                                tournament_pool = top_reports + combined_files
                                print(f"\n=== TRIGGERING PLAYOFFS EVALUATION ===")
                                print(f"  Pool size: {len(tournament_pool)}")
                                
                                # Calculate winners directory (sibling to output_folder root)
                                output_root = config.get('output_folder')
                                if output_root:
                                    output_root_parent = os.path.dirname(output_root)
                                    winners_root = os.path.join(output_root_parent, "winners")
                                    
                                    # Calculate relative path of the current file's dir from output_root
                                    # output_folder here is the specific dir for the file (passed to trigger_evaluation_for_all_files)
                                    # Wait, trigger_evaluation_for_all_files receives 'output_folder' which is the specific dir
                                    # But config['output_folder'] is the root output folder.
                                    
                                    try:
                                        rel_dir = os.path.relpath(output_folder, output_root)
                                    except ValueError:
                                        rel_dir = "."
                                        
                                    winners_dir = os.path.join(winners_root, rel_dir)
                                else:
                                    # Fallback
                                    winners_dir = os.path.join(output_folder, "winners")
                                
                                await trigger_evaluation_for_all_files(
                                    output_folder,
                                    config,
                                    generated_files=tournament_pool,
                                    timeout_seconds=timeout_seconds,
                                    is_combined_run=True,  # Prevent infinite recursion
                                    save_winner=True,
                                    winners_dir=winners_dir
                                )
                                
                                # --- GENERATE UNIFIED HTML REPORT ---
                                # After playoffs, generate combined HTML with both pre-combiner and playoffs data
                                try:
                                    # Import from llm-doc-eval package and tools
                                    import sys as _sys
                                    llm_eval_path = os.path.join(os.path.dirname(__file__), "llm-doc-eval")
                                    if llm_eval_path not in _sys.path:
                                        _sys.path.insert(0, llm_eval_path)
                                    tools_path = os.path.join(os.path.dirname(__file__), "tools")
                                    if tools_path not in _sys.path:
                                        _sys.path.insert(0, tools_path)
                                    from reporting.html_exporter import generate_unified_html_report
                                    
                                    # Find the playoffs DB path from exports
                                    playoffs_db_path = None
                                    playoffs_export_dir = None
                                    
                                    # Look for the most recent eval_run directory
                                    exports_base = os.path.join(os.path.dirname(__file__), "gptr-eval-process", "exports")
                                    if os.path.isdir(exports_base):
                                        eval_dirs = sorted([d for d in os.listdir(exports_base) if d.startswith("eval_run_")], reverse=True)
                                        if len(eval_dirs) >= 1:
                                            # Most recent should be playoffs
                                            playoffs_export_dir = os.path.join(exports_base, eval_dirs[0])
                                            # Find the sqlite db
                                            db_base = os.path.join(os.path.dirname(__file__), "llm-doc-eval", "llm_doc_eval")
                                            if os.path.isdir(db_base):
                                                db_files = sorted([f for f in os.listdir(db_base) if f.startswith("results_") and f.endswith(".sqlite")], reverse=True)
                                                if db_files:
                                                    playoffs_db_path = os.path.join(db_base, db_files[0])
                                    
                                    # Get generation timeline path
                                    gen_timeline_path = os.path.join(os.path.dirname(__file__), "logs", "timeline_data.json")
                                    if not os.path.exists(gen_timeline_path):
                                        gen_timeline_path = None
                                    
                                    # Generate playoffs eval timeline
                                    playoffs_eval_timeline_path = None
                                    if playoffs_db_path and os.path.exists(playoffs_db_path):
                                        # eval_timeline_from_db already imported above
                                        from eval_timeline_from_db import generate_eval_timeline
                                        import json as _json
                                        
                                        acm_log = os.path.join(os.path.dirname(__file__), "logs", "acm_session.log")
                                        playoffs_timeline = generate_eval_timeline(
                                            db_path=playoffs_db_path,
                                            log_path=acm_log if os.path.exists(acm_log) else None,
                                            export_dir=playoffs_export_dir,
                                            eval_type_label="playoffs"
                                        )
                                        if playoffs_export_dir:
                                            playoffs_eval_timeline_path = os.path.join(playoffs_export_dir, "eval_timeline.json")
                                            with open(playoffs_eval_timeline_path, "w", encoding="utf-8") as f:
                                                _json.dump(playoffs_timeline, f, indent=2)
                                            print(f"  Generated playoffs eval timeline: {playoffs_eval_timeline_path}")
                                    
                                    # Build doc_paths for hyperlinks
                                    all_doc_paths = {}
                                    for f in valid_files:
                                        all_doc_paths[os.path.basename(f)] = f
                                    for f in tournament_pool:
                                        all_doc_paths[os.path.basename(f)] = f
                                    
                                    # Get FPF logs directory for cost parsing
                                    # Primary: FilePromptForge/logs (direct FPF output)
                                    # Fallback: logs/eval_fpf_logs (copied logs)
                                    eval_fpf_logs_dir = os.path.join(os.path.dirname(__file__), "FilePromptForge", "logs")
                                    if not os.path.isdir(eval_fpf_logs_dir):
                                        eval_fpf_logs_dir = os.path.join(os.path.dirname(__file__), "logs", "eval_fpf_logs")
                                    if not os.path.isdir(eval_fpf_logs_dir):
                                        eval_fpf_logs_dir = None
                                    
                                    # Generate unified HTML
                                    if db_path and playoffs_db_path:
                                        unified_output_dir = playoffs_export_dir or pre_export_dir or os.path.join(exports_base, "unified")
                                        os.makedirs(unified_output_dir, exist_ok=True)
                                        
                                        # Load eval timeline chart data from both phases
                                        # These are generated by EvalTimelineAggregator in evaluate.py
                                        # with phase-specific filenames:
                                        #   - eval_timeline_chart_pre.json (precombine)
                                        #   - eval_timeline_chart_post.json (postcombine)
                                        pre_eval_timeline_chart_data = None
                                        playoffs_eval_timeline_chart_data = None
                                        
                                        # If pre_export_dir is not set, try to find it from the second-most-recent export dir
                                        # (playoffs is most recent, pre-combine is second-most-recent)
                                        if not pre_export_dir and len(eval_dirs) >= 2:
                                            pre_export_dir = os.path.join(exports_base, eval_dirs[1])
                                            print(f"  [DEBUG] pre_export_dir inferred from second-most-recent: {pre_export_dir}")
                                        
                                        # Debug: log pre_export_dir value
                                        print(f"  [DEBUG] pre_export_dir = {pre_export_dir}")
                                        
                                        if pre_export_dir:
                                            pre_chart_path = os.path.join(pre_export_dir, "eval_timeline_chart_pre.json")
                                            print(f"  [DEBUG] Looking for pre-combine chart at: {pre_chart_path}")
                                            print(f"  [DEBUG] File exists: {os.path.isfile(pre_chart_path)}")
                                            if os.path.isfile(pre_chart_path):
                                                try:
                                                    with open(pre_chart_path, "r", encoding="utf-8") as f:
                                                        pre_eval_timeline_chart_data = json.load(f)
                                                    print(f"  Loaded pre-combine eval timeline chart: {pre_chart_path}")
                                                    print(f"  [DEBUG] Chart data has {len(pre_eval_timeline_chart_data.get('rows', []))} rows")
                                                except Exception as e:
                                                    print(f"  Warning: Failed to load pre-combine chart: {e}")
                                            else:
                                                print(f"  [DEBUG] Pre-combine chart file NOT FOUND at: {pre_chart_path}")
                                        else:
                                            print(f"  [DEBUG] pre_export_dir is not set - cannot load pre-combine chart")
                                        
                                        if playoffs_export_dir:
                                            playoffs_chart_path = os.path.join(playoffs_export_dir, "eval_timeline_chart_post.json")
                                            if os.path.isfile(playoffs_chart_path):
                                                try:
                                                    with open(playoffs_chart_path, "r", encoding="utf-8") as f:
                                                        playoffs_eval_timeline_chart_data = json.load(f)
                                                    print(f"  Loaded playoffs eval timeline chart: {playoffs_chart_path}")
                                                except Exception as e:
                                                    print(f"  Warning: Failed to load playoffs chart: {e}")
                                        
                                        unified_html_path = generate_unified_html_report(
                                            pre_db_path=db_path,
                                            playoffs_db_path=playoffs_db_path,
                                            output_dir=unified_output_dir,
                                            gen_timeline_json_path=gen_timeline_path,
                                            pre_eval_timeline_json_path=pre_eval_timeline_path,
                                            playoffs_eval_timeline_json_path=playoffs_eval_timeline_path,
                                            doc_paths=all_doc_paths,
                                            fpf_log_dir=eval_fpf_logs_dir,
                                            pre_eval_timeline_chart_data=pre_eval_timeline_chart_data,
                                            playoffs_eval_timeline_chart_data=playoffs_eval_timeline_chart_data
                                        )
                                        if unified_html_path and master_html_path_holder is not None:
                                            master_html_path_holder["path"] = unified_html_path
                                        print(f"  Generated unified HTML report in: {unified_output_dir}")
                                except Exception as e:
                                    print(f"  Warning: Failed to generate unified HTML report: {e}")
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print("  No combined files were generated.")
                        else:
                            print("  Not enough top reports found to combine (need 2).")
                            
                    except Exception as e:
                        print(f"  âŒ ERROR during Combine & Revise process: {e}")
                        import traceback
                        print(traceback.format_exc())
                else:
                    print(f"  DB path invalid or not found: {db_path}")

    except subprocess.TimeoutExpired as e:
        print(f"\nâŒ ERROR: Evaluation timed out after {e.timeout} seconds")
        if e.stdout:
            print(f"Partial stdout:\n{e.stdout}")
        if e.stderr:
            print(f"Partial stderr:\n{e.stderr}")
        if SUBPROC_LOGGER:
            SUBPROC_LOGGER.error("[EVAL_ERROR] Evaluation timeout after %ds", timeout_seconds)
        try:
            proc.kill()
        except Exception:
            pass
    except Exception as e:
        print(f"\nâŒ ERROR: Subprocess execution failed: {e}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        if SUBPROC_LOGGER:
            SUBPROC_LOGGER.error("[EVAL_ERROR] Evaluation exception: %s", e, exc_info=True)

async def process_file_fpf_batch(md_file_path: str, config: dict, fpf_entries: list[dict], iterations: int, keep_temp: bool = False, on_event=None, timeout: float | None = None):
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
            # Generate standardized filename with uid to avoid duplicates
            uid = pm_utils.uid3()
            model_label = pm_utils.sanitize_model_for_filename(model)
            base_name = Path(md_file_path).stem
            batch_runs.append({
                "id": run_id,
                "provider": provider,
                "model": model,
                "file_a": instructions_file,
                "file_b": md_file_path,
                "out": os.path.join(output_folder, f"{base_name}.fpf.{rep}.{model_label}.{uid}.txt")
            })

    if not batch_runs:
        print("  No valid FPF runs to execute in batch.")
        return

    try:
        fpf_results = await fpf_runner.run_filepromptforge_batch(batch_runs, options={"json": False}, on_event=on_event, timeout=timeout)
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

    # NOTE: Evaluation trigger removed - now centralized in main() after ALL processing completes
    # This prevents partial evaluations that waste API costs on incomplete file sets

    # Cleanup temp dir (consistent with other paths)
    # REMOVED: Cleanup here causes race condition with concurrent GPTR runs that use TEMP_BASE
    # try:
    #     if os.path.exists(TEMP_BASE) and not keep_temp:
    #         shutil.rmtree(TEMP_BASE)
    # except Exception as e:
    #     print(f"  Warning: failed to cleanup temp dir {TEMP_BASE}: {e}")


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
    # Map normalized console level to GPTâ€‘R 'research' logger level
    cn = str(console_name).lower()
    if cn == "low":
        research_level = logging.WARNING
    elif cn in ("high", "debug"):
        research_level = logging.DEBUG
    else:
        # Default to INFO for medium or unknown/default values
        research_level = logging.INFO

    try:
        logging.getLogger("research").setLevel(research_level)
    except Exception:
        # If the logger doesn't exist yet, GPTâ€‘R will create it; we keep ACM logger configured regardless.
        pass
    logging_levels.emit_health(acm_logger, console_name, file_name, console_level, file_level)

    # Configure dedicated file-only logger for subprocess output
    subproc_log_path = None
    try:
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        subproc_log_path = os.path.join(logs_dir, f"acm_subprocess_{timestamp}.log")
        
        # Use a standard FileHandler for unique log files, not RotatingFileHandler
        subproc_handler = logging.FileHandler(subproc_log_path, encoding="utf-8")
        
        subproc_formatter = logging.Formatter("%(asctime)s - acm.subproc - %(levelname)s - %(message)s")
        subproc_handler.setFormatter(subproc_formatter)
        subproc_logger = logging.getLogger("acm.subproc")
        subproc_logger.setLevel(logging.INFO)
        
        # Clear existing handlers to ensure no duplicates
        if subproc_logger.hasHandlers():
            subproc_logger.handlers.clear()
            
        subproc_logger.addHandler(subproc_handler)
        subproc_logger.propagate = False
        
        global SUBPROC_LOGGER
        SUBPROC_LOGGER = subproc_logger
        acm_logger.info(f"Subprocess log initialized at: {subproc_log_path}")
    except Exception as e:
        acm_logger.error(f"Failed to initialize subprocess logger: {e}")
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
    
    # Track the master HTML report path for final output
    master_html_path_holder: dict = {"path": None}

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

    # Shared variable to store timeline JSON path for evaluation
    timeline_json_path_holder = {"path": None}
    
    # Append end-of-run timeline generated from the unique subprocess log into ACM log
    # Also exports timeline JSON for HTML report
    def _append_timeline_to_acm_log(log_path_to_process: str, json_output_dir: str = None):
        if not log_path_to_process:
            acm_logger.warning("Timeline generation skipped: no subprocess log path provided.")
            return
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "timeline_from_logs.py")
            acm_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "acm_session.log")
            
            if not (os.path.isfile(script_path) and os.path.isfile(log_path_to_process) and os.path.isfile(acm_log)):
                acm_logger.warning(f"Timeline script or log files not found. Script: {script_path}, SubprocLog: {log_path_to_process}, AcmLog: {acm_log}")
                return

            # Build command with optional JSON output
            cmd = [sys.executable, "-u", script_path, "--log-file", log_path_to_process, "--acm-log-file", acm_log]
            
            # If json_output_dir provided, add JSON export
            json_path = None
            if json_output_dir:
                os.makedirs(json_output_dir, exist_ok=True)
                json_path = os.path.join(json_output_dir, "timeline_data.json")
                cmd.extend(["--json-output", json_path])
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out, err = proc.communicate(timeout=120)
            if proc.returncode == 0 and out:
                try:
                    acm_logger.info("[TIMELINE]")
                except Exception:
                    pass
                for ln in out.splitlines():
                    lns = (ln or "").strip()
                    if not lns:
                        continue
                    # Log each line exactly as produced (ACM logger will add timestamp/level prefix)
                    try:
                        acm_logger.info(lns)
                    except Exception:
                        pass
                # Store JSON path if created
                if json_path and os.path.isfile(json_path):
                    timeline_json_path_holder["path"] = json_path
                    acm_logger.info(f"[TIMELINE_JSON] Exported to {json_path}")
            else:
                try:
                    acm_logger.warning("Timeline script exited rc=%s; stderr: %s", proc.returncode, (err or "").strip())
                except Exception:
                    pass
        except Exception as e:
            try:
                acm_logger.warning("Timeline append failed: %s", e)
            except Exception:
                pass

    # runs-only mode: per-type iterations are deprecated; we use iterations_default later
    markdown_files = file_manager.find_markdown_files(input_folder)
    print(f"Found {len(markdown_files)} markdown files in input folder.")

    if config.get('one_file_only', False) and markdown_files:
        # markdown_files = [markdown_files[0]] # DISABLED: Logic moved to end of loop
        pass

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
            base_name = os.path.splitext(os.path.basename(md))[0]
            skip_file = False

            # 1. Check Eval Output (if enabled)
            eval_config = config.get('eval', {})
            if eval_config.get('auto_run', False):
                eval_out_rel = eval_config.get('output_directory', os.path.join("gptr-eval-process", "final_reports"))
                if not os.path.isabs(eval_out_rel):
                    eval_out_abs = os.path.abspath(os.path.join(config_dir, eval_out_rel))
                else:
                    eval_out_abs = eval_out_rel
                
                if os.path.exists(eval_out_abs):
                    # Search recursively for base_name.*
                    # Optimization: Only check folders modified recently? No, check all.
                    for root, dirs, files in os.walk(eval_out_abs):
                        for f in files:
                            if f.startswith(f"{base_name}."):
                                print(f"Skipping {md} (found eval output: {os.path.join(root, f)})")
                                skip_file = True
                                break
                        if skip_file: break

            # 2. Check Generation Output (if not already skipped)
            if not skip_file:
                try:
                    rel_path = os.path.relpath(md, input_folder)
                    output_dir_for_file = os.path.dirname(os.path.join(output_folder, rel_path))
                    
                    # Check for existing winners in sibling 'winners' directory
                    # Structure: .../parent/outputs -> .../parent/winners/{rel_path_dir}/{base_name}.*
                    output_root_parent = os.path.dirname(output_folder)
                    winners_root = os.path.join(output_root_parent, "winners")
                    rel_dir = os.path.dirname(rel_path)
                    winners_dir_for_file = os.path.join(winners_root, rel_dir)
                    
                    if os.path.exists(winners_dir_for_file):
                        existing_winners = [
                            f for f in os.listdir(winners_dir_for_file)
                            if f.startswith(f"{base_name}.") and f.endswith((".md", ".txt"))
                        ]
                        if existing_winners:
                            print(f"Skipping {md} (found existing winner: {os.path.join(winners_dir_for_file, existing_winners[0])})")
                            skip_file = True

                    if not skip_file and os.path.exists(output_dir_for_file):
                        # Look for any file starting with base_name. and having a relevant extension
                        # This covers .gptr., .dr., .ma., .fpf. etc.
                        existing = [
                            f for f in os.listdir(output_dir_for_file)
                            if f.startswith(f"{base_name}.") and f.endswith((".md", ".json", ".txt", ".docx", ".pdf"))
                        ]
                        if existing:
                            print(f"Skipping {md} (found {len(existing)} existing outputs, e.g. {existing[0]})")
                            skip_file = True
                except Exception as e:
                    print(f"Warning: Failed to check existing outputs for {md}: {e}")

            if skip_file:
                continue

            # Split FPF vs non-FPF runs. Execute non-FPF individually as before; batch all FPF at once.
            fpf_entries = []
            other_entries = []
            for idx, entry in enumerate(runs):
                rtype = (entry.get("type") or "").strip().lower()
                if rtype == "fpf":
                    fpf_entries.append(entry)
                else:
                    other_entries.append((idx, entry))

            # Split other entries into MA vs GPTâ€‘R (gptr/dr)
            ma_entries: list[tuple[int, dict]] = []
            gptr_dr_entries: list[tuple[int, dict]] = []
            for idx, entry in other_entries:
                rtype = (entry.get("type") or "").strip().lower()
                if rtype == "ma":
                    ma_entries.append((idx, entry))
                else:
                    # Only gptr/dr should be in this bucket; unknowns still run sequentially
                    gptr_dr_entries.append((idx, entry))

            # Split GPTâ€‘R into standard vs deep research for ordered execution
            gptr_entries: list[tuple[int, dict]] = []
            dr_entries: list[tuple[int, dict]] = []
            for idx, entry in gptr_dr_entries:
                rtype2 = (entry.get("type") or "").strip().lower()
                if rtype2 == "dr":
                    dr_entries.append((idx, entry))
                else:
                    gptr_entries.append((idx, entry))

            # Execute FPF as two sub-batches: openaidp first, then rest.
            fpf_tasks: list[asyncio.Task] = []
            rest_task: asyncio.Task | None = None
            open_task: asyncio.Task | None = None
            tracker: FpfInflightTracker | None = None
            if fpf_entries:
                fpf_openaidp = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() == "openaidp"]
                fpf_rest = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() != "openaidp"]

                # Initialize inflight tracker with totals for watermark gating
                totals_rest = len(fpf_rest) * int(iterations_all)
                totals_deep = len(fpf_openaidp) * int(iterations_all)
                tracker = FpfInflightTracker({"rest": totals_rest, "deep": totals_deep})

                async def _run_fpf_batch(run_id: str, entries: list[dict], on_event_cb, timeout: float | None = None):
                    _register_run(run_id)
                    try:
                        # Combine the tracker.update with our new event handler
                        def combined_event_handler(event):
                            if on_event_cb:
                                on_event_cb(event)
                            _fpf_event_handler(event)
                        
                        await process_file_fpf_batch(md, config, entries, iterations_all, keep_temp=keep_temp, on_event=combined_event_handler, timeout=timeout)
                    finally:
                        _deregister_run(run_id)

                # Launch openaidp sub-batch first (do not await here)
                if fpf_openaidp:
                    print(f"\n--- Executing FPF openaidp-first batch ({len(fpf_openaidp)} run templates x {iterations_all} iteration(s)) ---")
                    run_id_open = f"fpf-openAidp-{Path(md).stem}"
                    # No timeout for openaidp (Deep Research)
                    open_task = asyncio.create_task(_run_fpf_batch(run_id_open, fpf_openaidp, tracker.update, timeout=None))
                    fpf_tasks.append(open_task)

                # Launch rest sub-batch (do not await here)
                if fpf_rest:
                    print(f"\n--- Executing FPF rest batch ({len(fpf_rest)} run templates x {iterations_all} iteration(s)) ---")
                    run_id_rest = f"fpf-rest-{Path(md).stem}"
                    # No batch timeout (rely on internal FPF per-call timeouts)
                    rest_task = asyncio.create_task(_run_fpf_batch(run_id_rest, fpf_rest, tracker.update, timeout=None))
                    fpf_tasks.append(rest_task)

            # Launch MA immediately (do not await) so it runs concurrently with GPTâ€‘R/DR and FPF
            tasks_ma: list[asyncio.Task] = []
            
            if ma_entries:
                # Resolve MA concurrency settings
                ma_enabled, ma_max_conc, ma_launch_delay = _resolve_ma_concurrency(config)
                
                if not ma_enabled:
                    # Sequential MA execution
                    print(f"\n--- Executing Multi-Agent runs ({len(ma_entries)} templates x {iterations_all} iteration(s)) (sequential) ---")
                    
                    async def _run_ma_serial(idx0: int, e0: dict):
                        run_id0 = f"ma-{idx0}"
                        _register_run(run_id0)
                        try:
                            await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                        finally:
                            _deregister_run(run_id0)
                    
                    for idx, entry in ma_entries:
                        tasks_ma.append(asyncio.create_task(_run_ma_serial(idx, entry)))
                else:
                    # Concurrent MA execution with semaphore gating
                    print(f"\n[MA Concurrency] enabled=True max_concurrent_runs={ma_max_conc} launch_delay_seconds={ma_launch_delay}")
                    sem_ma = asyncio.Semaphore(ma_max_conc)
                    
                    async def _run_ma_limited(idx0: int, e0: dict):
                        async with sem_ma:
                            run_id0 = f"ma-{idx0}"
                            _register_run(run_id0)
                            try:
                                await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                            finally:
                                _deregister_run(run_id0)
                    
                    for idx, entry in ma_entries:
                        tasks_ma.append(asyncio.create_task(_run_ma_limited(idx, entry)))

            # Next: Run GPTâ€‘R (standard) with report-level concurrency and launch pacing
            # Prepare shared state so standard and deep can run concurrently under one cap
            tasks_gptr_std: list[asyncio.Task] = []
            sem_all: asyncio.Semaphore | None = None
            
            # Start headroom gate as background task (non-blocking)
            gate_task = None
            if 'tracker' in locals() and tracker is not None:
                async def _wait_for_headroom():
                    try:
                        while True:
                            hr = tracker.headroom(low_watermark=1)
                            if hr.get("ready", False):
                                break
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass
                gate_task = asyncio.create_task(_wait_for_headroom())
            
            enabled, max_conc, launch_delay = _resolve_gptr_concurrency(config)
            if not enabled:
                # Fall back to sequential behavior
                for idx, entry in gptr_entries:
                    print(f"\n--- Executing GPTâ€‘R (standard) run #{idx} (sequential): {entry} ---")
                    run_id = f"gptr-std-{idx}"
                    _register_run(run_id)
                    try:
                        await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                    finally:
                        _deregister_run(run_id)
            else:
                print(f"\n[GPTâ€‘R Concurrency] (standard) enabled=True max_concurrent_reports={max_conc} launch_delay_seconds={launch_delay}")
                sem_all = asyncio.Semaphore(max_conc)

                async def _limited_std(idx0: int, e0: dict):
                    async with sem_all:
                        run_id0 = f"gptr-std-{idx0}"
                        _register_run(run_id0)
                        try:
                            await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                        finally:
                            _deregister_run(run_id0)

                # Create all tasks immediately (don't wait for gate)
                for j, (idx, entry) in enumerate(gptr_entries):
                    tasks_gptr_std.append(asyncio.create_task(_limited_std(idx, entry)))
                    if j < len(gptr_entries) - 1 and launch_delay > 0:
                        await asyncio.sleep(launch_delay)
                # Do not await here; deep group will be scheduled next and we'll await both together

            # Then: Run GPTâ€‘R Deep Research with the same concurrency controls
            # Note: Deep uses same gate_task and sem_all as standard to run concurrently
            if not enabled:
                for idx, entry in dr_entries:
                    print(f"\n--- Executing GPTâ€‘R (deep) run #{idx} (sequential): {entry} ---")
                    run_id = f"gptr-deep-{idx}"
                    _register_run(run_id)
                    try:
                        await process_file_run(md, config, entry, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                    finally:
                        _deregister_run(run_id)
            else:
                print(f"\n[GPTâ€‘R Concurrency] (deep) enabled=True max_concurrent_reports={max_conc} launch_delay_seconds={launch_delay}")
                # Use the same semaphore as standard to cap total GPTâ€‘R concurrency
                if sem_all is None:
                    sem_all = asyncio.Semaphore(max_conc)
                tasks_gptr_dr: list[asyncio.Task] = []

                async def _limited_dr(idx0: int, e0: dict):
                    async with sem_all:
                        run_id0 = f"gptr-deep-{idx0}"
                        _register_run(run_id0)
                        try:
                            await process_file_run(md, config, e0, iterations_all, keep_temp=keep_temp, forward_subprocess_output=forward_subprocess_output)
                        finally:
                            _deregister_run(run_id0)

                for j, (idx, entry) in enumerate(dr_entries):
                    tasks_gptr_dr.append(asyncio.create_task(_limited_dr(idx, entry)))
                    if j < len(dr_entries) - 1 and launch_delay > 0:
                        await asyncio.sleep(launch_delay)

                # Await MA, standard and deep groups together
                all_tasks: list[asyncio.Task] = []
                all_tasks.extend(tasks_ma or [])
                all_tasks.extend(tasks_gptr_std or [])
                all_tasks.extend(tasks_gptr_dr)
                if all_tasks:
                    await asyncio.gather(*all_tasks, return_exceptions=False)

            # If GPT-R is sequential, await MA separately to ensure completion
            if not enabled:
                # Sequential GPT-R mode: still await MA tasks to ensure they complete
                try:
                    if 'tasks_ma' in locals() and tasks_ma:
                        await asyncio.gather(*tasks_ma, return_exceptions=False)
               
                except Exception:
                    pass

            # Check if we should stop after one file
            if config.get('one_file_only', False):
                print("Stopping after one file (one_file_only=True)")
                break

        # Await both FPF batches (rest and openaidp-deep) before evaluation
        try:
            if 'rest_task' in locals() and rest_task is not None:
                await rest_task
            if 'open_task' in locals() and open_task is not None:
                await open_task
        except Exception:
            pass

        # CRITICAL: Trigger evaluation ONCE after ALL processing completes
        # This ensures evaluation sees all generated files (FPF + MA + GPTR)

        # and prevents expensive partial evaluations
        try:
            eval_config = config.get('eval', {})
            if eval_config.get('auto_run', False):
                print("\n=== TRIGGERING EVALUATION FOR ALL GENERATED FILES ===")
                # Determine output directory for this markdown file
                rel_path = os.path.relpath(md, input_folder)
                output_dir_for_file = os.path.dirname(os.path.join(output_folder, rel_path))
                
                # Count expected files before triggering evaluation
                expected_count = len([e for e in runs if e.get('type') in ('fpf', 'ma', 'gptr', 'dr')])
                print(f"  Expected generated files: {expected_count}")
                
                # Collect ALL generated files from this run for evaluation
                # Use recently modified files (within last 120 seconds) to ensure we only evaluate current run
                all_generated_files = []
                try:
                    import datetime
                    
                    # EXTREME LOGGING: Start of file collection
                    print(f"\n=== FILE COLLECTION DEBUG ===")
                    print(f"  Output directory: {output_dir_for_file}")
                    print(f"  Current time: {time.time()} ({datetime.datetime.now()})")
                    
                    # Add small buffer to ensure files have finished writing
                    print(f"  Sleeping 2 seconds to ensure file writes complete...")
                    await asyncio.sleep(2)
                    
                    # Use batch start time as threshold (files created THIS RUN only)
                    # batch_start_ts is captured at beginning of main() function
                    recent_threshold = batch_start_ts
                    print(f"  Batch start time: {recent_threshold} ({datetime.datetime.fromtimestamp(recent_threshold)})")
                    print(f"  Looking for files modified after: {datetime.datetime.fromtimestamp(recent_threshold)}")
                    
                    # List ALL files first for diagnostics
                    all_files_in_dir = []
                    try:
                        all_files_in_dir = os.listdir(output_dir_for_file)
                        print(f"  Total items in directory: {len(all_files_in_dir)}")
                    except Exception as list_ex:
                        print(f"  ERROR: Cannot list directory: {list_ex}")
                        raise
                    
                    # Process each file with extreme logging
                    for fname in all_files_in_dir:
                        fpath = os.path.join(output_dir_for_file, fname)
                        
                        # Log every file encountered
                        print(f"\n  Examining: {fname}")
                        
                        # Check if it's a file
                        if not os.path.isfile(fpath):
                            print(f"    âŒ SKIP: Not a file (is directory or other)")
                            continue
                        
                        # Check extension
                        if not fname.endswith(('.md', '.txt')):
                            print(f"    âŒ SKIP: Wrong extension (not .md or .txt)")
                            continue
                        
                        # Get file stats
                        try:
                            fsize = os.path.getsize(fpath)
                            fmtime = os.path.getmtime(fpath)
                            fmtime_dt = datetime.datetime.fromtimestamp(fmtime)
                            age_seconds = time.time() - fmtime
                            
                            print(f"    ðŸ“Š Size: {fsize} bytes")
                            print(f"    ðŸ“… Modified: {fmtime_dt} ({fmtime})")
                            print(f"    â±ï¸  Age: {age_seconds:.1f} seconds")
                            
                            # Check recency threshold
                            if fmtime >= recent_threshold:
                                all_generated_files.append(fpath)
                                print(f"    âœ… INCLUDED: File is recent enough")
                            else:
                                print(f"    âŒ EXCLUDED: File is too old (>120s)")
                                
                        except Exception as stat_ex:
                            print(f"    âŒ ERROR getting file stats: {stat_ex}")
                            continue
                    
                    print(f"\n=== FILE COLLECTION SUMMARY ===")
                    print(f"  Expected files: {expected_count}")
                    print(f"  Recent files found: {len(all_generated_files)}")
                    print(f"  Total files examined: {len(all_files_in_dir)}")
                    
                    # VALIDATION: Warn if mismatch
                    if len(all_generated_files) != expected_count:
                        print(f"  âš ï¸  WARNING: Found {len(all_generated_files)} files but expected {expected_count}")
                        print(f"  This may indicate:")
                        print(f"    - Files still being written (race condition)")
                        print(f"    - Generation failures (some runs didn't produce output)")
                        print(f"    - Stale files from previous runs (too old to include)")
                    
                    if len(all_generated_files) < 1:
                        print(f"  âŒ ERROR: No recent files found in {output_dir_for_file}. Skipping evaluation.")
                    else:
                        print(f"\n=== FILES TO EVALUATE ===")
                        for idx, f in enumerate(all_generated_files, 1):
                            fsize = os.path.getsize(f)
                            fmtime_dt = datetime.datetime.fromtimestamp(os.path.getmtime(f))
                            print(f"  {idx}. {os.path.basename(f)} ({fsize} bytes, {fmtime_dt})")
                        
                        # Generate timeline JSON BEFORE evaluation so it can be included in HTML report
                        try:
                            if subproc_log_path and os.path.isfile(subproc_log_path):
                                timeline_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
                                os.makedirs(timeline_output_dir, exist_ok=True)
                                _append_timeline_to_acm_log(subproc_log_path, json_output_dir=timeline_output_dir)
                                if timeline_json_path_holder.get("path"):
                                    print(f"  Timeline JSON generated: {timeline_json_path_holder['path']}")
                        except Exception as tl_err:
                            print(f"  Warning: Timeline JSON generation failed: {tl_err}")
                        
                        await trigger_evaluation_for_all_files(
                            output_dir_for_file,
                            config,
                            generated_files=all_generated_files,
                            timeline_json_path=timeline_json_path_holder.get("path"),
                            master_html_path_holder=master_html_path_holder
                        )
                except Exception as list_err:
                    print(f"\nâŒ ERROR: File collection failed: {list_err}")
                    import traceback
                    print(f"Traceback:\n{traceback.format_exc()}")
        except Exception as eval_err:
            print(f"  ERROR: Evaluation trigger failed: {eval_err}")

        # Cleanup temp dir after all tasks for this file are done
        try:
            if os.path.exists(TEMP_BASE) and not keep_temp:
                shutil.rmtree(TEMP_BASE)
        except Exception as e:
            print(f"  Warning: failed to cleanup temp dir {TEMP_BASE}: {e}")

        # Timeline already generated before evaluation; just stop heartbeat
        try:
            hb_stop.set()
        except Exception:
            pass
        
        # Print and open the master HTML report
        if master_html_path_holder.get("path"):
            html_path = master_html_path_holder["path"]
            print(f"\n{'='*60}")
            print(f"MASTER HTML REPORT: {html_path}")
            print(f"{'='*60}\n")
            # Open the HTML file in the default browser
            try:
                import webbrowser
                webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")
                print(f"Opened HTML report in browser.")
            except Exception as e:
                print(f"Note: Could not auto-open browser: {e}")
        
        print("\nprocess_markdown runner finished.")
        return

    # No legacy path: require explicit 'runs' configuration
    print("ERROR: config.yaml must define a 'runs' array (baselines/additional_models are no longer supported).")
    # Even if misconfigured, attempt to append any available timeline for diagnostics
    try:
        _append_timeline_to_acm_log(subproc_log_path)
    except Exception:
        pass
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

