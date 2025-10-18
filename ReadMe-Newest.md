# API Cost Multiplier (ACM) Project Overview

The `api_cost_multiplier` project acts as an orchestration layer for generating and evaluating AI-powered reports. It integrates various modules like GPT-Researcher, a Multi-Agent system, and FilePromptForge to produce diverse types of reports and then leverages `llm-doc-eval` for their subsequent evaluation. The system is highly configurable through YAML files, allowing for flexible definition of input sources, output destinations, and the specific models and providers to be used in report generation and evaluation.

## Key Components

*   **`generate.py`**: This is the primary script responsible for orchestrating the generation of reports. It reads markdown input files, retrieves instructions, and then dispatches generation tasks to Multi-Agent, GPT-Researcher (standard and deep research), and FilePromptForge. It then saves the generated reports to a structured output directory. Configuration for `generate.py` is primarily driven by `config.yaml`.
*   **`evaluate.py`**: This script handles the evaluation of generated reports. It utilizes the `llm-doc-eval` module to perform single or pairwise evaluations of reports, stores results in an SQLite database, and can identify the "best" report through an Elo-rating system. It also exports evaluation results to CSV files.
*   **`config.yaml`**: The main configuration file for the `api_cost_multiplier` project. It defines:
    *   `input_folder`: Directory containing source markdown files for generation.
    *   `output_folder`: Directory where generated reports will be saved.
    *   `instructions_file`: Path to a file containing instructions used during report generation.
    *   `one_file_only`: Boolean to process only the first discovered markdown file.
    *   `iterations_default`: Default number of iterations for runs.
    *   `runs`: A list of model configurations specifying the `type` (fpf, dr, ma, gptr), `provider`, and `model` to use for report generation.
    *   `guidelines_file`: Path to a file with guidelines for report generation.
*   **`presets.yaml`**: This file defines various named presets (e.g., `low`, `8`, `888`) that specify detailed operational parameters. These include:
    *   `iterations_default`, `input_folder`, `output_folder`, `instructions_file`.
    *   FPF-specific settings (`grounding.max_results`, `google.max_tokens`, `reasoning.effort`, `web_search.search_context_size`).
    *   Token limits for various model types (`FAST_TOKEN_LIMIT`, `SMART_TOKEN_LIMIT`, `STRATEGIC_TOKEN_LIMIT`).
    *   Search parameters (`MAX_SEARCH_RESULTS_PER_QUERY`).
    *   Deep Research parameters (`DEEP_RESEARCH_BREADTH`, `DEEP_RESEARCH_DEPTH`).
    *   Multi-Agent parameters (`max_sections`).
    *   `enable` flags to toggle fpf, gptr, dr, ma, and evaluation components.
    *   Specific `runs` configurations similar to `config.yaml` but tailored per preset.
*   **`functions/` directory**: Contains utility modules used by `generate.py` and `evaluate.py`, including `pm_utils` (for utilities), `MA_runner` (for Multi-Agent execution), `fpf_runner` (for FilePromptForge execution), `config_parser`, `file_manager`, and `gpt_researcher_client`.
*   **`llm-doc-eval/`**: A sub-project (or module within) responsible for the core evaluation logic, imported and used by `evaluate.py`.
*   **`gpt-researcher/`**: A sub-project (or module within) integrated for generating research reports, used by `generate.py`.
*   **`FilePromptForge/`**: (Inferred) A sub-project or module handling the FilePromptForge specific logic, used by `generate.py` via `fpf_runner`.

## Getting Started and Usage

To use the `api_cost_multiplier` project, you typically interact with `generate.py` for report creation and `evaluate.py` for performance assessment.

### Report Generation (`generate.py`)

This script processes markdown files from a specified input directory, applies instructions, and generates various types of reports using configured LLMs.

**Basic Usage:**

The `generate.py` script is designed to be run as a standalone Python script. It automatically loads its `config.yaml` from its own directory.

```bash
python generate.py
```

**Configuration via `config.yaml`**:
Modify `api_cost_multiplier/config.yaml` to define:
*   `input_folder`: Path to your markdown input files.
*   `output_folder`: Where generated reports will be stored.
*   `instructions_file`: The file containing prompts or instructions for report generation.
*   `runs`: Specify different models and report types (e.g., `fpf`, `gptr`, `dr`, `ma`) to generate.

**Example `config.yaml` snippet:**
```yaml
input_folder: C:\dev\silky\api_cost_multiplier\test\mdinputs
output_folder: C:\dev\silky\api_cost_multiplier\test\mdoutputs
instructions_file: C:\dev\invade\firstpub-Platform\docs\Lit Summery\instructions\FPF Deep Research One-Shot.md
runs:
  - type: fpf
    provider: google
    model: gemini-2.5-flash
  - type: dr
    provider: openai
    model: gpt-5
```

