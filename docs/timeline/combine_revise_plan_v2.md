# Combine & Revise Feature Implementation Plan (Standalone ACM)

## 1. Objective
Implement a robust "Combine & Revise" workflow entirely within the `api_cost_multiplier` (ACM) codebase, bypassing `gpt-researcher` internal agents. This feature acts as a "Post-Production" phase where the best generated reports are synthesized into a superior "Gold Standard" document.

## 2. Constraints & Principles
- **No GPT-Researcher Edits:** Do not modify any files inside the `gpt-researcher` directory.
- **No Patches:** Do not use monkey-patching.
- **Standalone Logic:** All logic must reside in `api_cost_multiplier` (e.g., `combiner.py`).
- **Tournament Style:** Combined reports must compete against their source reports in a re-evaluation loop.

## 3. Workflow Architecture

### Step 1: Initial Generation & Evaluation
- Run the standard generation batch (FPF, MA, GPT-R).
- Run `evaluate.py` to score all reports.
- **Selection:** Identify the **Top 2** highest-scoring reports based on the configured criteria.

### Step 2: Parallel Combination
- **Input:** The full Markdown text of the Top 2 reports.
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
- **Action:** Send this specific pool back to `evaluate.py`.
- **Goal:** Verify if the combined versions actually outscore the originals.

## 4. Implementation Steps

### Phase 1: The Combiner Module (`combiner.py`)
- Create `c:\dev\silky\api_cost_multiplier\combiner.py`.
- **Class `ReportCombiner`**:
    - `__init__(self, config)`: Load model settings.
    - `combine(self, report_paths: list, output_dir: str)`:
        - Load report contents.
        - Load `Eo instructions.md`.
        - Construct the "Merge" prompt.
        - Call `generate_response` (from `generate.py`) for each configured model.
        - Save the resulting markdown files.

### Phase 2: Orchestration (`runner.py`)
- Modify `runner.py` to add a post-evaluation hook.
- **Logic:**
    - After `trigger_evaluation_for_all_files` completes:
        - Parse the evaluation results (SQLite or JSON).
        - Find the Top 2 files.
        - Instantiate `ReportCombiner`.
        - Run the combination process.
        - **Loop:** Trigger `evaluate.py` again specifically for the new combined files + top 2 parents.

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
├── runner.py            # UPDATE: Trigger combination after eval
├── generate.py          # EXISTING: Used for LLM calls
└── config.yaml          # UPDATE: Add combine settings
```

## 6. Next Actions
1.  Create `combiner.py`.
2.  Update `runner.py` to read evaluation results and trigger the combiner.
3.  Verify GUI settings persistence.
