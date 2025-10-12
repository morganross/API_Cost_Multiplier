# FPF Concurrency GUI: Alternatives, Opinions, and Recommendation

This document reviews the existing plan for adding FPF concurrency controls to the GUI and proposes alternatives that better align with the guideline: “create new files for each GUI section; revise existing files only when necessary.”

## Summary of current plan (for reference)
- Add new concurrency widgets into `GUI/providers.ui` under `groupProvidersFPF`.
- Extend `GUI/fpf_ui.py (FPF_UI_Handler)` to load, gather, and write values to `FilePromptForge/fpf_config.yaml`.
- Minimal to no changes to `functions.py` / `MainWindow`.

While workable, this embeds concurrency controls into an already dense, multi-purpose UI file and increases coupling with `FPF_UI_Handler`. It also conflicts with the “new file per section” preference.

---

## Option A (Recommended): Standalone FPF Concurrency Panel (new UI + new handler)

Create a dedicated, isolated panel for concurrency settings with its own UI file and Python handler. Keep changes to existing files minimal and limited to wiring the new panel into the main window.

### Files to add
1) `api_cost_multiplier/GUI/fpf_concurrency.ui`
   - Independent Qt Designer file containing only concurrency controls.
   - Suggested structure:
     - Global Settings group:
       - “Enable Concurrency” (QCheckBox)
       - “Global Max Concurrency” (QSpinBox, 1..64)
     - Provider Settings group (dynamic or static sub-panels):
       - For each provider (e.g., `openai`, `google`, `openaidp`):
         - “Enable” (QCheckBox)
         - “Max Concurrency” (QSpinBox)
         - “QPS” (QDoubleSpinBox, step=0.1, decimals=2)
         - “Burst” (QSpinBox)
     - Buttons:
       - “Apply” (explicit write to config)
       - “Reset to Defaults”
     - Optional: “Effective Throughput Summary” label showing computed global vs provider QPS based on values.

2) `api_cost_multiplier/GUI/fpf_concurrency.py`
   - Class: `FPFConcurrencyPanel(QtWidgets.QWidget)`
   - Responsibilities:
     - Load `fpf_concurrency.ui`.
     - `load_values()` — read and populate from `FilePromptForge/fpf_config.yaml`.
     - `gather_values()` — collect current UI values into a `dict` shaped like:
       ```
       concurrency:
         enabled: bool
         max_concurrency: int
         per_provider:
           <provider>:
             enabled: bool (optional but useful for UX)
             max_concurrency: int
             rate_limit:
               qps: float
               burst: int
       ```
     - `apply()` — write partial update to YAML (see next file).
     - `reset_to_defaults()` — restore recommended defaults (e.g., `enabled: true`, `max_concurrency: 12`, provider defaults aligned with `scheduler.py`).

3) `api_cost_multiplier/GUI/concurrency_config.py`
   - Small utility module to encapsulate config I/O:
     - `read_fpf_yaml(path) -> dict`
     - `write_fpf_yaml(path, data: dict)`
     - `merge_concurrency(old: dict, new: dict) -> dict` (partial updates that only touch the `concurrency` subtree, preserving other keys)
   - Consider using a safe dumper; if comments must be preserved, note that PyYAML will drop them and recommend `ruamel.yaml` in a future enhancement.

### Minimal changes to existing files
- `api_cost_multiplier/GUI/functions.py` (MainWindow wiring only)
  - Instantiate and insert the new `FPFConcurrencyPanel` into the layout (e.g., a new tab or a new group on the right pane).
  - Connect panel signals to any global recomputation logic (e.g., `_compute_total_reports` if needed).
  - Avoid editing `providers.ui` and avoid expanding `fpf_ui.py` for concurrency.

- No changes required to `gui.py`.

### Dynamic provider support (recommended)
- Instead of hardcoding providers, discover them:
  - Option 1: From config keys under `concurrency.per_provider`.
  - Option 2: From `model_registry/providers/*.yaml` file names.
- Build per-provider sub-panels at runtime (or hide/show static rows if dynamic creation is complex).
- Benefits: adding a new provider later requires zero UI edits.

### Validation and UX
- Disable/enable child inputs based on the “Enable” checkbox (global and per-provider).
- Validate ranges:
  - `max_concurrency` >= 1
  - `qps` >= 0.0
  - `burst` >= 0
