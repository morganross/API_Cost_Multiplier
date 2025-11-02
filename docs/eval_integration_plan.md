# Plan: Integrate `evaluate.py` with ACM (`runner.py`)

## Objective
To modify the Automated Content Multiplier (ACM) system such that after `runner.py` finishes generating all reports for a single input file, it automatically triggers `evaluate.py` to perform an evaluation specifically on those newly generated reports. This requires `evaluate.py` to accept targeted input (either specific file paths or a temporary directory containing only the relevant reports for evaluation).

## Restatement of User Request
The goal is to enhance the Automated Content Multiplier (ACM) system so that its report generation process is seamlessly followed by an evaluation step. Currently, ACM's `runner.py` generates various reports for each input file. The user wants to modify this workflow so that immediately after ACM has completed generating all reports for a given input file, it automatically invokes the `evaluate.py` script. A key challenge is that `evaluate.py` typically processes all files within a designated directory. To achieve the desired integration, `runner.py` must be able to instruct `evaluate.py` to perform its evaluation specifically on the set of reports that were just generated for the single input file, rather than evaluating an entire directory. This implies a need for `evaluate.py` to accept specific file paths or a temporary directory containing only the relevant reports for evaluation.

## Proposed Plan:

**Phase 1: Enhance `api_cost_multiplier/evaluate.py` to accept targeted input.**

1.  **Add Command-Line Arguments**: Modify `evaluate.py` to accept an optional command-line argument, for example, `--target-files` which would take a list of file paths, or `--target-dir` to specify a directory containing only the files to be evaluated for that specific run.
2.  **Implement Conditional Logic**: Introduce logic within `evaluate.py`'s `main` function. If `--target-files` or `--target-dir` is provided, the script will use these specified inputs for evaluation. Otherwise, it will revert to its current behavior of scanning the default `api_cost_multiplier/test/mdoutputs` directory.
3.  **Refine Output Handling**: Ensure that when `evaluate.py` processes targeted files, its output (final reports and CSVs) is organized in a way that reflects this specific evaluation run, perhaps by creating a timestamped subdirectory within the configured `output_directory` and `export_directory`.

**Phase 2: Modify `api_cost_multiplier/runner.py` to trigger `evaluate.py` after report generation.**

1.  **Identify Trigger Point**: Locate the section in `runner.py` (likely within the `process_file` or `process_file_run` functions) where all reports for a single input markdown file have been generated and saved. This would be after the `save_generated_reports` call.
2.  **Collect Generated Report Paths**: After `save_generated_reports` is executed, capture the list of absolute paths to all reports that were just created for the current input file.
3.  **Invoke `evaluate.py` as a Subprocess**: Use Python's `subprocess` module (e.g., `subprocess.Popen` or `asyncio.create_subprocess_exec`) to run `evaluate.py` as a separate process. This will keep the main `runner.py` process clean and allow `evaluate.py` to run independently.
4.  **Pass Report Paths**: Pass the collected list of generated report paths to the `evaluate.py` subprocess using the new `--target-files` argument.
5.  **Add Configuration Flag**: Introduce a new boolean setting in `config.yaml` (e.g., `eval.auto_run: true/false`). `runner.py` will check this flag, and only invoke `evaluate.py` if `auto_run` is set to `true`.
6.  **Error Handling and Logging**: Implement appropriate error handling for the `evaluate.py` subprocess call within `runner.py`, and log its output or any errors to the ACM logger.

**Phase 3: Update `api_cost_multiplier/config.yaml`**

1.  Add the `auto_run` boolean flag under the `eval` section in `config.yaml` to enable or disable this automatic evaluation feature.
