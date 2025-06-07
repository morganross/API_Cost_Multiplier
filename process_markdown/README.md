# `process_markdown_files.py`

This script automates the processing of markdown files by integrating with the GPT-Researcher API for content generation and the `doc_eval` CLI tool for evaluation.

## Core Functionality

*   **Markdown Discovery**: Scans an input directory for `.md` files.
*   **GPT-Researcher Integration**: Sends combined markdown content and instructions to GPT-Researcher to generate reports.
*   **`doc_eval` Integration**: Evaluates the generated reports using the `doc_eval` CLI tool.
*   **Output Management**: Stores processed and evaluated reports in a structured output directory.

## Configuration

Key variables at the top of `process_markdown_files.py` control its behavior, including input/output directories and API/CLI paths.

## Usage

To run the script:

```bash
python process_markdown_files.py
```

Ensure GPT-Researcher API is running and `doc_eval` CLI is accessible.