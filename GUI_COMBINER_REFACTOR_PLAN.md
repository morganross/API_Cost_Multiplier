# GUI Combiner Refactor Plan

## 1. Current State Analysis

### 1.1. Existing Implementation
The current "Combine & Revise" functionality in the GUI is implemented as a placeholder within `GUI/functions.py`. It suffers from several critical issues:
*   **Hardcoded Widget Names:** The code references auto-generated names like `comboMAProvider_2`, `comboMAModel_5`, and `groupProvidersMA_3`, making the code brittle and hard to read.
*   **No Dynamic Population:** The comboboxes for selecting models (Model 1 and Model 2) are **never populated**. They are empty or contain static placeholder data, rendering the feature unusable.
*   **Monolithic Logic:** The logic for loading and saving these settings is buried inside the massive `load_current_values` and `gather_values` methods in `functions.py`.

### 1.2. Widget Mapping (Inferred from `functions.py`)
Based on the existing code, the following widgets correspond to the "Combine & Revise" features:
*   **Master Enable:** `groupBox` (QGroupBox, checkable) - Controls the entire section.
*   **Use Evaluated File:** `checkBox` (QCheckBox) - Toggle for `use_evaluated_file`.
*   **Model 1 Provider:** `comboMAProvider_2` (QComboBox)
*   **Model 1 Model:** `comboMAModel_2` (QComboBox)
*   **Model 2 Provider:** `comboMAProvider_6` (QComboBox)
*   **Model 2 Model:** `comboMAModel_5` (QComboBox)
*   **Tournament Pool:** `comboMAProvider_5` (QComboBox) - Selects "Both" or "Revised Only".
*   **Tournament Iterations:** `sliderEvaluationIterations_5` (QSlider)

### 1.3. Configuration Schema (`config.yaml`)
The target configuration structure is:
```yaml
combine:
  enabled: boolean
  use_evaluated_file: boolean
  model_1:
    provider: string
    model: string
  model_2:
    provider: string
    model: string
  tournament:
    pool_selection: "both" | "revised_only"
    iterations: integer
```

---

## 2. Detailed Refactor Plan

### 2.1. Create `GUI/combine_ui.py`
We will create a dedicated handler class `Combine_UI_Handler` to encapsulate all logic for this section.

**Class Structure:**
```python
class Combine_UI_Handler:
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = main_window
        # Widget references will be stored here
        self.chk_enable = None
        self.combo_prov_1 = None
        # ... etc

    def setup_ui(self):
        """Finds widgets by name and connects signals."""
        # Map the hardcoded names to semantic variables
        self.chk_enable = self.ui.findChild(QtWidgets.QGroupBox, "groupBox")
        # ... map all other widgets ...
        
        # Connect provider combos to update model combos
        self.combo_prov_1.currentIndexChanged.connect(self._update_model_1_list)
        self.combo_prov_2.currentIndexChanged.connect(self._update_model_2_list)

    def populate_models(self):
        """
        1. Calls model_catalog.discover_fpf_models(self.main_window.pm_dir).
        2. Parses 'provider:model' strings into a dict: {provider: [models]}.
        3. Populates provider comboboxes.
        4. Triggers initial model population.
        """

    def load_config(self, full_config: dict):
        """Reads the 'combine' section and sets widget states."""

    def gather_values(self) -> dict:
        """Returns the 'combine' dictionary for config.yaml."""
```

### 2.2. Update `GUI/functions.py`
We will surgically remove the old logic and inject the new handler.

**Steps:**
1.  **Import:** `from .combine_ui import Combine_UI_Handler`
2.  **Init:** In `MainWindow.__init__`:
    ```python
    self.combine_handler = Combine_UI_Handler(self)
    self.combine_handler.setup_ui()
    self.combine_handler.populate_models()
    ```
3.  **Load:** In `load_current_values`:
    *   **DELETE** lines ~786-836 (the old manual loading logic).
    *   **ADD** `self.combine_handler.load_config(y)`
