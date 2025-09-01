from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5 import QtWidgets, uic

from API_Cost_Multiplier.GUI.gui_utils import (
    clamp_int, temp_from_slider, read_yaml, read_json, read_text, write_yaml, write_json, write_text,
    show_error, show_info, _open_in_file_explorer, _set_combobox_text
)


class FPF_UI_Handler:
    def __init__(self, main_window: QtWidgets.QMainWindow):
        self.main_window = main_window
        
        # Paths
        self.fpf_yaml = self.main_window.pm_dir / "FilePromptForge" / "default_config.yaml"

        # Cache widgets
        self.sliderGroundingMaxResults: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderGroundingMaxResults")
        self.sliderGoogleMaxTokens: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderGoogleMaxTokens")
        
        self.comboFPFProvider: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboFPFProvider")
        self.comboFPFModel: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboFPFModel")

        self.groupProvidersFPF: Optional[QtWidgets.QGroupBox] = main_window.findChild(QtWidgets.QGroupBox, "groupProvidersFPF")

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

    def load_values(self) -> None:
        """
        Read config files and set slider values and provider/model combobox accordingly for FPF section.
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
                # Populate provider/model comboboxes from default_config.yaml:
                try:
                    prov = fy.get("provider")
                    if prov and self.comboFPFProvider:
                        _set_combobox_text(self.comboFPFProvider, str(prov))
                    # provider-specific model location: fy[provider]["model"]
                    if prov:
                        sec = fy.get(prov) or {}
                        pmodel = sec.get("model") if isinstance(sec, dict) else None
                        if pmodel and self.comboFPFModel:
                            _set_combobox_text(self.comboFPFModel, str(pmodel))
                except Exception:
                    pass
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

        # Provider/model selected in UI (persist under a 'providers' key so write_configs can update file)
        try:
            prov = None
            model = None
            if getattr(self, "comboFPFProvider", None):
                prov = str(self.comboFPFProvider.currentText())
            if getattr(self, "comboFPFModel", None):
                model = str(self.comboFPFModel.currentText())
            if prov or model:
                vals.setdefault("providers", {})["fpf"] = {}
                if prov:
                    vals["providers"]["fpf"]["provider"] = prov
                if model:
                    vals["providers"]["fpf"]["model"] = model
        except Exception:
            pass

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

            # Persist provider/model from UI if provided under vals["providers"]["fpf"]
            prov_info = (vals.get("providers") or {}).get("fpf") if isinstance(vals.get("providers"), dict) else None
            if isinstance(prov_info, dict):
                prov = prov_info.get("provider")
                pmodel = prov_info.get("model")
                if prov:
                    fy["provider"] = prov
                    # ensure provider section exists
                    if not isinstance(fy.get(prov), dict):
                        fy[prov] = {}
                    if pmodel:
                        fy[prov]["model"] = pmodel

            write_yaml(self.fpf_yaml, fy)

            # Detailed console output
            try:
                log_lines = []
                if gmr:
                    log_lines.append(f"Wrote grounding.max_results = {gmr} -> {self.fpf_yaml}")
                if gmt:
                    log_lines.append(f"Wrote google.max_tokens = {gmt} -> {self.fpf_yaml}")
                if prov_info:
                    log_lines.append(f"Wrote providers.fpf = {prov_info!r} -> {self.fpf_yaml}")
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
            # Providers
            provs = data.get("providers", {})
            if isinstance(provs, dict):
                fpf = provs.get("fpf", {})
                if isinstance(fpf, dict):
                    if "provider" in fpf and self.comboFPFProvider:
                        _set_combobox_text(self.comboFPFProvider, str(fpf["provider"]))
                    if "model" in fpf and self.comboFPFModel:
                        _set_combobox_text(self.comboFPFModel, str(fpf["model"]))

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
