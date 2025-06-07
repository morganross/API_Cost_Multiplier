import os
import logging
import asyncio
import json
import re
import shutil
import pathlib
import urllib.parse
import subprocess
import tempfile
import argparse
import time
import websockets

# --- Configuration ---
# The base directory where markdown files to be processed are located.
INPUT_DIR = pathlib.Path("input_markdown_files") # Example: gptr-eval-process/input_markdown_files
# The path to a markdown file containing instructions that will be appended to each input markdown file's content.
INSTRUCTION_FILE = pathlib.Path("instructions.md") # Example: gptr-eval-process/instructions.md
# The WebSocket URL for the GPT-Researcher API.
GPT_RESEARCHER_API_URL = "ws://localhost:8000/ws"
# The base directory of the GPT-Researcher project, used to locate generated report files.
GPT_RESEARCHER_BASE_DIR = pathlib.Path("../gpt-researcher") # Relative to gptr-eval-process/process_markdown
# The directory where the processed and evaluated output files will be stored.
OUTPUT_BASE_DIR = pathlib.Path("../output_evaluated_reports") # Relative to gptr-eval-process/process_markdown

# The absolute path to the cli.py script of the doc_eval tool.
# This path needs to be correct relative to where the script is run, or absolute.
# Assuming doc_eval is cloned into gptr-eval-process/llm-doc-eval
DOC_EVAL_CLI_PATH = pathlib.Path("../llm-doc-eval/cli.py") # Relative to gptr-eval-process/process_markdown

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def get_research_report(query: str) -> str:
    """
    Connects to the GPT-Researcher API, sends a query, and retrieves the research report.
    """
    uri = GPT_RESEARCHER_API_URL
    logger.info(f"Connecting to GPT-Researcher API at {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Sending query to GPT-Researcher: {query[:100]}...")
            await websocket.send(json.dumps({"query": query}))

            report_data = ""
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if data["type"] == "report":
                    report_data = data["output"]
                    logger.info("Received final report from GPT-Researcher.")
                    break
                elif data["type"] == "logs":
                    logger.info(f"GPT-Researcher Log: {data['output']}")
                else:
                    logger.debug(f"Unhandled message type from GPT-Researcher: {data['type']}")
            return report_data
    except websockets.exceptions.ConnectionClosedOK:
        logger.warning("GPT-Researcher WebSocket connection closed gracefully.")
        return ""
    except Exception as e:
        logger.error(f"Error communicating with GPT-Researcher API: {e}")
        return ""

