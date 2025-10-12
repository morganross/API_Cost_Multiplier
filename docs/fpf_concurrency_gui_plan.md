# FPF Concurrency GUI Implementation Plan

## Objective
To add a new section to the GUI that allows users to configure FPF's concurrency settings (global max concurrency, per-provider max concurrency, QPS, and burst) and persist these settings to `api_cost_multiplier/FilePromptForge/fpf_config.yaml`.

## Current GUI Structure Overview
*   `api_cost_multiplier/GUI/gui.py`: Main launcher script.
*   `api_cost_multiplier/GUI/functions.py`: Contains the `MainWindow` class, which is the central logic for the GUI. It loads UI elements from `.ui` files and manages overall application flow.
*   `api_cost_multiplier/GUI/fpf_ui.py`: Defines the `FPF_UI_Handler` class, responsible for managing FPF-specific UI elements and interacting with `fpf_config.yaml`.
*   `api_cost_multiplier/GUI/main_window.ui`: Defines the main window layout, including placeholders for other `.ui` files.
*   `api_cost_multiplier/GUI/providers.ui`: Contains the group boxes for FPF, GPTR, DR, and MA model selections. This file is dynamically inserted into `MainWindow`'s `rightLayout`.

## Proposed Solution

The most logical and modular approach is to integrate the FPF concurrency settings directly into the `providers.ui` file, specifically within the `groupProvidersFPF` section, and manage its logic within the `FPF_UI_Handler` class.

### Step 1: Modify `providers.ui` (UI Design)

We will add new UI elements to `api_cost_multiplier/GUI/providers.ui` within the `<widget class="QGroupBox" name="groupProvidersFPF">` section. This will include:

*   **Global Concurrency Enabled Checkbox:** A `QCheckBox` to enable/disable concurrency for FPF.
    *   `objectName`: `checkFPFConcurrencyEnabled`
*   **Global Max Concurrency:** A `QSpinBox` or `QSlider` for `concurrency.max_concurrency`.
    *   `objectName`: `spinBoxFPFGlobalMaxConcurrency` (or `sliderFPFGlobalMaxConcurrency`)
    *   `minimum`: 1, `maximum`: 32 (or a reasonable upper limit)
*   **Per-Provider Concurrency Settings (for OpenAI, Google, OpenAIDP):** For each provider, we'll need:
    *   **Max Concurrency:** A `QSpinBox` or `QSlider` for `concurrency.per_provider.<provider>.max_concurrency`.
        *   `objectName`: `spinBoxFPF<Provider>MaxConcurrency` (e.g., `spinBoxFPFOpenAIMaxConcurrency`)
    *   **QPS (Queries Per Second):** A `QDoubleSpinBox` for `concurrency.per_provider.<provider>.rate_limit.qps`.
        *   `objectName`: `doubleSpinBoxFPF<Provider>QPS`
        *   `decimals`: 2, `singleStep`: 0.1
    *   **Burst:** A `QSpinBox` for `concurrency.per_provider.<provider>.rate_limit.burst`.
        *   `objectName`: `spinBoxFPF<Provider>Burst`

    These per-provider settings can be grouped within their own `QGroupBox` for better organization, or simply added as rows in a `QFormLayout` within the FPF section.

### Step 2: Update `FPF_UI_Handler` (`fpf_ui.py`)

The `FPF_UI_Handler` class will be extended to manage these new concurrency UI elements and their interaction with `fpf_config.yaml`.

1.  **`__init__(self, main_window)`:**
    *   Add new attributes to cache references to the concurrency UI widgets.
        ```python
        self.checkFPFConcurrencyEnabled: Optional[QtWidgets.QCheckBox] = main_window.findChild(QtWidgets.QCheckBox, "checkFPFConcurrencyEnabled")
        self.spinBoxFPFGlobalMaxConcurrency: Optional[QtWidgets.QSpinBox] = main_window.findChild(QtWidgets.QSpinBox, "spinBoxFPFGlobalMaxConcurrency")
        # ... similar for per-provider settings
        self.spinBoxFPFOpenAIMaxConcurrency: Optional[QtWidgets.QSpinBox] = main_window.findChild(QtWidgets.QSpinBox, "spinBoxFPFOpenAIMaxConcurrency")
        self.doubleSpinBoxFPFOpenAIQPS: Optional[QtWidgets.QDoubleSpinBox] = main_window.findChild(QtWidgets.QDoubleSpinBox, "doubleSpinBoxFPFOpenAIQPS")
        self.spinBoxFPFOpenAIBurst: Optional[QtWidgets.QSpinBox] = main_window.findChild(QtWidgets.QSpinBox, "spinBoxFPFOpenAIBurst")
        # ... for google and openaidp
        ```

