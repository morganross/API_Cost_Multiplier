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

# Ensure we prefer the locally checked-out gpt-researcher sources (side-effect).
# Add repository root to sys.path so package imports like `process_markdown.*` resolve
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    sys.path.insert(0, os.path.join(repo_root, 'gpt-researcher'))

# Import side-effect helper that prefers local gpt-researcher when available
# import run_gptr_local  # side-effect: prefer local gpt-researcher


# Now import refactored modules (sys.path updated so package import works)
from functions import pm_utils
from functions import MA_runner
from functions import fpf_runner

from EXAMPLE_fucntions import config_parser, file_manager, gpt_researcher_client

"""
process_markdown_noeval.py (refactored)

This version delegates:
- heartbeat, temp dir and model sanitization utilities to process_markdown.functions.pm_utils
- Multi-Agent CLI runs to process_markdown.functions.MA_runner

Other functions (gpt-researcher wrapper, saving reports, and orchestration) are kept here
for now to minimize simultaneous edits.
"""

# Use TEMP_BASE defined in MA_runner for consistency
TEMP_BASE = MA_runner.TEMP_BASE


async def run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> list:
    """
    Use existing gpt_researcher_client to run concurrent research.
    Returns list of absolute paths to generated reports (may be empty on failures).
    """
    try:
        raw = await gpt_researcher_client.run_concurrent_research(
            query_prompt, num_runs=num_runs, report_type=report_type
        )
    except Exception as e:
        print(f"  GPT-Researcher ({report_type}) runs failed: {e}")
        return []
    # raw may be list of tuples or strings
    return pm_utils.normalize_report_entries(raw)


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
            # fallback to env if available
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
        dest = os.path.join(output_dir_for_file, f"{base_name}.fpf.{idx}.{model_label}.txt")
        try:
            shutil.copy2(p, dest)
            saved.append(dest)
        except Exception as e:
            print(f"    Failed to save FPF report {p} -> {dest}: {e}")

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
    pm_utils.ensure_temp_dir(TEMP_BASE)

    # 1) Run MA reports
    print("  Generating 1 Multi-Agent reports (MA) ...")
    # Wrap query_prompt in a list to satisfy sub_queries.append() expectation in gpt-researcher
    # This works around Attribute Error in gpt-researcher/gpt_researcher/skills/researcher.py
    ma_input_query = [query_prompt] if isinstance(query_prompt, str) else query_prompt
    try:
        ma_results = await MA_runner.run_multi_agent_runs(ma_input_query, num_runs=1)
        print(f"  MA generated {len(ma_results)} report(s).")
    except Exception as e:
        print(f"  MA generation failed: {e}")
        ma_results = []

    # 2) Run GPT-Researcher standard reports and deep reports (concurrently)
    print("  Generating 1 GPT-Researcher standard reports (concurrently) ...")
    gptr_task = asyncio.create_task(run_gpt_researcher_runs(query_prompt, num_runs=1, report_type="research_report"))

    print("  Generating 1 GPT-Researcher deep research reports (concurrently) ...")
    dr_task = asyncio.create_task(run_gpt_researcher_runs(query_prompt, num_runs=1, report_type="deep"))
    print("  Generating 1 FilePromptForge reports (concurrently) ...")
    # New FPF contract: pass instructions_file and current input markdown path
    fpf_task = asyncio.create_task(fpf_runner.run_filepromptforge_runs(instructions_file, md_file_path, num_runs=1))

    gptr_results, dr_results, fpf_results = await asyncio.gather(gptr_task, dr_task, fpf_task)

    print(f"  GPT-R standard generated: {len(gptr_results)}")
    print(f"  GPT-R deep generated: {len(dr_results)}")
    print(f"  FilePromptForge generated: {len(fpf_results)}")

    generated = {"ma": ma_results, "gptr": gptr_results, "dr": dr_results, "fpf": fpf_results}

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

    # Do not merge gpt-researcher defaults here.
    # process_markdown should not provide or inject gpt-researcher defaults;
    # gpt-researcher will load its own DEFAULT_CONFIG when instantiated.
    # Keep config as the pipeline-local YAML values only.

    if not config:
        print("Failed to load configuration. Exiting.")
        return

    # Start heartbeat for visible terminal activity
    hb_stop = pm_utils.start_heartbeat("process_markdown_noeval", interval=3.0)

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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(current_dir, "config.yaml")
    # Delegate orchestration to the centralized runner to avoid duplicated logic.
    try:
        import runner
    except Exception:
        # If running as a module, try package import
        from process_markdown import runner
    runner.run(cfg)
