import os
import sys
import asyncio
import tempfile
import shutil
import uuid
import subprocess
from pathlib import Path
import re

# Reuse utilities from existing process-markdown package
# These are relative imports since this script sits inside gptr-eval-process/process-markdown-noeval/

# Heartbeat helper: prints a short alive message every few seconds so the terminal always shows activity.
import threading
import time

def start_heartbeat(label: str = "process_markdown_noeval", interval: float = 3.0):
    """
    Start a daemon heartbeat thread that prints a short message every `interval` seconds.
    Returns a threading.Event you can set() to stop the heartbeat.
    """
    stop_event = threading.Event()

    def _hb():
        counter = 0
        while not stop_event.is_set():
            counter += 1
            print(f"[HEARTBEAT {label}] alive ({counter})", flush=True)
            # wait with timeout so stop_event can interrupt
            stop_event.wait(interval)

    t = threading.Thread(target=_hb, daemon=True)
    t.start()
    return stop_event

# End heartbeat helper
# Import utilities from the local package where example helpers live.
# Use explicit package imports to reflect the repository layout.
# When running this script directly, Python's sys.path[0] is the package directory
# (process_markdown) which prevents importing the `process_markdown` package by name.
# Add the repository root (parent dir) to sys.path so absolute imports like
# `process_markdown.*` work in both direct runs and when executed as a package.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from process_markdown.EXAMPLE_fucntions import config_parser, file_manager, gpt_researcher_client

"""
process_markdown_noeval.py

Behavior:
- For each input .md (recursively discovered) that does NOT already have an output file,
  generate 9 reports and save them into the configured output directory (mirroring input structure).
  Order:
    1) 3 Multi-Agent (MA) reports (generated first)
    2) 3 GPT-Researcher standard reports
    3) 3 GPT-Researcher deep research reports
- Do NOT run any evaluation step.
- Save all 9 outputs with the naming scheme:
    {basename}.ma.1.md ... {basename}.ma.3.md
    {basename}.gptr.1.md ... {basename}.gptr.3.md
    {basename}.dr.1.md  ... {basename}.dr.3.md
- Uses the Multi_Agent_CLI.py script found under ../newexe/GPT-Researcher-Multi-Agent-CLI/Multi_Agent_CLI.py
  This script is invoked as a subprocess; query text is written to a temporary file and passed with --query-file.
"""

# Path to the MA CLI script (local MA_CLI included in this repo)
MA_CLI_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'MA_CLI', 'Multi_Agent_CLI.py'))

# Temp base dir for intermediate outputs (placed under process_markdown directory)
TEMP_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'temp_process_markdown_noeval'))


def ensure_temp_dir(path):
    os.makedirs(path, exist_ok=True)
    return path

def sanitize_model_for_filename(model: str | None) -> str:
    """
    Convert a raw model string to a safe, short filename component.
    Behavior:
      - If model is None or empty -> "unknown-model"
      - If contains ":" (provider:model) -> take the part after the first colon (model only)
      - Lowercase, replace non-alphanum (except .,_,-) with '-'
      - Collapse repeated '-' and strip leading/trailing '-'
      - Truncate to 60 chars
    """
    if not model:
        return "unknown-model"
    # If provider included like "openai:gpt-4o", take the model only (after first colon)
    if ":" in model:
        try:
            model = model.split(":", 1)[1]
        except Exception:
            pass
    s = str(model).lower()
    # Replace any sequence of characters that are not a-z0-9._- with a single hyphen
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    # Collapse multiple hyphens
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    if not s:
        return "unknown-model"
    return s[:60]


