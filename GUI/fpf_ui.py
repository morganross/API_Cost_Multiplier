from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5 import QtWidgets, uic

from .gui_utils import (
    clamp_int, temp_from_slider, read_yaml, read_json, read_text, write_yaml,
    show_error, show_info, _open_in_file_explorer
)

from ..model_registry.provider_model_selector import discover_providers, extract_models_from_yaml


class FPF_UI_Handler:
    def __init__(self, main_window: QtWidgets.QMainWindow):
        self.main_window = main_window
        
        # Paths
        self.fpf_yaml = self.main_window.pm_dir / "FilePromptForge" / "default_config.yaml"

        # Cache widgets
        self.sliderGroundingMaxResults: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderGroundingMaxResults")
        self.sliderGoogleMaxTokens: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderGoogleMaxTokens")
        
        self.groupProvidersFPF: Optional[QtWidgets.QGroupBox] = main_window.findChild(QtWidgets.QGroupBox, "groupProvidersFPF")

        # Provider/Model comboboxes (programmatically populated from model_registry/providers/*.yaml)
        self.comboFPFProvider: Optional[QtWidgets.QComboBox] = main_window.findChild(QtWidgets.QComboBox, "comboFPFProvider")
        self.comboFPFModel: Optional[QtWidgets.QComboBox] = main_window.findChild(QtWidgets.QComboBox, "comboFPFModel")
        # Fallback: uic.loadUi sometimes sets widgets as attributes on the main window.
        # If findChild didn't locate them, try attribute lookup.
        try:
            if not self.comboFPFProvider and hasattr(main_window, "comboFPFProvider"):
                self.comboFPFProvider = getattr(main_window, "comboFPFProvider")
        except Exception:
            pass
        try:
            if not self.comboFPFModel and hasattr(main_window, "comboFPFModel"):
                self.comboFPFModel = getattr(main_window, "comboFPFModel")
        except Exception:
            pass

        # Diagnostic: list all QComboBox object names visible from the main window at this point.
        try:
            names = [cb.objectName() for cb in main_window.findChildren(QtWidgets.QComboBox)]
            print(f"[DEBUG][FPF_UI] comboboxes on main_window during init ({len(names)}): {names}", flush=True)
        except Exception:
            pass

        # Discover provider YAMLs and populate provider combobox (do not persist selections here)
        try:
            providers_dir = str(self.main_window.pm_dir / "model_registry" / "providers")
            self._provider_to_path = discover_providers(providers_dir)
            providers = sorted(self._provider_to_path.keys())

            # Debug: log discovery and widget presence
            try:
                print(f"[DEBUG][FPF_UI] providers_dir={providers_dir}", flush=True)
                print(f"[DEBUG][FPF_UI] discovered providers={providers}", flush=True)
                print(f"[DEBUG][FPF_UI] comboFPFProvider found={bool(self.comboFPFProvider)}", flush=True)
                print(f"[DEBUG][FPF_UI] comboFPFModel found={bool(self.comboFPFModel)}", flush=True)
            except Exception:
                pass

            if self.comboFPFProvider:
                try:
                    self.comboFPFProvider.clear()
                except Exception:
                    pass
                if providers:
                    try:
                        self.comboFPFProvider.addItems(providers)
                    except Exception as e:
                        print(f"[WARN][FPF_UI] Failed to add items to comboFPFProvider: {e}", flush=True)
                    # wire selection changes to update model list
                    try:
                        self.comboFPFProvider.currentTextChanged.connect(self._on_provider_changed)
                    except Exception as e:
                        print(f"[WARN][FPF_UI] Failed to connect comboFPFProvider signal: {e}", flush=True)
            # Initialize the model list for the first provider if present
            if providers:
                try:
                    # If provider combo exists, prefer setting current text to first provider to trigger population
                    if self.comboFPFProvider and providers:
                        try:
                            # Block signals while setting initial index to avoid premature callbacks
                            prev = self.comboFPFProvider.blockSignals(True)
                            self.comboFPFProvider.setCurrentIndex(0)
                            self.comboFPFProvider.blockSignals(prev)
                        except Exception:
                            pass
                        # Call population explicitly
                        self._on_provider_changed(providers[0])
                    else:
                        self._on_provider_changed(providers[0])
                except Exception as e:
                    print(f"[WARN][FPF_UI] Initial model population failed: {e}", flush=True)
        except Exception as e:
            # Non-fatal: log and continue
            print(f"[WARN] Failed to initialize FPF provider/model combos: {e}", flush=True)

    def connect_signals(self):
        """Connect UI signals to handler methods."""
        # Bottom toolbar button connections
        try:
            btn = self.main_window.findChild(QtWidgets.QPushButton, "btnAction2")  # Open FPF Config (file)
            if btn:
                btn.clicked.connect(self.on_open_fpf_config)
        except Exception:
            pass
        
        # Connect groupbox toggles
        if self.groupProvidersFPF:
            self.groupProvidersFPF.toggled.connect(lambda v, k="fpf": self._on_groupbox_toggled(k, v))

        # Schedule a late populate after the event loop starts to ensure widgets are realized.
        try:
            from PyQt5 import QtCore
            QtCore.QTimer.singleShot(0, self._late_populate)
        except Exception:
            # If QTimer import fails for any reason, attempt immediate populate as fallback.
            try:
                self._late_populate()
            except Exception:
                pass

    def _late_populate(self) -> None:
        """
        Late initialization that runs after the main event loop starts.
        This re-finds combobox widgets (in case they weren't available earlier)
        and populates the provider/model lists.
        """
        try:
            # Re-find comboboxes in case they were not available during __init__
            if not self.comboFPFProvider:
                try:
                    self.comboFPFProvider = self.main_window.findChild(QtWidgets.QComboBox, "comboFPFProvider")
                except Exception:
                    self.comboFPFProvider = None
            if not self.comboFPFModel:
                try:
                    self.comboFPFModel = self.main_window.findChild(QtWidgets.QComboBox, "comboFPFModel")
                except Exception:
                    self.comboFPFModel = None

            # Additional fallback: scan all comboboxes attached to main_window and match by objectName
            try:
                if not self.comboFPFProvider or not self.comboFPFModel:
                    all_cbs = self.main_window.findChildren(QtWidgets.QComboBox)
                    names = [cb.objectName() for cb in all_cbs]
                    print(f"[DEBUG][FPF_UI][_late_populate] all combobox names: {names}", flush=True)
                    if not self.comboFPFProvider:
                        for cb in all_cbs:
                            if cb.objectName() == "comboFPFProvider":
                                self.comboFPFProvider = cb
                                break
                    if not self.comboFPFModel:
                        for cb in all_cbs:
                            if cb.objectName() == "comboFPFModel":
                                self.comboFPFModel = cb
                                break
            except Exception:
                pass

            # Debug state
            try:
                print(f"[DEBUG][FPF_UI][_late_populate] comboFPFProvider={bool(self.comboFPFProvider)}, comboFPFModel={bool(self.comboFPFModel)}", flush=True)
            except Exception:
                pass

            if not self.comboFPFProvider or not self.comboFPFModel:
                return

            # Discover providers and populate
            try:
                providers_dir = str(self.main_window.pm_dir / "model_registry" / "providers")
                self._provider_to_path = discover_providers(providers_dir)
                providers = sorted(self._provider_to_path.keys())
                print(f"[DEBUG][FPF_UI][_late_populate] discovered providers={providers}", flush=True)
            except Exception as e:
                print(f"[WARN][FPF_UI][_late_populate] provider discovery failed: {e}", flush=True)
                providers = []

            try:
                self.comboFPFProvider.clear()
            except Exception:
                pass

            if providers:
                try:
                    self.comboFPFProvider.addItems(providers)
                except Exception as e:
                    print(f"[WARN][FPF_UI][_late_populate] Failed to add items: {e}", flush=True)
                try:
                    # Populate models for first provider
                    self._on_provider_changed(providers[0])
                except Exception:
                    pass

            # Connect signal if not already connected
            try:
                self.comboFPFProvider.currentTextChanged.connect(self._on_provider_changed)
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN][FPF_UI][_late_populate] Unexpected error: {e}", flush=True)

    def load_values(self) -> None:
        """
        Read config files and set slider values accordingly for FPF section.
        """
        try:
            # FilePromptForge/default_config.yaml
            try:
                fy = read_yaml(self.fpf_yaml)
                if self.sliderGroundingMaxResults:
                    gmr = int((((fy.get("grounding") or {}).get("max_results")) or 5))
                    self.sliderGroundingMaxResults.setValue(clamp_int(gmr, self.sliderGroundingMaxResults.minimum(), self.sliderGroundingMaxResults.maximum()))
                if self.sliderGoogleMaxTokens:
                    gmt = int((((fy.get("google") or {}).get("max_tokens")) or 1500))
                    self.sliderGoogleMaxTokens.setValue(clamp_int(gmt, self.sliderGoogleMaxTokens.minimum(), self.sliderGoogleMaxTokens.maximum()))
            except Exception as e:
                print(f"[WARN] Could not load {self.fpf_yaml}: {e}", flush=True)

        except Exception as e:
            show_error(f"Failed to initialize FPF UI from configs: {e}")

    def gather_values(self) -> Dict[str, Any]:
        """
        Collect slider values for FPF section.
        Returns a dictionary suitable for merging into main vals.
        """
        vals: Dict[str, Any] = {}

        # FPF (default_config.yaml)
        if self.sliderGroundingMaxResults:
            vals.setdefault("fpf", {})["grounding.max_results"] = int(self.sliderGroundingMaxResults.value())
        if self.sliderGoogleMaxTokens:
            vals.setdefault("fpf", {})["google.max_tokens"] = int(self.sliderGoogleMaxTokens.value())

        # Enable flags from checkable groupboxes (only for this section)
        enables: Dict[str, bool] = {}
        if self.groupProvidersFPF is not None:
            enables["fpf"] = bool(self.groupProvidersFPF.isChecked())
        if enables:
            vals["enable"] = enables

        return vals

    def write_configs(self, vals: Dict[str, Any]) -> None:
        """
        Persist collected slider values into FPF default_config.yaml.
        """
        try:
            fy = read_yaml(self.fpf_yaml)

            grounding = fy.get("grounding")
            if not isinstance(grounding, dict):
                grounding = {}
                fy["grounding"] = grounding
            # support both top-level keys and nested 'fpf' keys
            gmr = None
            if "grounding.max_results" in vals:
                gmr = int(vals["grounding.max_results"])
            else:
                gmr = int((vals.get("fpf", {}) or {}).get("grounding.max_results") or 0)
            if gmr is not None and gmr != 0:
                grounding["max_results"] = int(gmr)

            google = fy.get("google")
            if not isinstance(google, dict):
                google = {}
                fy["google"] = google
            gmt = None
            if "google.max_tokens" in vals:
                gmt = int(vals["google.max_tokens"])
            else:
                gmt = int((vals.get("fpf", {}) or {}).get("google.max_tokens") or 0)
            if gmt is not None and gmt != 0:
                google["max_tokens"] = int(gmt)
            
            write_yaml(self.fpf_yaml, fy)

            # Detailed console output
            try:
                log_lines = []
                if gmr:
                    log_lines.append(f"Wrote grounding.max_results = {gmr} -> {self.fpf_yaml}")
                if gmt:
                    log_lines.append(f"Wrote google.max_tokens = {gmt} -> {self.fpf_yaml}")
                if log_lines:
                    print("[OK] Wrote to", self.fpf_yaml)
                    for ln in log_lines:
                        print("  -", ln)
                else:
                    print(f"[OK] Wrote {self.fpf_yaml} (no relevant keys found in vals)", flush=True)
            except Exception:
                print(f"[OK] Wrote {self.fpf_yaml}", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to write {self.fpf_yaml}: {e}")

    def on_open_fpf_config(self) -> None:
        """Open the FilePromptForge default_config.yaml file in the system editor (if present)."""
        try:
            if self.fpf_yaml.exists():
                _open_in_file_explorer(str(self.fpf_yaml))
            else:
                show_info(f"FilePromptForge default_config.yaml not found at {self.fpf_yaml}")
        except Exception as e:
            print(f"[WARN] on_open_fpf_config failed: {e}", flush=True)

    def _on_provider_changed(self, provider_name: str) -> None:
        """
        Populate the comboFPFModel based on the selected provider's YAML.
        This mirrors ProviderModelSelector.on_provider_changed but keeps state local to the FPF handler.
        """
        try:
            path = None
            try:
                path = self._provider_to_path.get(provider_name)
            except Exception:
                path = None

            if not self.comboFPFModel:
                return

            # Clear current models
            try:
                self.comboFPFModel.clear()
            except Exception:
                pass

            if not path or not Path(path).is_file():
                try:
                    self.comboFPFModel.setEnabled(False)
                except Exception:
                    pass
                return

            try:
                models, detected_key = extract_models_from_yaml(provider_name, path)
            except Exception as e:
                models = []
                print(f"[WARN] Failed to extract models from {path}: {e}", flush=True)

            if not models:
                try:
                    self.comboFPFModel.setEnabled(False)
                except Exception:
                    pass
                return

            try:
                self.comboFPFModel.addItems(models)
                self.comboFPFModel.setEnabled(True)
            except Exception as e:
                print(f"[WARN] Failed to populate FPF model combobox: {e}", flush=True)
        except Exception as e:
            print(f"[WARN] _on_provider_changed failed: {e}", flush=True)

    def _on_groupbox_toggled(self, key: str, checked: bool) -> None:
        """
        Handler when a checkable groupbox is toggled for this section.
        """
        try:
            status = f"FPF {key} enabled" if checked else f"FPF {key} disabled"
            if self.main_window.statusBar(): # Check if status bar exists
                self.main_window.statusBar().showMessage(status, 3000)
        except Exception:
            print(f"[INFO] {status}", flush=True)

    def apply_master_quality_to_sliders(self, percent: float) -> None:
        """
        Applies master quality percentage to all sliders managed by this handler.
        """
        sliders = [
            self.sliderGroundingMaxResults,
            self.sliderGoogleMaxTokens,
        ]
        for sl in sliders:
            if sl:
                self._scale_slider(sl, percent)
    
    def _scale_slider(self, slider: QtWidgets.QSlider, percent: float) -> None:
        """
        Set a slider to min + percent*(max-min), blocking signals to avoid feedback loops.
        """
        try:
            smin = slider.minimum()
            smax = slider.maximum()
            if smax <= smin:
                return
            target = smin + round(percent * (smax - smin))
            prev = slider.blockSignals(True)
            slider.setValue(int(target))
            slider.blockSignals(prev)
        except Exception as e:
            print(f"[WARN] Scaling slider failed in FPF_UI_Handler: {e}", flush=True)

    def apply_preset(self, data: Dict[str, Any]) -> None:
        """Apply preset dict to UI widgets for FPF section."""
        try:
            # Enables
            en = data.get("enable", {})
            if isinstance(en, dict):
                if "fpf" in en and self.groupProvidersFPF:
                    self.groupProvidersFPF.setChecked(bool(en["fpf"]))

            # Sliders (managed by this handler)
            if "fpf" in data and isinstance(data["fpf"], dict):
                if "grounding.max_results" in data["fpf"] and self.sliderGroundingMaxResults:
                    self.sliderGroundingMaxResults.setValue(int(data["fpf"]["grounding.max_results"]))
                if "google.max_tokens" in data["fpf"] and self.sliderGoogleMaxTokens:
                    self.sliderGoogleMaxTokens.setValue(int(data["fpf"]["google.max_tokens"]))
        except Exception as e:
            print(f"[WARN] apply_preset failed in FPF_UI_Handler: {e}", flush=True)
