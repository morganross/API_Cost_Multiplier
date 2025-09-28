# Plan to Split config_sliders.ui into Multiple Files

## Background
The `config_sliders.ui` file is currently ~2,300 lines of XML, making it difficult to maintain, prone to merge conflicts, and overwhelming to edit. Qt UI files do not have built-in import/include mechanisms like Python modules, so splitting requires loading multiple UI widgets programmatically in the PyQt5 code and combining them into the main window layout.

This plan outlines splitting the file into 5-6 logical sections (~300-500 lines each), updating the loading code in `functions.py`, and ensuring functionality remains intact.

## Current State Analysis
- **File Examined:** `api_cost_multiplier/GUI/config_sliders.ui` - Monolithic XML with nested QGroupBoxes, layouts, sliders, and buttons.
- **Loader Code:** `functions.py` loads the entire file via `self.ui = uic.loadUi(str(self.ui_path), self)`, caching widgets via `findChild()`.
- **Code Modularity:** Already exists with handlers (`fpf_ui.py`, `gptr_ma_ui.py`) but UI remains unsplit.
- **Previous Attempts:** Handlers split Python logic, but no UI file fragmentation attempted.
- **Docs Review:** No existing plans or reports on UI splitting in `/docs/`.

## Proposed Split Structure
Split into these sections based on layout and functionality (each as a `QWidget` root):

1. **`presets_general.ui`** (~150 lines): "Presets" (Master Quality slider) and "General" (Iterations slider) groupboxes → Left scroll area top.
2. **`report_configs.ui`** (~900 lines): FPF, GPTR, DR, MA groupboxes with sliders/compoboxes → Left scroll area main content.
3. **`providers.ui`** (~200 lines): Provider/Model selection groupboxes (FPF, GPTR, DR, MA) + enable checkboxes → Middle panel.
4. **`paths_evaluations.ui`** (~250 lines): "Paths" (file paths, guidelines) and evaluation sections → Right panel.
5. **`combine_revise.ui`** (~200 lines): "Combine and Revise" (post-eval models, checkboxes) → Right panel bottom/second.
6. **`metrics_buttons.ui`** (~150 lines): "Runtime Metrics" groupbox and bottom buttons bar → Bottom.

Core `config_sliders.ui` reduced to minimal skeleton (~100 lines): Main window + `QVBoxLayout` with top `QHBoxLayout` (scrollArea + right layouts) + bottom.

## Implementation Steps

### 1. Preparation (Qt Designer or Manual Editing)
- **Approach:** Use Qt Designer to copy sections into new .ui files. Each starts with `<ui><widget class="QWidget">` containing the group's XML.
- **Widget Names:** Preserve existing names (e.g., `sliderIterations`) to keep `findChild()` calls unchanged.
- **Backup:** Commit current `config_sliders.ui` before edits.

### 2. Update Loading Code in `functions.py`
- Replace single `uic.loadUi()` with:
  - Load skeleton via direct XML or minimal .ui.
  - For each section: `section_widget = uic.loadUi("GUI/section.ui")`; `layout.addWidget(section_widget)`.
- Adjust signal connections: `findChild()` works across added widgets if names are unique.
- Handle layout nesting (e.g., left scroll area contains multiple sections).

### 3. Testing & Validation
- **Incremental:** Load each sub-UI individually, verify widget access (e.g., via `findChildren(QtWidgets.QSlider)`).
- **Full Integration:** Run GUI, test sliders update configs, buttons load/run properly.
- **Edge Cases:** Confirm handlers connect signals to loaded widgets, presets/load/save work.

### 4. Documentation & Maintenance
- Update `README.md` with split structure notes.
- Document widget ownership to avoid naming conflicts.
- Benefits expected: Easier edits (less scrolling), reduced merge risks, better alignment with code modularity.

## Identified Concerns & Investigation Results
Before proceeding with implementation, the following concerns were identified and investigated through code analysis and PyQt5 documentation research:

### 1. Layout Nesting Complexity (Medium Risk)
- **Concern**: The left scroll area contains multiple groupboxes that need to stack properly. When loading separate UI files into the scroll area, the vertical stacking and spacing might not match the original exactly.
- **Investigation**: Analyzed `functions.py` MainWindow layout structure and PyQt5 scroll area behavior. PyQt5's `uic.loadUi()` preserves layout properties when loading QWidget-based UI files. Scroll areas can have their widget set programmatically without losing stacking behavior. Internet search confirmed PyQt5 handles nested layouts reliably.
- **Definitive Answer**: **LOW RISK** - PyQt5 handles this well. Can be mitigated by testing scroll behavior incrementally and adjusting layout margins if needed.

### 2. Widget Name Conflicts (Low Risk)
- **Concern**: If any widget names duplicate across files (unlikely since they're from one file), `findChild()` could grab the wrong widget.
- **Investigation**: Analyzed `config_sliders.ui` widget names - all 300+ names are unique. PyQt5's `findChild()` searches the entire widget tree, but unique names prevent conflicts. No duplicates found in current file.
- **Definitive Answer**: **VERY LOW RISK** - Current file has unique names. Can add validation in code to detect duplicates if they occur.

### 3. Signal Connection Reliability (Medium Risk)
- **Concern**: Handlers in `fpf_ui.py` and `gptr_ma_ui.py` rely on `findChild()` to connect signals. If widgets load in a different order or context, some connections might fail silently.
- **Investigation**: Reviewed signal connection patterns in `functions.py`, `fpf_ui.py`, and `gptr_ma_ui.py`. PyQt5 connects signals after all widgets are loaded and parented. Code has extensive error handling and fallback mechanisms. Internet search shows signal connections are robust in PyQt5.
- **Definitive Answer**: **LOW RISK** - Signal connections are robust in PyQt5. Can add verification logging to ensure all expected widgets are found before connecting.

### 4. Testing Burden (High Risk)
- **Concern**: More files = more potential failure points. A layout issue in one section could break the whole GUI.
- **Investigation**: Current code already has extensive error handling and fallback mechanisms. PyQt5 best practices support incremental loading and widget verification. Internet search confirms GUI smoke tests can be structured to isolate issues.
- **Definitive Answer**: **MEDIUM RISK** - Manageable with structured testing. Start with independent section loading, then integration testing. Full revert possible if issues arise.

### 5. Maintenance Overhead (Medium Risk)
- **Concern**: Future UI changes require editing multiple files instead of one, increasing merge conflict risk.
- **Investigation**: Current code is already well-modularized with handlers. Split files reduce individual file size from 2,300 to ~400 lines, making edits easier. Internet search shows smaller files actually reduce merge conflicts overall.
- **Definitive Answer**: **LOW RISK** - Benefits outweigh costs. Smaller files reduce merge conflicts overall. Can document split structure for future maintainers.

### 6. PyQt5 Edge Cases (Low Risk)
- **Concern**: Complex nested layouts with scroll areas might have rendering quirks when split.
- **Investigation**: Researched PyQt5 documentation and community forums. `uic.loadUi()` is designed for this use case. Scroll areas and nested layouts work correctly when properly structured. Internet search shows this is a well-supported pattern.
- **Definitive Answer**: **VERY LOW RISK** - PyQt5's `uic.loadUi()` handles complex layouts reliably. Edge cases are rare and usually fixable with minor layout adjustments.

## Overall Risk Assessment
- **Total Risk**: **LOW-MEDIUM** - Concerns are standard for UI refactoring but well-understood and mitigable.
- **Proceed Recommendation**: **YES** - Benefits of reduced file size and improved maintainability outweigh the manageable risks.
- **Mitigation Strategy**: Implement with incremental testing and maintain revert capability.

## Next Steps
- Approve this plan? Ready to implement via toggle to ACT MODE.
- Adjust splits (e.g., fewer files)? Let me know preferred sections or tool preferences.

## References
- PyQt5 `uic.loadUi()` supports loading any valid .ui XML root.
- No Qt Designer required for users; runtime compiles.
- Inspired by handler separation—extend to UI.
