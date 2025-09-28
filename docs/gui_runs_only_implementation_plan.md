# Make the GUI match the new ACM “runs” setup

Goal
- Switch the GUI to use checkboxes for picking models instead of dropdowns.
- Only show models that are actually supported.
- When the user clicks “Write” or “Run”, the GUI writes everything to `config.yaml` inside a `runs` list.
- The GUI should stop editing the tool files directly (no more writing to `default.py`, `fpf_config.yaml`, or `task.json`). The runner will handle those.

What the new screen looks like
- There is a section for each report type: FPF, GPTR, DR, MA.
- Inside each section, there is a simple list of checkboxes.
- Each checkbox is one “provider:model”, like `openai:gpt-4.1` or `google:gemini-2.5-flash`.
- The user can check as many boxes as they want.
- Keep the “iterations_default” slider (how many times to repeat each run).

Where the model lists come from
- FPF:
  - We already know how to find FPF providers and their models by reading each provider’s Python file in `FilePromptForge/providers/*/fpf_{name}_main.py` and using `ALLOWED_MODELS`.
- GPTR and DR:
  - Read from `model_registry/providers/*.yaml` (like `openai.yaml`, `google.yaml`, `openrouter.yaml`, `anthropic.yaml`).
  - Build a list of `provider:model` strings per report type (for GPTR and DR, they usually share the same LLM list).
- MA:
  - Use the same provider YAMLs. MA needs a `model` in `runs`. We’ll still show the label as `provider:model` so it’s clear where it comes from, but for MA we only save the `model` field in `runs`.

What we will save to `config.yaml`
- We write a `runs` list, one item per checked box:
  - For GPTR: `{ type: "gptr", provider: "<prov>", model: "<model>" }`
  - For DR: `{ type: "dr", provider: "<prov>", model: "<model>" }`
  - For FPF: `{ type: "fpf", provider: "<prov>", model: "<model>" }`
  - For MA: `{ type: "ma", model: "<model>" }`
- We also write `iterations_default` (the slider value).
- We do not write provider/model into the tool files anymore. The runner will temporarily patch them per run and then restore them.

What we remove
- The four “Additional Model” boxes and their dropdowns.
- The old per-type `iterations` map in `config.yaml`. We only keep `iterations_default`.
- The code that wrote:
  - GPTR provider:model to `gpt-researcher/.../default.py`
  - FPF provider/model to `FilePromptForge/fpf_config.yaml`
  - MA model to `gpt-researcher/multi_agents/task.json`
- The old “Total Reports” math that counted 8 groupboxes (4 base + 4 extra). The new total is simpler.

New “Total Reports” label
- Count how many model checkboxes are selected across all types.
- Multiply by `iterations_default`.
- Show that number.

Step-by-step changes (code)

1) Make a simple “Model Catalog” helper
- New module (for example `GUI/model_catalog.py`).
- It loads models for GPTR/DR/MA from `model_registry/providers/*.yaml`.
- It reuses current FPF discovery to read `ALLOWED_MODELS` for each FPF provider.
- It returns a dictionary like:
  ```
  {
    "gptr": ["openai:gpt-4.1", "google:gemini-2.5-flash", ...],
    "dr":   ["openai:gpt-4.1", "google:gemini-2.5-flash", ...],
    "fpf":  ["google:gemini-2.5-flash", ...],
    "ma":   ["openai:gpt-4.1", "google:gemini-2.5-flash", ...]
  }
  ```

2) Replace dropdowns with checkboxes
- For each report type, build a scrollable list of `QCheckBox` items in the UI (or in code).
- Each checkbox text is the `provider:model` string (for MA, we still label them this way even though we only save the `model` value).
- Remove the four “Additional Model” groupboxes from the UI.

3) Gather values (when the user clicks Write or Run)
- Look at which checkboxes are checked in each section.
- Build the `runs` list as described above.
- Read the `iterations_default` slider value.

4) Write `config.yaml` (in `functions.py` write path)
- Write:
  - `iterations_default`
  - `runs: [ {type, provider?, model}, ... ]`
- Do not write any provider/model values to the tool config files.

5) Remove old code paths
- Delete the code that:
  - Creates and writes `additional_models`.
  - Maintains `y["iterations"]` per type.
  - Writes provider/model to:
    - `default.py` (GPTR)
    - `fpf_config.yaml` (FPF)
    - `task.json` (MA)
- Update “Total Reports” to use: `iterations_default * (number of checked model boxes)`.

6) Optional: load old settings gracefully
- If `config.yaml` has a `runs` list, pre-check those boxes.
- If the old `additional_models` exists, you can convert it to pre-checked boxes one time (optional).
- If tool files still have models set from the past, we can ignore them now since the runner will patch per run.