async def run_multi_agent_once(query_text: str, output_folder: str, run_index: int) -> str:
    """
    Run the Multi_Agent_CLI.py as a subprocess once.
    Returns the path to the generated markdown file (absolute) on success.
    """
    if not os.path.exists(MA_CLI_PATH):
        raise FileNotFoundError(f"Multi-Agent CLI not found at {MA_CLI_PATH}")

    # Write query to a temp file (the MA CLI supports --query-file)
    tmp_query_file = os.path.join(output_folder, f"query_{uuid.uuid4()}.txt")
    with open(tmp_query_file, "w", encoding="utf-8") as f:
        f.write(query_text)

    # Create an explicit output filename so we can find it easily
    output_filename = f"ma_report_{run_index}_{uuid.uuid4()}.md"
    cmd = [
        sys.executable,
        "-u",
        MA_CLI_PATH,
        "--query-file",
        tmp_query_file,
        "--output-folder",
        output_folder,
        "--output-filename",
        output_filename,
        "--publish-markdown"
    ]

    # Launch subprocess and stream output in real time to avoid blocking on input prompts.
    # Build environment: start from current env and merge keys from available .env files.
    env = os.environ.copy()
    try:
        # repo_root is two levels up from this file
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

        # If MA CLI doesn't have a local .env, attempt to copy the root gptr-eval-process/.env into it
        try:
            ma_cli_dir = os.path.dirname(MA_CLI_PATH)
            ma_env_path = os.path.join(ma_cli_dir, '.env')
            root_env_path = os.path.join(repo_root, 'process_markdown', '.env')
            # If MA CLI .env is missing and root env exists, copy it to MA CLI dir
            if not os.path.exists(ma_env_path) and os.path.exists(root_env_path):
                try:
                    shutil.copy2(root_env_path, ma_env_path)
                    print(f"Copied root .env to MA CLI directory: {ma_env_path}")
                except Exception as copy_err:
                    print(f"Warning: failed to copy root .env to MA CLI directory: {copy_err}")

            # Also ensure gpt-researcher has an .env so programmatic runs see keys
            try:
                gptr_env_target = os.path.join(repo_root, 'gptr-eval-process', 'gpt-researcher-3.2.9', '.env')
                if not os.path.exists(gptr_env_target) and os.path.exists(root_env_path):
                    try:
                        shutil.copy2(root_env_path, gptr_env_target)
                        print(f"Copied root .env to gpt-researcher env: {gptr_env_target}")
                    except Exception as copy_err2:
                        print(f"Warning: failed to copy root .env to gpt-researcher env: {copy_err2}")
            except Exception:
                pass

        except Exception:
            pass

        # Load env vars from gpt-researcher .env (if present)
        gptr_env_path = os.path.join(repo_root, 'gptr-eval-process', 'gpt-researcher-3.2.9', '.env')
        if os.path.exists(gptr_env_path):
            with open(gptr_env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    if k and v:
                        env.setdefault(k.strip(), v.strip())

        # Also load env vars from MA CLI .env if present (priority after gpt_researcher so explicit MA .env can override)
        try:
            ma_env_path = os.path.join(os.path.dirname(MA_CLI_PATH), '.env')
            if os.path.exists(ma_env_path):
                with open(ma_env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        if k and v:
                            env.setdefault(k.strip(), v.strip())
        except Exception:
            pass

    except Exception:
        # non-fatal; continue with existing env
        pass

    # Ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Use Popen to stream stdout/stderr; disable stdin so CLI won't block on input()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    # Read stdout and stderr concurrently using threads to avoid blocking
    import threading

    stdout_lines = []
    stderr_lines = []

    def _reader(stream, prefix, collector):
        try:
            for line in iter(stream.readline, ''):
                if line == '':
                    break
                # Normalize carriage returns so progress bars show correctly
                normalized = line.rstrip('\r\n')
                print(f"{prefix} {normalized}", flush=True)
                collector.append(normalized)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_reader, args=(process.stdout, f"[MA run {run_index}]", stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(process.stderr, f"[MA run {run_index} ERR]", stderr_lines), daemon=True)

    t_out.start()
    t_err.start()

    # Wait for process to exit and readers to finish
    process.wait()
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    stderr_out = "\n".join(stderr_lines)

    # Check return code
    if process.returncode != 0:
        raise RuntimeError(f"Multi-Agent run failed with exit code {process.returncode}. Stderr: {stderr_out}")

    # Construct expected path
    md_path = os.path.join(output_folder, output_filename)
    if not os.path.exists(md_path):
        # MA CLI may write a slightly different name; try to find newest .md file in output_folder
        md_files = sorted(Path(output_folder).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            return str(md_files[0].absolute())
        raise FileNotFoundError(f"Expected MA output {md_path} not found; no .md files in {output_folder}")

    return os.path.abspath(md_path)


async def run_multi_agent_runs(query_text: str, num_runs: int = 3) -> list:
    """
    Run the MA CLI num_runs times. Each run gets its own temp output folder.
    Returns a list of tuples: [(absolute_path, model_name_used), ...]
    The MA model is resolved once before the runs using environment variables
    (STRATEGIC_LLM or MA_MODEL) and falls back to the MA default 'gpt-4o'.
    """
    results = []

    # Resolve MA model (prefer STRATEGIC_LLM or MA_MODEL env). If value contains a provider (provider:model),
    # only keep the model part as requested.
    ma_model_raw = os.environ.get("STRATEGIC_LLM") or os.environ.get("MA_MODEL") or None
    if ma_model_raw and ":" in ma_model_raw:
        ma_model = ma_model_raw.split(":", 1)[1]
    else:
        ma_model = ma_model_raw or "gpt-4o"

    for i in range(1, num_runs + 1):
        run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"ma_run_{uuid.uuid4()}"))
        try:
            md = await run_multi_agent_once(query_text, run_temp, i)
            results.append((md, ma_model))
        except Exception as e:
            print(f"  MA run {i} failed: {e}")
            # continue to next run (we preserve partial results)
    return results


def normalize_report_entries(results):
    """
    Normalize entries returned by gpt_researcher_client.run_concurrent_research or other run functions.

    Input items may be:
      - tuple/list: (path, model_name)
      - str: path

    Returns list of tuples: [(abs_path, model_name_or_none), ...]
    """
    normalized = []
    for res in results:
        model = None
        if isinstance(res, (tuple, list)):
            path = res[0]
            if len(res) > 1:
                model = res[1]
        else:
            path = res
        if path:
            normalized.append((os.path.abspath(path), model))
    return normalized


async def run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> list:
    """
    Use existing gpt_researcher_client to run concurrent research.
    Returns list of absolute paths to generated reports (may be empty on failures).
    """
    try:
        raw = await gpt_researcher_client.run_concurrent_research(query_prompt, num_runs=num_runs, report_type=report_type)
    except Exception as e:
        print(f"  GPT-Researcher ({report_type}) runs failed: {e}")
        return []
    # raw may be list of tuples or strings
    return normalize_report_entries(raw)


def save_generated_reports(input_md_path: str, input_base_dir: str, output_base_dir: str, generated_paths: dict):
    """
    Copy generated files into the output folder that mirrors the input structure,
    using the naming scheme specified.

    generated_paths is expected to be a dict:
      {"ma": [...], "gptr": [...], "dr": [...]}
    where each list item may be either:
      - a path string, or
      - a tuple/list (path, model_name)
    The output filenames will include the report type (ma/gptr/dr), the run index,
    and the sanitized model name (model-only, no provider).
    """
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
        model_label = sanitize_model_for_filename(model)
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
            # fallback to env if available
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = sanitize_model_for_filename(model)
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
        model_label = sanitize_model_for_filename(model)
        dest = os.path.join(output_dir_for_file, f"{base_name}.dr.{idx}.{model_label}.md")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save Deep research report {p} -> {dest}: {e}")

    return saved


async def process_file(md_file_path: str, config: dict):
    input_folder = os.path.abspath(config["input_folder"])
    output_folder = os.path.abspath(config["output_folder"])
    instructions_file = os.path.abspath(config["instructions_file"])

    print(f"\nProcessing file: {md_file_path}")
    output_file_path = file_manager.get_output_path(md_file_path, input_folder, output_folder)

    if file_manager.output_exists(output_file_path):
        print(f"  Output exists at {output_file_path}. Skipping.")
        return

    # Read markdown content
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except Exception as e:
        print(f"  Error reading {md_file_path}: {e}")
        return

    # Read instructions
    try:
        with open(instructions_file, "r", encoding="utf-8") as f:
            instructions_content = f.read()
    except Exception as e:
        print(f"  Error reading instructions {instructions_file}: {e}")
        return

    query_prompt = gpt_researcher_client.generate_query_prompt(markdown_content, instructions_content)

    # Ensure temp base exists
    ensure_temp_dir(TEMP_BASE)

    # 1) Run 3 MA reports (sequentially per spec that MA reports come first)
    print("  Generating 3 Multi-Agent reports (MA) ...")
    try:
        ma_results = await run_multi_agent_runs(query_prompt, num_runs=3)
        print(f"  MA generated {len(ma_results)} report(s).")
    except Exception as e:
        print(f"  MA generation failed: {e}")
        ma_results = []

    # 2) Run 3 GPT-Researcher standard reports and 3 deep reports (concurrently)
    print("  Generating 3 GPT-Researcher standard reports (concurrently) ...")
    gptr_task = asyncio.create_task(run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="research_report"))

    print("  Generating 3 GPT-Researcher deep research reports (concurrently) ...")
    dr_task = asyncio.create_task(run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="deep"))

    gptr_results, dr_results = await asyncio.gather(gptr_task, dr_task)

    print(f"  GPT-R standard generated: {len(gptr_results)}")
    print(f"  GPT-R deep generated: {len(dr_results)}")

    generated = {"ma": ma_results, "gptr": gptr_results, "dr": dr_results}

    # Save outputs (copy into output folder using naming scheme)
    print("  Saving generated reports to output folder (mirroring input structure)...")
    saved_files = save_generated_reports(md_file_path, input_folder, output_folder, generated)
    print(f"  Saved {len(saved_files)} report(s) to {os.path.dirname(saved_files[0]) if saved_files else output_folder}")

    # Cleanup: remove TEMP_BASE for this file run to avoid disk accumulation
    # (Note: if you prefer to keep temp artifacts, comment this out)
    try:
        # remove only directories created under TEMP_BASE
        if os.path.exists(TEMP_BASE):
            shutil.rmtree(TEMP_BASE)
    except Exception as e:
        print(f"  Warning: failed to cleanup temp dir {TEMP_BASE}: {e}")


