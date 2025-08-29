import os
import sys
import asyncio
import shutil

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


async def process_file(md_file_path: str, config: dict, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
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

    # MA (optional)
    if run_ma:
        print("  Generating 3 Multi-Agent reports (MA) ...")
        try:
            ma_results = await MA_runner.run_multi_agent_runs(query_prompt, num_runs=num_runs)
            print(f"  MA generated {len(ma_results)} report(s).")
            generated["ma"] = ma_results
        except Exception as e:
            print(f"  MA generation failed: {e}")
            generated["ma"] = []

    # GPT-Researcher (always run) - run groups sequentially
    print("  Generating GPT-Researcher standard reports ...")
    gptr_results = await run_gpt_researcher_runs(query_prompt, num_runs=num_runs, report_type="research_report")
    print(f"  GPT-R standard generated: {len(gptr_results)}")

    print("  Generating GPT-Researcher deep research reports ...")
    dr_results = await run_gpt_researcher_runs(query_prompt, num_runs=num_runs, report_type="deep")
    print(f"  GPT-R deep generated: {len(dr_results)}")

    # FPF (optional)
    if run_fpf:
        print("  Generating FilePromptForge reports ...")
        fpf_results = await fpf_runner.run_filepromptforge_runs(query_prompt, num_runs=num_runs)
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

    markdown_files = file_manager.find_markdown_files(input_folder)
    print(f"Found {len(markdown_files)} markdown files in input folder.")

    if config.get('one_file_only', False) and markdown_files:
        markdown_files = [markdown_files[0]]

    for md in markdown_files:
        await process_file(md, config, run_ma=run_ma, run_fpf=run_fpf, num_runs=num_runs, keep_temp=keep_temp)

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