7) Testing checklist
- Case A: Pick 2 GPTR models and 1 FPF model. Set `iterations_default=2`.
  - Expect: `runs` has 3 entries. “Total Reports” shows 6.
  - Run `generate.py` and confirm outputs for each run and each iteration.
- Case B: MA-only. Pick 1 MA model, `iterations_default=1`.
  - Expect: `runs` has 1 entry. Outputs generated for MA.
- Case C: No selections.
  - Expect: `runs` is empty, “Total Reports” shows 0, no crash.

Benefits
- Easier to understand: “Pick your models. Click Run.”
- Fewer lines of code: we delete the old “baseline + additional models” system.
- The GUI and runner use the same `runs` list, so there’s less confusion.
- No more messing with tool config files directly; runner handles that safely each time.

Notes for developers
- Keep the existing split UI files where helpful (like `providers.ui`, `report_configs.ui`). Just swap dropdowns for checkboxes.
- `gptr_ma_ui.py` and `fpf_ui.py` should stop writing provider/model to their tool configs. Keep only sliders and other non-model settings if still useful.
- `functions.py` should build `runs` from the checked boxes and write it to `config.yaml`.
- The runner (`runner.py`) already supports `runs` as the source of truth.

---

## Technical Plan (Detailed)

This section is an in-depth engineering plan describing all code changes, exact file touch-points, reused logic, and how the new GUI will align with the ACM runner’s runs-only workflow.

### 1) Architecture overview

- Source of truth:
  - ACM runner expects `config.yaml` with:
    - `iterations_default: <int>`
    - `runs: [ { type: "gptr"|"dr"|"fpf"|"ma", provider?: "<name>", model: "<id>" }, ... ]`
  - Legacy keys (like `additional_models`, per-type `iterations`) must be considered deprecated by the GUI writer.

- GUI responsibilities:
  - Present per-type model choices as checkboxes (no dropdowns).
  - Persist only `iterations_default` and `runs[]` in `api_cost_multiplier/config.yaml`.
  - Do not mutate tool configs (no writes to `default.py`, `fpf_config.yaml`, `task.json`).
  - Optional: read legacy inputs to pre-check choices, but don’t persist them back as legacy formats.

- Runner responsibilities (unchanged):
  - For each run entry, patch the corresponding tool config on disk, execute a run, then restore files (already implemented in `runner.py`).

### 2) Files to modify and expected changes

- `api_cost_multiplier/GUI/functions.py`
  - load_current_values:
    - New: read `config.yaml` and parse `runs[]`. For each run entry, pre-check matching checkbox in the appropriate section.
    - Remove/ignore: old logic that reads/sets per-type `iterations` and `additional_models`.
    - Keep: reading `iterations_default`.
  - gather_values:
    - Replace: Instead of building `additional_models`, scan checkboxes across FPF, GPTR, DR, MA sections and build `runs[]`.
    - Remove: building `providers` dict and merging provider fields (these no longer persist to `config.yaml`).
  - write_configs:
    - Write only:
      - `iterations_default`
      - `runs` (complete list from checked boxes)
    - Remove:
      - Writing `additional_models`
      - Writing per-type `iterations` map
    - Delegate: still call handler `write_configs(vals)` but ensure handlers do not write provider/model into their own tool-specific files (see handler changes).

  - Total Reports calculation (`_compute_total_reports`):
    - Replace logic: count all checked model checkboxes across the four sections and multiply by `iterations_default`.
    - Remove counting of groupAdditionalModel[1..4] and baseline (type) groupboxes as report counts.

- `api_cost_multiplier/GUI/gptr_ma_ui.py`
  - Load:
    - Optional: keep reading sliders for non-model settings if you want to keep those controls (e.g., token limits, temperature) as UI-only (no longer persisted to tool files).
    - Remove preloading provider/model into combos (we will no longer have those combos; we’ll have checkboxes).
  - gather_values:
    - Provide only non-model values you still want in GUI state (UI-only) and enables (if still used for show/hide).
    - Do not build or mirror providers/models in `vals["providers"]`.
  - write_configs:
    - Remove writing provider/model to `default.py` (remove SMART_LLM/STRATEGIC_LLM/FAST_LLM edits).
    - Remove writing MA model to `task.json`.
    - If you choose to keep non-model sliders, either:
      - Do not write them at all (UI-only), or
      - Persist them to a future ACM key (e.g., `tool_overrides` in `config.yaml`) if/when runner supports it.
    - For now: simplest is no write for non-model fields (documented as not persisted).

