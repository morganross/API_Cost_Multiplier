"""
Processor: orchestrates processing of a single markdown file.

Depends on:
- process_markdown.functions.pm_utils
- process_markdown.functions.MA_runner
- process_markdown.functions.gptr_runner
- process_markdown.functions.output_manager
- process_markdown.EXAMPLE_fucntions.file_manager
- process_markdown.EXAMPLE_fucntions.gpt_researcher_client
"""

from __future__ import annotations

import os
import shutil
import asyncio

from process_markdown.functions import pm_utils, MA_runner, gptr_runner, output_manager
from process_markdown.EXAMPLE_fucntions import file_manager, gpt_researcher_client


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
    pm_utils.ensure_temp_dir(MA_runner.TEMP_BASE)

    # 1) Run 3 MA reports (sequentially per spec that MA reports come first)
    print("  Generating 3 Multi-Agent reports (MA) ...")
    try:
        ma_results = await MA_runner.run_multi_agent_runs(query_prompt, num_runs=3)
        print(f"  MA generated {len(ma_results)} report(s).")
    except Exception as e:
        print(f"  MA generation failed: {e}")
        ma_results = []

    # 2) Run 3 GPT-Researcher standard reports and 3 deep reports (concurrently)
    print("  Generating 3 GPT-Researcher standard reports (concurrently) ...")
    gptr_task = asyncio.create_task(gptr_runner.run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="research_report"))

    print("  Generating 3 GPT-Researcher deep research reports (concurrently) ...")
    dr_task = asyncio.create_task(gptr_runner.run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="deep"))

    gptr_results, dr_results = await asyncio.gather(gptr_task, dr_task)

    print(f"  GPT-R standard generated: {len(gptr_results)}")
    print(f"  GPT-R deep generated: {len(dr_results)}")

    generated = {"ma": ma_results, "gptr": gptr_results, "dr": dr_results}

    # Save outputs (copy into output folder using naming scheme)
    print("  Saving generated reports to output folder (mirroring input structure)...")
    saved_files = output_manager.save_generated_reports(md_file_path, input_folder, output_folder, generated)
    print(f"  Saved {len(saved_files)} report(s) to {os.path.dirname(saved_files[0]) if saved_files else output_folder}")

    # Cleanup: remove TEMP_BASE for this file run to avoid disk accumulation
    # (Note: if you prefer to keep temp artifacts, comment this out)
    try:
        # remove only directories created under TEMP_BASE
        if os.path.exists(MA_runner.TEMP_BASE):
            shutil.rmtree(MA_runner.TEMP_BASE)
    except Exception as e:
        print(f"  Warning: failed to cleanup temp dir {MA_runner.TEMP_BASE}: {e}")