- Tooltips that explain:
  - “QPS” and “Burst” semantics (token-bucket model)
  - Interaction between global vs per-provider limits (global cap still applies).
- Optional: “Autosave” toggle; default to explicit “Apply” to avoid surprising writes.

### Pros
- Aligns with “new files per GUI section” policy.
- Minimizes coupling and risk to `providers.ui` and `fpf_ui.py`.
- Easier to iterate, test, and maintain in isolation.
- Scales to more providers without UI churn (with dynamic provider discovery).

### Cons
- Requires small wiring change in `functions.py`.
- Adds a small config helper module (but improves clarity and reuse).

---

## Option B: Schema-driven dynamic form (advanced, future-proof)
- Define a JSON Schema or a Pydantic model for the concurrency config subtree.
- Render form controls dynamically from the schema (generic “schema -> Qt form” mapper).
- Benefits:
  - Future changes to config structure require less UI work.
  - Can be reused for other config sections.
- Drawbacks:
  - More engineering effort up front.
  - Debugging dynamic forms can be harder for non-Qt experts.

---

## Option C: Concurrency Profiles (optional enhancement)
- Support named profiles in `fpf_config.yaml`, e.g.:
  ```
  concurrency_profiles:
    laptop_low:
      enabled: true
      max_concurrency: 4
      per_provider: { ... }
    workstation_high:
      enabled: true
      max_concurrency: 16
      per_provider: { ... }
  concurrency_profile_active: laptop_low
  ```
- GUI panel adds:
  - Profile selector (ComboBox)
  - “Save As New Profile”, “Delete Profile”, “Set Active”
- Benefits:
  - Rapid switching between environments.
- Drawbacks:
  - Requires changes in how runtime selects the active profile (minor update to loader).

---

## Option D: Read-only Preview inside Providers UI (not recommended)
- Add just a small “summary” into `providers.ui` and link to the new panel for edits.
- Benefit: Users see effective concurrency at a glance.
- Drawback: Still touches `providers.ui`, contrary to the guideline.

---

## Recommendation
Adopt Option A:
- New, self-contained `fpf_concurrency.ui` and `FPFConcurrencyPanel` (`fpf_concurrency.py`).
- New `concurrency_config.py` to encapsulate YAML I/O and merging logic.
- Only minimal wiring changes in `functions.py` (e.g., adding the panel to a layout or tab).
- Implement dynamic provider sub-panels by inspecting providers in config or registry.
- Provide explicit “Apply” and “Reset to Defaults” with clear tooltips and input validation.

Option C (Profiles) can be layered on later without impacting the basic panel.

---

## Proposed defaults (tunable)
- Global:
  - enabled: true
  - max_concurrency: 12
- Per-provider (example):
  - max_concurrency: 4
  - qps: 2.0
  - burst: 4

Ensure the panel reads current values and only writes what changed within `concurrency`.

---

## Implementation outline

1) Create `GUI/fpf_concurrency.ui` with groups as described.
2) Implement `GUI/concurrency_config.py`:
   - `read_fpf_yaml(path)`, `write_fpf_yaml(path, data)`, `merge_concurrency(old, new)`.
3) Implement `GUI/fpf_concurrency.py`:
   - Load UI, wire signals, implement `load_values()`, `gather_values()`, `apply()`, `reset_to_defaults()`.
   - Generate provider sub-panels dynamically (preferred) or via hidden static rows.
4) Modify `GUI/functions.py` minimally to mount the new panel and optionally connect a recompute signal.
5) Test matrix:
   - Load with no concurrency keys (panel shows defaults).
   - Load with partial per-provider keys (fallbacks applied).
   - Change values, click Apply, verify YAML diff only under `concurrency`.
   - Toggle enablement globally and per-provider; UI state updates correctly.
   - Runtime smoke test (`generate.py`) to assert values are consumed.

---

## Notes and pitfalls
- YAML comments are not preserved with standard PyYAML. If preservation is important, consider `ruamel.yaml` in a follow-up.
- If concurrency settings influence other computed GUI values (e.g., estimated report count), emit a signal on change and let `MainWindow` decide how to react.
- Keep provider keys consistent with runtime (e.g., `openai`, `google`, `openaidp`).