- `api_cost_multiplier/GUI/fpf_ui.py`
  - Load:
    - Keep `_discover_fpf_providers()` and `_load_allowed_models()` for model listing (reused logic).
    - Stop preselecting/reading provider/model from `fpf_config.yaml` since we won’t use that file as a source of truth.
  - gather_values:
    - Return only enables or non-model UI-only values.
  - write_configs:
    - Remove writing provider/model (and other values) into `fpf_config.yaml`.

- `api_cost_multiplier/GUI/config_sliders.ui` (+ split panels)
  - Remove widgets (and related labels):
    - groupAdditionalModel
    - groupAdditionalModel2
    - groupAdditionalModel3
    - groupAdditionalModel4
    - comboAdditionalType, comboAdditionalType2, comboAdditionalType3, comboAdditionalType4
    - comboAdditionalProvider, comboAdditionalProvider2, comboAdditionalProvider3, comboAdditionalProvider4
    - comboAdditionalModel, comboAdditionalModel2, comboAdditionalModel3, comboAdditionalModel4
  - Remove any old provider/model dropdowns for each type (GPTR/DR/MA/FPF).
  - Add per-type container(s) for checkbox lists, e.g.:
    - For each of: fpf, gptr, dr, ma
      - QScrollArea with content widget and a QVBoxLayout named like:
        - layoutFPFModels
        - layoutGPTRModels
        - layoutDRModels
        - layoutMAModels
  - Keep:
    - `sliderIterations_2` (mapped to `iterations_default`)
    - Label `label_2` (Total Reports), but recalc method will change

- `api_cost_multiplier/GUI/main_window.ui` and split UIs
  - Ensure placeholders/containers exist in the left panel to host the new checkbox lists (or create at runtime).

### 3) New module: Model Catalog

- New file: `api_cost_multiplier/GUI/model_catalog.py`
- Responsibilities:
  - Load models for GPTR/DR/MA from provider registry YAMLs:
    - Path: `api_cost_multiplier/model_registry/providers/*.yaml`
    - For each provider YAML (e.g., `openai.yaml`), build a list of models:
      - Return as `provider:model` strings for GPTR and DR
      - For MA, we still present as `provider:model` labels but only save `model` later
  - Load FPF models by reusing existing logic:
    - Reuse `FPF_UI_Handler._discover_fpf_providers()` to map provider -> module
    - Reuse `FPF_UI_Handler._load_allowed_models(module_path)` to get `ALLOWED_MODELS`
    - Return `provider:model` strings for FPF
  - API:
    ```
    def load_all() -> dict[str, list[str]]:
        return {
          "gptr": [...],  # provider:model strings
          "dr":   [...],
          "fpf":  [...],
          "ma":   [...],
        }
    ```
  - Error handling:
    - On YAML or provider module load errors, log warnings and return partial lists (don’t crash the GUI).

### 4) Building and wiring the checkboxes

- In `MainWindow.__init__` (functions.py):
  - After UI load, call a helper to build and insert checkbox lists:
    - `self._build_model_checklists()`:
      - Calls `model_catalog.load_all()`
      - For each type key (fpf/gptr/dr/ma), inject `QCheckBox` into the matching container layout (e.g., `layoutGPTRModels`).
      - Set objectName for each checkbox as:
        - `check_{type}_{provider}_{model}` (safe characters, replace non-alnum with `_`).
  - Signal wiring:
    - Each checkbox’s `toggled(bool)` connects to `_compute_total_reports` to update totals live.

- Pre-check from `config.yaml`:
  - In `load_current_values()`, after reading `config.yaml`:
    - For each entry in `runs`:
      - Map to checkbox name and set `setChecked(True)`
    - Make this tolerant to missing models (e.g., models not present in current catalog).

### 5) Translating checkboxes to runs[]

- In `gather_values()` (functions.py):
  - Pseudocode:
    ```
    vals = {}
    vals["iterations_default"] = int(self.sliderIterations_2.value())
    runs = []
    for type_key in ("fpf", "gptr", "dr", "ma"):
        for each checkbox in that section:
            if checkbox.isChecked():
                prov, model = parse_provider_model(checkbox.text())
                if type_key == "ma":
                    runs.append({"type":"ma", "model": model})
                else:
                    runs.append({"type": type_key, "provider": prov, "model": model})
    vals["runs"] = runs
    return vals
    ```
  - Do NOT collect `providers`, `additional_models`, or per-type enables for execution.
  - Only iterations_default and runs matter to the runner.

### 6) Writing config.yaml

