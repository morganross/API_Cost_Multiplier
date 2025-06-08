# Plan for `process-markdown` script

## 1. Goal:
The primary goal is to automate the process of generating research reports using `gpt-researcher` and evaluating them with `llm-doc-eval`, then saving the best report. This script will act as an orchestrator, handling file management, external tool execution, and result processing.

## 2. Core Functionality Breakdown:

*   **Configuration Loading:** Read and parse configuration details (input directory, output directory, instructions file path) from `process-markdown/config.md`.
*   **File Discovery & Filtering:** Recursively scan the specified input directory for Markdown (`.md`) files. For each found file, determine if a corresponding processed output already exists in the output directory to avoid redundant processing.
*   **GPT-Researcher Integration:** For new or updated Markdown files, combine their content with a predefined instruction set to form a query. Execute `gpt-researcher` via its command-line interface (CLI) with this query. This process will be repeated three times concurrently to generate multiple reports.
*   **LLM-Doc-Eval Integration:** Take the three generated reports from `gpt-researcher` and pass them to `llm-doc-eval` via its CLI for evaluation. Extract the path to the "best" report based on `llm-doc-eval`'s output.
*   **Output Management:** Write the selected "best" report to the designated output directory, ensuring the original input file's directory structure is mirrored.

## 3. Module and File Structure:

To maintain modularity and readability, the `process-markdown` script will be structured into several Python files within the `process-markdown/` directory:

*   [`process-markdown/process_markdown.py`](process-markdown/process_markdown.py): The main entry point of the script. It will orchestrate the calls to other modules.
*   [`process-markdown/config_parser.py`](process-markdown/config_parser.py): Handles reading and parsing the `config.md` file.
*   [`process-markdown/file_manager.py`](process-markdown/file_manager.py): Contains functions for file system operations like listing Markdown files, checking for existing outputs, and creating output directories.
*   [`process-markdown/gpt_researcher_client.py`](process-markdown/gpt_researcher_client.py): Encapsulates the logic for interacting with the `gpt-researcher` CLI, including query formatting and output parsing.
*   [`process-markdown/llm_doc_eval_client.py`](process-markdown/llm_doc_eval_client.py): Manages interactions with the `llm-doc-eval` CLI, including passing reports for evaluation and extracting the best result.
*   [`process-markdown/utils.py`](process-markdown/utils.py): A utility file for common helper functions, such as handling concurrent execution.

## 4. Detailed Steps & Implementation Notes:

*   **Step 1: Initial Project Setup**
    *   Ensure the `process-markdown/` directory contains `process_markdown.py` and `config.md`.
    *   Create the new Python files: `config_parser.py`, `file_manager.py`, `gpt_researcher_client.py`, `llm_doc_eval_client.py`, and `utils.py`.

*   **Step 2: Refine `config.md` and Implement `config_parser.py`**
    *   **`config.md`**: Update its content to a more easily parsable format, e.g., simple key-value pairs or YAML. For example:
        ```
        input_folder: ./test/mdinputs
        output_folder: ./test/mdoutputs
        instructions_file: ./instructions.md
        ```
    *   **`config_parser.py`**: Implement a function to read `config.md` and return a dictionary or object containing `input_folder`, `output_folder`, and `instructions_file`. Use Python's built-in file reading and string parsing, or a YAML parser if `config.md` is converted to `config.yaml`.

*   **Step 3: Implement `file_manager.py`**
    *   `find_markdown_files(input_dir)`: Use `os.walk` to recursively find all `.md` files within `input_dir`. Return a list of absolute paths.
    *   `get_output_path(input_file_path, input_base_dir, output_base_dir)`: A helper function to construct the corresponding output file path, maintaining the relative directory structure.
    *   `output_exists(output_file_path)`: Check if a file exists at `output_file_path` using `os.path.exists`.
    *   `create_output_dirs(output_file_path)`: Create necessary parent directories for `output_file_path` using `os.makedirs(..., exist_ok=True)`.

*   **Step 4: Implement `gpt_researcher_client.py`**
    *   `generate_query_prompt(markdown_content, instructions_content)`: Concatenate the two string inputs.
    *   `run_gpt_researcher(query_prompt)`:
        *   Use `subprocess.run` to execute the `gpt-researcher` CLI command. The exact command will need to be determined from the `gpt-researcher` documentation (e.g., `python -m gpt_researcher.cli "<query>" --report_type research_report`).
        *   Capture `stdout` and `stderr`. Parse the output to extract the path to the generated report file. Error handling for non-zero exit codes.
    *   `run_concurrent_research(query_prompt, num_runs=3)`:
        *   Use `asyncio.gather` with `functools.partial` and `loop.run_in_executor` (or `concurrent.futures.ThreadPoolExecutor`) to run `run_gpt_researcher` three times concurrently.
        *   Return a list of paths to the three generated reports.

*   **Step 5: Implement `llm_doc_eval_client.py`**
    *   `evaluate_reports(report_paths)`:
        *   Use `subprocess.run` to execute the `llm-doc-eval` CLI command. The command will likely be `python -m llm_doc_eval.cli run-pairwise <report_path_1> <report_path_2> ...`.
        *   Capture `stdout` and `stderr`. Parse the output to identify the path to the "best" report. This might involve looking for specific keywords or patterns in the output.

*   **Step 6: Implement `process_markdown.py` (Main Orchestration)**
    *   Load configuration using `config_parser.py`.
    *   Iterate through Markdown files found by `file_manager.py`.
    *   For each file:
        *   Check if output exists. If so, continue.
        *   Read input Markdown and instructions.
        *   Call `gpt_researcher_client.run_concurrent_research`.
        *   Call `llm_doc_eval_client.evaluate_reports` with the results.
        *   Call `file_manager.create_output_dirs` and then copy the best report to the final destination.

## 5. Dependencies:

*   Standard Python libraries: `os`, `subprocess`, `asyncio`, `shutil`.
*   Potentially `PyYAML` if `config.md` is converted to `config.yaml`.
*   The `gpt-researcher` and `llm-doc-eval` tools must be installed and accessible via their CLI commands in the environment where this script runs.

## 6. Workflow Diagram:

```mermaid
graph TD
    A[Start process_markdown.py] --> B{Load Configuration};
    B --> C[Parse config.md];
    C --> D[Get input_folder, output_folder, instructions_file];
    D --> E{Find all .md files in input_folder};
    E -- For each input .md file --> F{Check if corresponding output exists};
    F -- Yes --> G[Skip file];
    F -- No --> H[Read input .md content];
    H --> I[Read instructions file content];
    I --> J[Generate query prompt];
    J --> K{Run GPT-Researcher CLI (3 times concurrently)};
    K -- 3 Report Paths --> L{Run LLM-Doc-Eval CLI};
    L -- Best Report Path --> M[Create output directories];
    M --> N[Write best report to output_folder];
    N --> O[Process next file or End];
    O --> P[End];