### Report Evaluation (`evaluate.py`)

This script assesses the quality of generated reports using the `llm-doc-eval` framework. It supports different evaluation modes and can determine a "best" report.

**Basic Usage:**

```bash
python evaluate.py
```

The script will look for candidate files in `api_cost_multiplier/test/mdoutputs` by default, or the first subfolder if no files are found directly. Evaluation results are saved to an SQLite database and exported to CSVs (`gptr-eval-process/exports`).

**Configuration:**
The `evaluate.py` script itself does not heavily rely on `config.yaml` in the same way `generate.py` does for specifying runs, but the underlying `llm-doc-eval` component might use its own `config.yaml` (as mentioned in the old README for `llm-doc-eval/config.yaml`). The evaluation `mode` (single, pairwise) is currently hardcoded to "config" which implies it looks for a config setting within `llm_doc_eval`, which is outside `acm`'s `config.yaml`.

## Audience-Specific Information

### For Developers

*   **Extending Functionality**: The `generate.py` script is modular, leveraging `functions/pm_utils`, `functions/MA_runner`, and `functions/fpf_runner`. To add new report generation types or integrate new LLM providers, modify these runner modules or extend `generate.py` to call new functions.
*   **Report Handling**: `save_generated_reports` in `generate.py` dictates how reports are named and stored. Customizing this function allows for different output formats or metadata inclusion.
*   **Configuration Parsing**: `config_parser.py` handles loading YAML configurations. Ensure any new configuration options are properly integrated there.
*   **Asynchronous Operations**: Both `generate.py` and `evaluate.py` use `asyncio` for concurrent operations (e.g., running multiple research tasks). Be mindful of `async`/`await` patterns when modifying or adding new asynchronous tasks.
*   **GPT-Researcher Integration**: `gpt_researcher_client.py` provides the interface to GPT-Researcher.
*   **`FilePromptForge` Integration**: `fpf_runner.py` manages the execution of FilePromptForge tasks.

### For Users / Researchers

*   **Input Data**: Place your source markdown files in the directory specified by `input_folder` in `config.yaml`.
*   **Instructions**: Provide clear and concise instructions/prompts in the file specified by `instructions_file` in `config.yaml`.
*   **Output Review**: Check the `output_folder` (from `config.yaml`) for generated reports. After running `evaluate.py`, look in `gptr-eval-process/exports` for CSV summaries of evaluation results, and `gptr-eval-process/final_reports` for the identified best report.
*   **Preset Management**: Utilize `presets.yaml` to define and select different operational profiles, which can be useful for comparing model performance under varying constraints.

### For Operators / Administrators

*   **Dependency Management**: All project dependencies are managed in a central `requirements.txt` file (as per the old README). Ensure this is kept up-to-date and installed in the environment.
*   **Temporary Files**: The system uses a `TEMP_BASE` directory for temporary files. By default, `generate.py` attempts to clean these up after each file run. If temporary artifacts need to be retained for debugging, this cleanup step can be commented out.
*   **Path Configuration**: Pay close attention to absolute and relative paths specified in `config.yaml` (`input_folder`, `output_folder`, `instructions_file`, `guidelines_file`) and `presets.yaml`. Ensure these paths are accessible and correctly configured for the operating environment.
*   **Database Management**: `evaluate.py` creates a unique SQLite database (`results_TIMESTAMP.sqlite`) per run. These databases are stored alongside the `llm-doc-eval` module's `DB_PATH`. Manage these files for long-term storage or analysis of evaluation history.

## Argument Flags (CLI)

The `generate.py` and `evaluate.py` scripts primarily rely on their respective configuration files (`config.yaml`, `presets.yaml`) for defining their behavior rather than direct command-line arguments.

*   `generate.py`: Executes by simply running `python generate.py`. All operational parameters are derived from the `config.yaml` file located in the same directory.
*   `evaluate.py`: Executes by simply running `python evaluate.py`. It uses a default evaluation folder (`api_cost_multiplier/test/mdoutputs`) and internally configured paths for its SQLite database and CSV exports.

**Note**: For more granular control or programmatic invocation, you would typically modify the `config.yaml` or directly interact with the underlying functions and classes within the `functions/` directory or the `llm_doc_eval.api` module. It appears `runner.py` is intended for a centralized orchestration, which takes a config file as an argument, suggesting that `api_cost_multiplier` is often run as part of a larger pipeline.