- In `write_configs()` (functions.py):
  - Use `read_yaml` to load existing YAML, then overwrite keys:
    - `y["iterations_default"] = vals["iterations_default"]`
    - `y["runs"] = vals["runs"]`
  - Remove keys if present:
    - `y.pop("additional_models", None)`
    - `y.pop("iterations", None)`
  - `write_yaml(self.pm_config_yaml, y)`
  - Do not write any tool-specific configs.

### 7) Removing legacy logic

- In `functions.py`:
  - Remove blocks that:
    - Load `additional_models` into additional slots
    - Build `additional_models` in gather_values
    - Persist `additional_models` in write_configs
    - Derive/maintain `y["iterations"]`
  - Update `_compute_total_reports()` to use checkbox counts × `iterations_default`.

- In `gptr_ma_ui.py`:
  - Remove writing of:
    - SMART_LLM/STRATEGIC_LLM/FAST_LLM into `default.py`
    - MA `task.json` model
  - Optional: keep non-model slider reads/writes as UI-only (no persistence), or remove them if not needed.

- In `fpf_ui.py`:
  - Remove writing provider/model and other values to `fpf_config.yaml`.
  - Keep provider discovery (`_discover_fpf_providers`) and model loading (`_load_allowed_models`) for building the catalog.

- In `.ui` files:
  - Delete additional model widgets and old provider/model combos.
  - Add containers for dynamic checkboxes.

### 8) Reused logic inventory (exact references)

- Provider/Model discovery:
  - `api_cost_multiplier/GUI/fpf_ui.py`
    - `_discover_fpf_providers(self) -> Dict[str, str]`
    - `_load_allowed_models(self, module_path: str)`
  - `api_cost_multiplier/model_registry/providers/*.yaml`
    - Use `gui_utils.read_yaml` to parse and list models per provider.
- File IO and utilities:
  - `api_cost_multiplier/GUI/gui_utils.py`
    - `read_yaml`, `write_yaml`, `read_json`, `write_json`, `read_text`, `write_text`
    - `show_error`, `show_info`
    - `clamp_int`, `temp_from_slider` (if keeping non-model sliders)
- UI framework & threading:
  - `RunnerThread`, `DownloadThread` stay as-is (no changes required).
- Runner alignment:
  - `api_cost_multiplier/runner.py` already implements runs-only execution with patch/restore of tool files.

### 9) Migration notes

- On load:
  - If `runs` exists: pre-check matching boxes.
  - If only `additional_models` exists (legacy):
    - Optionally convert to checked boxes in memory (do not rewrite `additional_models`).
  - Ignore values persisted in tool configs for model selection (runner will set them per run).

### 10) Testing plan (technical)

- Unit-ish UI tests:
  - Build catalog returns lists for all four types (non-empty where expected).
  - Checkbox builder creates correct number of boxes with expected labels.
  - Pre-check logic checks boxes that match `config.yaml.runs`.
- Writer tests:
  - After selecting N boxes and setting iterations_default, write_configs produces:
    ```
    iterations_default: X
    runs:
      - { type: "...", provider?: "...", model: "..." }
      ...
    ```
  - Ensures no `additional_models` or per-type `iterations` keys exist post-write.
- End-to-end:
  - Select models across GPTR/DR/FPF/MA, run `generate.py`, verify outputs are produced by runner for each run × iterations_default.
  - Verify that `default.py`, `fpf_config.yaml`, and `task.json` are restored after runs.

### 11) Performance and UX considerations

- Catalog load is lightweight (YAML parsing + optional module import per FPF provider).
- Checkbox lists can be long; use scroll areas with lazy population if necessary.
- Show a small count badge or live number next to each type to indicate selections per section.
- Total Reports updates live on any checkbox toggle or iterations slider change.

### 12) Backward compatibility

- Reading legacy `additional_models` only for pre-check (optional), never writing it back.
- If users have old presets that include providers/models, apply them to pre-check boxes where possible.

### 13) Rollout steps

1) Implement `model_catalog.py`.
2) Add checkbox containers to UI (or build them programmatically if easier).
3) Implement checkbox builder, pre-check on load, and total reports math.
4) Replace gather/write logic in `functions.py` to output only `runs` and `iterations_default`.
5) Remove legacy code and tool-file writes in handlers.
6) QA: unit checks + end-to-end runs.
7) Document the new behavior in `GUI/README.md`.

### 14) Future enhancements (optional)

- Add quick filters (by provider) above checkbox lists.
- Add “Select All for this provider” buttons.
- Group reasoning models (if needed) under a separate header per provider.

This plan centralizes execution truth in `config.yaml.runs` and simplifies the GUI to choose models directly, while preserving and reusing the robust discovery logic already in place for FPF and provider YAMLs.