async def main():
    # Step 1: Load configuration (reuse existing parser)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # config.yaml resides in this package directory
    config_file_path = os.path.join(current_dir, 'config.yaml')
    config_file_path = os.path.abspath(config_file_path)
    config_dir = os.path.dirname(config_file_path)
    config = config_parser.load_config(config_file_path)

    if not config:
        print("Failed to load configuration. Exiting.")
        return

    # Start heartbeat for visible terminal activity
    hb_stop = start_heartbeat("process_markdown_noeval", interval=3.0)

    # Resolve relative paths in config relative to the config file directory
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

    # Persist resolved absolute paths back into the loaded config so other functions use them
    config['input_folder'] = input_folder
    config['output_folder'] = output_folder
    config['instructions_file'] = instructions_file

    # Discover markdown files
    markdown_files = file_manager.find_markdown_files(input_folder)
    print(f"Found {len(markdown_files)} markdown files in input folder.")

    # Optional: if one_file_only is set in config, limit processing
    if config.get('one_file_only', False) and markdown_files:
        markdown_files = [markdown_files[0]]

    # Process files sequentially (can be parallelized later if desired)
    for md in markdown_files:
        await process_file(md, config)

    print("\nprocess_markdown_noeval finished.")


if __name__ == "__main__":
    asyncio.run(main())
