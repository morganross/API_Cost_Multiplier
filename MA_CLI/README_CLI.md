# Multi-Agent CLI Command Line Arguments

This document describes the command-line arguments available for the Multi-Agent CLI executable (`Multi_Agent_CLI.exe`).

## Usage

```bash
Multi_Agent_CLI.exe [options] [--query <research_query>]
```

or

```bash
Multi_Agent_CLI.exe [options] --query-file <query_file_path>
```

## Arguments

*   `--query <research_query>`: The research query. This is optional if a task configuration file or query file is provided.
*   `--task-config <task_file_path>`: Path to a task configuration JSON file. This file can define the query, output formats, guidelines, and other settings.
*   `--query-file <query_file_path>`: Path to a file containing the research query. The content of this file will be used as the query.
*   `--guidelines-file <guidelines_file_path>`: Path to a file containing the research guidelines. Each line in the file will be treated as a separate guideline.
*   `--output-folder <folder_path>`: Set the output folder for the generated reports. Defaults to `outputs`.
*   `--output-filename <filename>`: Set the base filename for the output reports. Defaults to `multi_agent_report_<uuid>`. The appropriate file extension (`.md`, `.pdf`, `.docx`) will be added based on the publish formats.
*   `--max-sections <number>`: Set the maximum number of sections in the research report.
*   `--publish-markdown`: Enable markdown output.
*   `--no-publish-markdown`: Disable markdown output.
*   `--publish-pdf`: Enable PDF output.
*   `--no-publish-pdf`: Disable PDF output.
*   `--publish-docx`: Enable DOCX output.
*   `--no-publish-docx`: Disable DOCX output.
*   `--include-human-feedback`: Enable human feedback during the research process.
*   `--no-include-human-feedback`: Disable human feedback.
*   `--follow-guidelines`: Enable following the provided guidelines.
*   `--no-follow-guidelines`: Disable following guidelines.
*   `--model <model_name>`: Set the language model to use for the research. Defaults to `gpt-4o`.
*   `--guidelines <guideline1> <guideline2> ...`: Set guidelines directly as command-line arguments. Multiple guidelines can be provided separated by spaces. If guidelines contain spaces, they should be enclosed in quotes.
*   `--verbose`: Enable verbose output for more detailed logging.
*   `--no-verbose`: Disable verbose output.
*   `--openai-api-key <key>`: Set the OpenAI API key. Overrides the `OPENAI_API_KEY` environment variable.
*   `--tavily-api-key <key>`: Set the Tavily API key. Overrides the `TAVILY_API_KEY` environment variable.

## Handling Multiple Queries

This CLI tool now supports providing multiple research queries and query files on the command line. The values from `--query` arguments and the content from files specified by `--query-file` arguments will be concatenated in the order they appear on the command line to form a single research query.

If neither `--query` nor `--query-file` are used, the query specified in the task configuration (e.g., `task.json`) will be used.

**Examples:**

*   **Concatenating multiple command-line queries:**
    ```bash
    python Multi_Agent_CLI.py --query "First part of the query" --query "second part of the query"
    ```
    Resulting query: "First part of the query second part of the query"

*   **Concatenating queries from multiple files:**
    Assume `file1.md` contains "query from file 1" and `file2.md` contains "query from file 2".
    ```bash
    python Multi_Agent_CLI.py --query-file file1.md --query-file file2.md
    ```
    Resulting query: "query from file 1 query from file 2"

*   **Concatenating queries from command line and files:**
    Assume `file1.md` contains "query from file 1".
    ```bash
    python Multi_Agent_CLI.py --query "command line part" --query-file file1.md --query "another command line part"
    ```
    Resulting query: "command line part query from file 1 another command line part"


## Examples

Run a research with a query and enable verbose output:

```bash
Multi_Agent_CLI.exe --query "Latest advancements in AI" --verbose
```

Run a research using a task configuration file and publish only to PDF:

```bash
Multi_Agent_CLI.exe --task-config ./config/my_task.json --no-publish-markdown --publish-pdf --no-publish-docx
```

Run a research with guidelines provided directly:

```bash
Multi_Agent_CLI.exe --query "Impact of climate change on coastal cities" --follow-guidelines --guidelines "Focus on economic impacts" "Include case studies"