2.  **`load_values(self)`:**
    *   Read the `concurrency` section from `self.fpf_yaml` and populate the new UI widgets.
        ```python
        fy = read_yaml(self.fpf_yaml)
        concurrency_cfg = fy.get("concurrency", {})

        if self.checkFPFConcurrencyEnabled:
            self.checkFPFConcurrencyEnabled.setChecked(concurrency_cfg.get("enabled", False))
        if self.spinBoxFPFGlobalMaxConcurrency:
            self.spinBoxFPFGlobalMaxConcurrency.setValue(concurrency_cfg.get("max_concurrency", 1))

        per_provider_cfg = concurrency_cfg.get("per_provider", {})
        # Example for OpenAI
        openai_cfg = per_provider_cfg.get("openai", {})
        if self.spinBoxFPFOpenAIMaxConcurrency:
            self.spinBoxFPFOpenAIMaxConcurrency.setValue(openai_cfg.get("max_concurrency", 1))
        if self.doubleSpinBoxFPFOpenAIQPS:
            self.doubleSpinBoxFPFOpenAIQPS.setValue(openai_cfg.get("rate_limit", {}).get("qps", 0.0))
        if self.spinBoxFPFOpenAIBurst:
            self.spinBoxFPFOpenAIBurst.setValue(openai_cfg.get("rate_limit", {}).get("burst", 0))
        # ... similar for google and openaidp
        ```

3.  **`gather_values(self)`:**
    *   Collect the values from the new concurrency UI widgets and structure them into a dictionary suitable for `fpf_config.yaml`.
        ```python
        concurrency_vals = {}
        if self.checkFPFConcurrencyEnabled:
            concurrency_vals["enabled"] = self.checkFPFConcurrencyEnabled.isChecked()
        if self.spinBoxFPFGlobalMaxConcurrency:
            concurrency_vals["max_concurrency"] = self.spinBoxFPFGlobalMaxConcurrency.value()

        per_provider_vals = {}
        # Example for OpenAI
        openai_provider_vals = {}
        if self.spinBoxFPFOpenAIMaxConcurrency:
            openai_provider_vals["max_concurrency"] = self.spinBoxFPFOpenAIMaxConcurrency.value()
        rate_limit_openai = {}
        if self.doubleSpinBoxFPFOpenAIQPS:
            rate_limit_openai["qps"] = self.doubleSpinBoxFPFOpenAIQPS.value()
        if self.spinBoxFPFOpenAIBurst:
            rate_limit_openai["burst"] = self.spinBoxFPFOpenAIBurst.value()
        if rate_limit_openai:
            openai_provider_vals["rate_limit"] = rate_limit_openai
        if openai_provider_vals:
            per_provider_vals["openai"] = openai_provider_vals
        # ... similar for google and openaidp
        if per_provider_vals:
            concurrency_vals["per_provider"] = per_provider_vals

        if concurrency_vals:
            vals.setdefault("concurrency", {}).update(concurrency_vals)
        ```

4.  **`write_configs(self, vals)`:**
    *   Update the `concurrency` section of `fpf_config.yaml` with the collected values.
        ```python
        fy = read_yaml(self.fpf_yaml)
        # Ensure concurrency section exists
        if "concurrency" not in fy or not isinstance(fy["concurrency"], dict):
            fy["concurrency"] = {}
        
        # Update concurrency settings
        if "concurrency" in vals:
            fy["concurrency"].update(vals["concurrency"])

        write_yaml(self.fpf_yaml, fy)
        # ... add logging for concurrency settings
        ```

5.  **Connect Signals:**
    *   Connect `valueChanged` (for spinboxes/sliders) or `toggled` (for checkboxes) of the new concurrency widgets to a method that triggers `MainWindow._compute_total_reports` if these settings impact the total number of reports. This might require adding a new signal in `FPF_UI_Handler` that `MainWindow` connects to.

### Step 3: Update `MainWindow` (`functions.py`)

*   No major changes are expected here, as `FPF_UI_Handler` will encapsulate the concurrency logic.
*   Ensure `_compute_total_reports` correctly reflects any changes in concurrency settings if they influence the total count. This might involve `FPF_UI_Handler` exposing a method to get its current concurrency state.

## Testing
*   Verify that the new UI elements appear correctly in the GUI.
*   Test loading existing `fpf_config.yaml` files with concurrency settings.
*   Test modifying concurrency settings in the GUI and verifying that `fpf_config.yaml` is updated correctly.
*   Run `generate.py` with various concurrency settings to ensure they are applied and function as expected.

## Open Questions / Considerations
*   What are the appropriate min/max values for `max_concurrency`, `qps`, and `burst` sliders/spinboxes? (Defaults will be used from `scheduler.py` if not set, but UI should guide user).
*   How should the UI handle providers that are not explicitly listed in `per_provider` in `fpf_config.yaml`? (Currently, `scheduler.py` uses `default_bucket` for these).
*   Should the concurrency settings be enabled/disabled globally, or per-provider? The current `fpf_config.yaml` has a global `enabled` flag under `concurrency`.

This plan provides a clear roadmap for integrating the concurrency settings into the FPF GUI.
