# Combine & Revise Feature Implementation Plan (Standalone ACM)

## 1. Objective
Implement a robust "Combine & Revise" workflow entirely within the `api_cost_multiplier` (ACM) codebase, bypassing `gpt-researcher` internal agents. This feature acts as a "Post-Production" phase where the best generated reports are synthesized into a superior "Gold Standard" document.

## 2. Constraints & Principles
- **No GPT-Researcher Edits:** Do not modify any files inside the `gpt-researcher` directory.
- **No Patches:** Do not use monkey-patching.
- **Standalone Logic:** All logic must reside in `api_cost_multiplier` (e.g., `combiner.py`).
- **Tournament Style:** Combined reports must compete against their source reports in a re-evaluation loop.
- **Configurability:** The Combiner workflow is strictly optional. The system must function normally (Generation -> Eval) if the Combiner is disabled.
- **Output Strategy:**
    -   **Generation:** Produces multiple candidate reports (saved to run-specific folders/temp).
    -   **Combiner:** Produces "Challenger" reports.
    -   **Final Artifact:** The system should aim to identify and highlight the single "Gold Standard" report (the winner of the tournament).
    -   **Reporting:** `evaluate.py` must generate its standard CSV/HTML reports for *both* the initial run and the isolated "Playoffs" run.

## 3. Workflow Architecture

### Step 1: Initial Generation & Evaluation
- Run the standard generation batch (FPF, MA, GPT-R).
- Run `evaluate.py` to score all reports.
- **Selection:** Identify the **Top 2** highest-scoring reports based on the configured criteria.

### Step 2: Parallel Combination (Eval Subsystem + FPF)
- **Hierarchy:** The Combiner is a component of the Evaluation subsystem, which resides within ACM.
- **Mechanism:** The `combiner.py` module executes as part of the post-evaluation workflow.
- **Execution (FPF Calls):** Just as the Evaluation system uses FPF (FilePromptForge) calls to communicate with LLMs for scoring, the Combiner uses FPF calls to perform the text synthesis.
- **Models:** Use **two different** high-reasoning models (e.g., `gpt-4o` and `gemini-1.5-pro`) as specified in the GUI/Config.
- **Process:**
    - Create a prompt that includes:
        1.  The Master Instructions (`Eo instructions.md`).
        2.  Text of Report A.
        3.  Text of Report B.
        4.  Instruction to merge them into a single "Gold Standard" report, adhering strictly to the Master Structure and Rhetorical Intensity.
    - Execute this prompt in parallel against both selected models.
- **Output:** Two new "Challenger" reports (e.g., `Combined_ModelA.md`, `Combined_ModelB.md`).

### Step 3: The "Playoffs" (Re-Evaluation)
- **Pool:** Create a new evaluation pool containing:
    1.  The original Top 2 reports (the parents).
    2.  The 2 new Combined reports (the challengers).
- **Action:** Trigger a **new, separate instance** of `evaluate.py`.
- **Isolation:** This run must generate its own independent set of logs, reports (CSV/HTML), and output folder (e.g., `.../eval_reports/Run_TIMESTAMP_Combined`). It must **NOT** overwrite or merge with the original run's data.
- **Goal:** Verify if the combined versions actually outscore the originals in a clean, isolated environment.

## 4. Implementation Steps

### Phase 1: The Combiner Module (`combiner.py`)
- Create `c:\dev\silky\api_cost_multiplier\combiner.py`.
- **Role:** A submodule of the Evaluation system that utilizes FPF calls to synthesize reports.
- **Assets**:
    - Create `c:\dev\silky\api_cost_multiplier\prompts\combine_instructions.txt`.
    - **Content**:
        > "You are an expert editor and synthesizer of technical reports.
        > The following text contains:
        > 1. The original instructions used to generate the reports.
        > 2. Two distinct reports (Report A and Report B) generated based on those instructions.
        >
        > Your task is to create a single, superior 'Gold Standard' report by combining the best elements of both.
        > - STRICTLY follow the original instructions regarding structure, tone, and formatting.
        > - Synthesize the content: If one report covers a detail better, use it. If they conflict, use the more detailed or plausible one (or mention the nuance).
        > - Maintain the highest level of quality and rhetorical intensity requested in the original instructions.
        > - Do not output any meta-commentary. Output ONLY the final Markdown report."
- **Class `ReportCombiner`**:
    - `__init__(self, config)`: Load model settings.
    - `combine(self, report_paths: list, output_dir: str)`:
        - Load report contents.
        - Load `Eo instructions.md`.
        - Load `prompts/combine_instructions.txt`.
        - Construct the "Merge" prompt: `[Combine Instructions] + [Original Instructions] + [Report A] + [Report B]`.
        - **Execute FPF Call:** Invoke `generate_response` (from `generate.py`) to send this prompt to the configured models. This aligns with how Eval uses FPF for its operations.
        - Save the resulting markdown files.