4.  **Save:** In `gather_values`:
    *   **DELETE** lines ~990-1040 (the old manual gathering logic).
    *   **ADD** `vals["combine"] = self.combine_handler.gather_values()`

### 2.3. Dynamic Model Population Logic
The `populate_models` method will use `GUI/model_catalog.py`:
1.  `raw_list = model_catalog.discover_fpf_models(pm_dir)` returns `['openai:gpt-4o', 'google:gemini-1.5-pro', ...]`.
2.  The handler must parse this list to group models by provider.
3.  `comboProv1` and `comboProv2` are filled with the sorted keys (providers).
4.  When a provider is selected, the corresponding `comboMod` is cleared and filled with that provider's models.

---

## 3. Loop Prevention Strategy (The "One-Pass" Rule)

To prevent infinite recursion (Eval -> Combine -> Eval -> Combine...), the system must enforce a strict limit.

### 3.1. Logic Flow
1.  **Initial Run:** `generate.py` produces reports.
2.  **Eval 1:** `evaluate.py` runs.
    *   If `combine.enabled` is True:
    *   It identifies Top 2 winners.
    *   It calls `combiner.py`.
3.  **Combine:** `combiner.py` generates a synthesized report.
4.  **Eval 2 (Playoffs):** `evaluate.py` runs on the combined report + original winners.
    *   **CRITICAL:** This run must know it is a "Playoff" run.
    *   It must **NOT** trigger `combiner.py` again.

### 3.2. Implementation Detail
*   **Flag:** We will use a flag `is_playoff=True` (or `depth=1`) when calling the secondary evaluation.
*   **Runner Integration:** In `runner.py`, when triggering the post-combine evaluation:
    ```python
    # Pseudo-code
    if not is_playoff:
        # ... logic to trigger combine ...
        trigger_combine(...)
    else:
        # We are already in a playoff, just pick a winner and stop.
        finalize_winner(...)
    ```
*   **Config Safety:** The `combine.enabled` setting in `config.yaml` is the *user's preference*. The runtime logic must override this during the playoff phase to prevent the loop.

---

## 4. Validation Checklist
1.  **UI Initialization:** Launch GUI. Verify "Combine & Revise" section exists.
2.  **Dropdowns:** Verify `Model 1` and `Model 2` dropdowns are populated with FPF models (e.g., `openai`, `google`).
3.  **Interactivity:** Change Provider -> Verify Model list updates.
4.  **Persistence:**
    *   Select specific models (e.g., `google:gemini-1.5-pro`).
    *   Click "Write to Configs".
    *   Check `config.yaml`: Verify `combine` section reflects choices.
    *   Restart GUI: Verify choices are reloaded.
5.  **Execution:** (Future step) Verify `runner.py` respects the "One-Pass" rule during an actual run.

## Progress Update (2025-11-23)

### Completed Actions
1.  **Created `GUI/combine_ui.py`:**
    *   Implemented `Combine_UI_Handler` class.
    *   Mapped all widgets to their semantic names.
    *   Implemented `populate_models` using `model_catalog.discover_fpf_models`.
    *   Implemented `load_config` and `gather_values` for seamless config integration.
    *   Added dynamic signal connections for provider->model updates.

2.  **Updated `GUI/functions.py`:**
    *   Imported `Combine_UI_Handler`.
    *   Instantiated the handler in `MainWindow.__init__`.
    *   Replaced the monolithic loading logic in `load_current_values` with `self.combine_handler.load_config(y)`.
    *   Replaced the monolithic gathering logic in `gather_values` with `vals["combine"] = self.combine_handler.gather_values()`.

### Next Steps
1.  **Validation:** Launch the GUI and verify that the "Combine & Revise" section is populated with actual FPF models and that settings persist correctly.
2.  **Runner Integration:** Implement the "One-Pass" rule in `runner.py` to prevent infinite loops during the Combine phase.