def run_doc_eval(input_dir: pathlib.Path, output_file: pathlib.Path):
    """
    Runs the doc_eval CLI tool on the generated reports.
    """
    logger.info(f"Running doc_eval on reports in: {input_dir}")
    logger.info(f"doc_eval CLI path: {DOC_EVAL_CLI_PATH.resolve()}")

    if not DOC_EVAL_CLI_PATH.exists():
        logger.error(f"doc_eval CLI script not found at: {DOC_EVAL_CLI_PATH.resolve()}")
        raise FileNotFoundError(f"doc_eval CLI script not found at {DOC_EVAL_CLI_PATH.resolve()}")

    # Ensure the output directory for doc_eval exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable, # Use the current Python interpreter
        str(DOC_EVAL_CLI_PATH),
        "evaluate",
        "--input_path", str(input_dir),
        "--output_path", str(output_file)
    ]
    
    logger.info(f"Executing doc_eval command: {' '.join(command)}")
    try:
        # Use subprocess.run for blocking execution and capturing output
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info(f"doc_eval stdout:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"doc_eval stderr:\n{result.stderr}")
        logger.info(f"doc_eval completed for {input_dir}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"doc_eval command failed with exit code {e.returncode}:\n{e.stdout}\n{e.stderr}")
        raise
    except FileNotFoundError:
        logger.error(f"Python interpreter or doc_eval script not found. Command: {command[0]} {command[1]}")
        raise

async def process_markdown_file(md_file_path: pathlib.Path, instructions: str):
    """
    Processes a single markdown file: generates a report using GPT-Researcher and evaluates it.
    """
    logger.info(f"Processing markdown file: {md_file_path.name}")

    try:
        md_content = md_file_path.read_text(encoding='utf-8')
        combined_query = f"{md_content}\n\n{instructions}"

        # Generate report using GPT-Researcher
        report_content = await get_research_report(combined_query)
        if not report_content:
            logger.error(f"Failed to generate report for {md_file_path.name}. Skipping evaluation.")
            return

        # Determine output path for the final evaluated report
        relative_path = md_file_path.relative_to(INPUT_DIR)
        output_dir_for_file = OUTPUT_BASE_DIR / relative_path.parent
        output_filename = f"{md_file_path.stem}_evaluated.md" # Or .json, depending on doc_eval output
        final_output_path = output_dir_for_file / output_filename

        # Create a temporary directory for doc_eval input
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            temp_report_path = temp_dir / f"{md_file_path.stem}_generated.md"
            temp_report_path.write_text(report_content, encoding='utf-8')
            logger.info(f"Generated report saved temporarily to: {temp_report_path}")

            # Run doc_eval on the temporary report
            # doc_eval typically outputs to a file or stdout, adjust as needed
            # For simplicity, let's assume doc_eval writes to a file in the temp_dir
            # and we'll copy that to final_output_path
            doc_eval_output_temp_path = temp_dir / "doc_eval_results.json" # Assuming JSON output
            run_doc_eval(temp_dir, doc_eval_output_temp_path)

            # Copy the doc_eval output to the final destination
            output_dir_for_file.mkdir(parents=True, exist_ok=True)
            if doc_eval_output_temp_path.exists():
                shutil.copy(doc_eval_output_temp_path, final_output_path)
                logger.info(f"Final evaluated report copied to: {final_output_path}")
            else:
                logger.error(f"doc_eval output file not found at {doc_eval_output_temp_path}. Skipping copy.")

    except Exception as e:
        logger.error(f"An error occurred while processing {md_file_path.name}: {e}")

async def main():
    # Resolve paths relative to the script's location
    script_dir = pathlib.Path(__file__).parent
    global INPUT_DIR, INSTRUCTION_FILE, GPT_RESEARCHER_BASE_DIR, OUTPUT_BASE_DIR, DOC_EVAL_CLI_PATH

    INPUT_DIR = (script_dir / INPUT_DIR).resolve()
    INSTRUCTION_FILE = (script_dir / INSTRUCTION_FILE).resolve()
    GPT_RESEARCHER_BASE_DIR = (script_dir / GPT_RESEARCHER_BASE_DIR).resolve()
    OUTPUT_BASE_DIR = (script_dir / OUTPUT_BASE_DIR).resolve()
    DOC_EVAL_CLI_PATH = (script_dir / DOC_EVAL_CLI_PATH).resolve()

    logger.info(f"Resolved INPUT_DIR: {INPUT_DIR}")
    logger.info(f"Resolved INSTRUCTION_FILE: {INSTRUCTION_FILE}")
    logger.info(f"Resolved GPT_RESEARCHER_BASE_DIR: {GPT_RESEARCHER_BASE_DIR}")
    logger.info(f"Resolved OUTPUT_BASE_DIR: {OUTPUT_BASE_DIR}")
    logger.info(f"Resolved DOC_EVAL_CLI_PATH: {DOC_EVAL_CLI_PATH}")

    # Ensure input directories exist
    if not INPUT_DIR.is_dir():
        logger.error(f"Input directory not found: {INPUT_DIR}")
        return
    if not INSTRUCTION_FILE.is_file():
        logger.error(f"Instruction file not found: {INSTRUCTION_FILE}")
        return

    instructions_content = INSTRUCTION_FILE.read_text(encoding='utf-8')
    logger.info("Instructions loaded successfully.")

    markdown_files = list(INPUT_DIR.rglob("*.md"))
    if not markdown_files:
        logger.info(f"No markdown files found in {INPUT_DIR}")
        return

    logger.info(f"Found {len(markdown_files)} markdown files to process.")

    for md_file in markdown_files:
        await process_markdown_file(md_file, instructions_content)

if __name__ == "__main__":
    asyncio.run(main())