### Phase 2: Orchestration (`runner.py`)
- Modify `runner.py` to add a post-evaluation hook.
- **Logic:**
    - After `trigger_evaluation_for_all_files` completes (and finishes writing its own reports/logs):
        - Parse the evaluation results (SQLite or JSON) from the *completed* run.
        - Find the Top 2 files.
        - Instantiate `ReportCombiner`.
        - Run the combination process to generate the "Challenger" files.
        - **Loop:** Call `evaluate.py` a second time.
            - **Crucial:** Pass a modified Run ID or Timestamp (e.g., `original_timestamp + "_COMBINED"`) to ensure `evaluate.py` creates a completely new folder structure for this tournament run.
            - Pass only the 4 files (2 Parents + 2 Challengers) as the target list.

### Phase 3: Configuration & GUI
- **`config.yaml`**: Add a `combine` section:
    ```yaml
    combine:
      enabled: true
      use_evaluated_file: true
      model_1:
        provider: "openai"
        model: "gpt-4o"
      model_2:
        provider: "google"
        model: "gemini-1.5-pro"
      tournament:
        pool_selection: "both" # or "revised_only"
        iterations: 1
    ```
- **GUI Mapping (`main_window.ui` -> `functions.py`)**:
    - **Main Group:** `groupBox` ("Combine and Revise") -> Maps to `combine.enabled`.
    - **Checkbox:** `checkBox` ("Use Evaluated File") -> Maps to `combine.use_evaluated_file`.
    - **Model 1:** `groupProvidersMA_2` ("Post-Eval Revise Model") -> Maps to `combine.model_1`.
        - `comboMAProvider_2` -> `combine.model_1.provider`
        - `comboMAModel_2` -> `combine.model_1.model`
    - **Model 2:** `groupProvidersMA_5` ("Additional Post-Eval Revise Model") -> Maps to `combine.model_2`.
        - `comboMAProvider_6` -> `combine.model_2.provider`
        - `comboMAModel_5` -> `combine.model_2.model`
    - **Tournament:** `groupProvidersMA_3` ("Secondary revision") -> Maps to `combine.tournament`.
        - `comboMAProvider_5` ("Inputs") -> `combine.tournament.pool_selection`
        - `sliderEvaluationIterations_5` -> `combine.tournament.iterations`

- **Action:** Update `functions.py` to:
    1.  Read these widgets in `gather_values()`.
    2.  Write them to the `combine` section of `config.yaml` in `write_configs()`.
    3.  Load them from `config.yaml` in `load_current_values()`.

## 5. File Structure
```text
api_cost_multiplier/
├── combiner.py          # NEW: Core logic for merging reports
├── prompts/
│   └── combine_instructions.txt # NEW: System prompt for the combiner
├── runner.py            # UPDATE: Trigger combination after eval
├── generate.py          # EXISTING: Used for LLM calls
└── config.yaml          # UPDATE: Add combine settings
```

## 6. Next Actions
1.  Create `combiner.py`.
2.  Update `runner.py` to read evaluation results and trigger the combiner.
3.  Verify GUI settings persistence.

## 7. Progress Log
- **[DATE] Phase 1 Complete:**
    - Created `prompts/combine_instructions.txt` with the system prompt.
    - Created `combiner.py` with the `ReportCombiner` class.
    - Implemented logic to load files, construct the prompt, and call `generate.generate_response`.
- **[DATE] Phase 2 Complete:**
    - Modified `runner.py` to import `ReportCombiner`.
    - Updated `trigger_evaluation_for_all_files` to capture the DB path from `evaluate.py` output.
    - Implemented the "Combine & Revise" trigger logic:
        - Checks `combine.enabled` config.
        - Retrieves Top 2 reports from DB.
        - Runs `combiner.combine`.
        - Triggers a secondary "Playoffs" evaluation with the combined files.
- **[DATE] Phase 3 Complete:**
    - Updated `config.yaml` with the new `combine` section structure.
    - Updated `GUI/functions.py`:
        - `gather_values`: Collects settings from the mapped GUI widgets.
        - `write_configs`: Persists the `combine` section to `config.yaml`.
        - `load_current_values`: Reads `config.yaml` and populates the GUI widgets.

## 8. Completion Status
**All phases are complete.** The "Combine & Revise" feature is fully implemented, integrated into the runner, and configurable via the GUI.
