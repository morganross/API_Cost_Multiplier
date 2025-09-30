from pathlib import Path
import re
from typing import Dict, Any, Optional

from PyQt5 import QtWidgets, uic

from .gui_utils import (
    clamp_int, temp_from_slider, read_yaml, read_json, read_text, write_yaml, write_json, write_text,
    extract_number_from_default_py, replace_number_in_default_py, show_error, show_info,
    _open_in_file_explorer, _set_combobox_text
)


class GPTRMA_UI_Handler:
    def __init__(self, main_window: QtWidgets.QMainWindow):
        self.main_window = main_window
        
        # Paths
        self.gptr_default_py = self.main_window.pm_dir / "gpt-researcher" / "gpt_researcher" / "config" / "variables" / "default.py"
        self.ma_task_json = self.main_window.pm_dir / "gpt-researcher" / "multi_agents" / "task.json"

        # Cache widgets
        self.sliderFastTokenLimit: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderFastTokenLimit")
        self.sliderSmartTokenLimit: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderSmartTokenLimit")
        self.sliderStrategicTokenLimit: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderStrategicTokenLimit")
        self.sliderBrowseChunkMaxLength: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderBrowseChunkMaxLength")
        self.sliderSummaryTokenLimit: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderSummaryTokenLimit")
        self.sliderTemperature: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderTemperature")
        self.sliderMaxSearchResultsPerQuery: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderMaxSearchResultsPerQuery")
        self.sliderTotalWords: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderTotalWords")
        self.sliderMaxIterations: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderMaxIterations")
        self.sliderMaxSubtopics: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderMaxSubtopics")
        self.sliderDeepResearchBreadth: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderDeepResearchBreadth")
        self.sliderDeepResearchDepth: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderDeepResearchDepth")
        self.sliderMaxSections: QtWidgets.QSlider = main_window.findChild(QtWidgets.QSlider, "sliderMaxSections")

        self.comboGPTRProvider: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboGPTRProvider")
        self.comboGPTRModel: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboGPTRModel")
        self.comboDRProvider: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboDRProvider")
        self.comboDRModel: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboDRModel")
        self.comboMAProvider: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboMAProvider")
        self.comboMAModel: QtWidgets.QComboBox = main_window.findChild(QtWidgets.QComboBox, "comboMAModel")

        self.groupProvidersGPTR: Optional[QtWidgets.QGroupBox] = main_window.findChild(QtWidgets.QGroupBox, "groupProvidersGPTR")
        self.groupProvidersDR: Optional[QtWidgets.QGroupBox] = main_window.findChild(QtWidgets.QGroupBox, "groupProvidersDR")
        self.groupProvidersMA: Optional[QtWidgets.QGroupBox] = main_window.findChild(QtWidgets.QGroupBox, "groupProvidersMA")

    def connect_signals(self):
        """Connect UI signals to handler methods."""
        
        # Bottom toolbar button connections
        try:
            btn = self.main_window.findChild(QtWidgets.QPushButton, "btnAction1")  # Open GPT-R Config (file)
            if btn:
                btn.clicked.connect(self.on_open_gptr_config)
        except Exception:
            pass
        try:
            btn = self.main_window.findChild(QtWidgets.QPushButton, "btnAction3")  # Open MA Config (file)
            if btn:
                btn.clicked.connect(self.on_open_ma_config)
        except Exception:
            pass

        # Connect groupbox toggles
        if self.groupProvidersGPTR:
            self.groupProvidersGPTR.toggled.connect(lambda v, k="gptr": self._on_groupbox_toggled(k, v))
        if self.groupProvidersDR:
            self.groupProvidersDR.toggled.connect(lambda v, k="dr": self._on_groupbox_toggled(k, v))
        if self.groupProvidersMA:
            self.groupProvidersMA.toggled.connect(lambda v, k="ma": self._on_groupbox_toggled(k, v))

        # Keep GPTR and DR provider/model selectors in sync (they represent the same underlying LLM)
        try:
            def _sync_provider_from_gptr(_idx=None):
                try:
                    prov = self.comboGPTRProvider.currentText() if getattr(self, "comboGPTRProvider", None) else ""
                    model = self.comboGPTRModel.currentText() if getattr(self, "comboGPTRModel", None) else ""
                    if getattr(self, "comboDRProvider", None):
                        prev = self.comboDRProvider.blockSignals(True)
                        _set_combobox_text(self.comboDRProvider, prov)
                        self.comboDRProvider.blockSignals(prev)
                    if getattr(self, "comboDRModel", None):
                        prev = self.comboDRModel.blockSignals(True)
                        _set_combobox_text(self.comboDRModel, model)
                        self.comboDRModel.blockSignals(prev)
                except Exception:
                    pass

            def _sync_provider_from_dr(_idx=None):
                try:
                    prov = self.comboDRProvider.currentText() if getattr(self, "comboDRProvider", None) else ""
                    model = self.comboDRModel.currentText() if getattr(self, "comboDRModel", None) else ""
                    if getattr(self, "comboGPTRProvider", None):
                        prev = self.comboGPTRProvider.blockSignals(True)
                        _set_combobox_text(self.comboGPTRProvider, prov)
                        self.comboGPTRProvider.blockSignals(prev)
                    if getattr(self, "comboGPTRModel", None):
                        prev = self.comboGPTRModel.blockSignals(True)
                        _set_combobox_text(self.comboGPTRModel, model)
                        self.comboGPTRModel.blockSignals(prev)
                except Exception:
                    pass

            if getattr(self, "comboGPTRProvider", None):
                try:
                    self.comboGPTRProvider.currentIndexChanged.connect(_sync_provider_from_gptr)
                except Exception:
                    pass
            if getattr(self, "comboGPTRModel", None):
                try:
                    self.comboGPTRModel.currentIndexChanged.connect(_sync_provider_from_gptr)
                except Exception:
                    pass
            if getattr(self, "comboDRProvider", None):
                try:
                    self.comboDRProvider.currentIndexChanged.connect(_sync_provider_from_dr)
                except Exception:
                    pass
            if getattr(self, "comboDRModel", None):
                try:
                    self.comboDRModel.currentIndexChanged.connect(_sync_provider_from_dr)
                except Exception:
                    pass
        except Exception:
            pass


    def load_values(self) -> None:
        """
        Read config files and set slider values accordingly for GPTR and MA sections.
        """
        try:
            # gpt-researcher/gpt_researcher/config/variables/default.py
            try:
                t = read_text(self.gptr_default_py)
                def set_from_py(slider: Optional[QtWidgets.QSlider], key: str, scale_temp: bool = False, default_val: int = 0):
                    if not slider:
                        return
                    val = extract_number_from_default_py(t, key)
                    if val is None:
                        # keep default slider value
                        return
                    if scale_temp:
                        v100 = int(round(float(val) * 100.0))
                        slider.setValue(clamp_int(v100, slider.minimum(), slider.maximum()))
                    else:
                        slider.setValue(clamp_int(int(round(val)), slider.minimum(), slider.maximum()))

                set_from_py(self.sliderFastTokenLimit, "FAST_TOKEN_LIMIT")
                set_from_py(self.sliderSmartTokenLimit, "SMART_TOKEN_LIMIT")
                set_from_py(self.sliderStrategicTokenLimit, "STRATEGIC_TOKEN_LIMIT")
                set_from_py(self.sliderBrowseChunkMaxLength, "BROWSE_CHUNK_MAX_LENGTH")
                set_from_py(self.sliderSummaryTokenLimit, "SUMMARY_TOKEN_LIMIT")
                set_from_py(self.sliderTemperature, "TEMPERATURE", scale_temp=True)
                set_from_py(self.sliderMaxSearchResultsPerQuery, "MAX_SEARCH_RESULTS_PER_QUERY")
                set_from_py(self.sliderTotalWords, "TOTAL_WORDS")
                set_from_py(self.sliderMaxIterations, "MAX_ITERATIONS")
                set_from_py(self.sliderMaxSubtopics, "MAX_SUBTOPICS")
                set_from_py(self.sliderDeepResearchBreadth, "DEEP_RESEARCH_BREADTH")
                set_from_py(self.sliderDeepResearchDepth, "DEEP_RESEARCH_DEPTH")
                # Extract GPTR provider:model combined strings (SMART_LLM / STRATEGIC_LLM)
                try:
                    m = re.search(r'["\']SMART_LLM["\']\s*:\s*["\']([^"\']+)["\']', t)
                    smart = m.group(1) if m else None
                    m2 = re.search(r'["\']STRATEGIC_LLM["\']\s*:\s*["\']([^"\']+)["\']', t)
                    strategic = m2.group(1) if m2 else None
                    combined = smart or strategic
                    if combined and self.comboGPTRProvider and self.comboGPTRModel:
                        if ":" in combined:
                            prov, model = combined.split(":", 1)
                            _set_combobox_text(self.comboGPTRProvider, prov)
                            _set_combobox_text(self.comboGPTRModel, model)
                        else:
                            # no provider prefix; put entire string into model combobox
                            _set_combobox_text(self.comboGPTRModel, combined)
                except Exception:
                    pass
            except Exception as e:
                print(f"[WARN] Could not load {self.gptr_default_py}: {e}", flush=True)

            # gpt-researcher/multi_agents/task.json
            try:
                j = read_json(self.ma_task_json)
                ms = int(j.get("max_sections", 1))
                if self.sliderMaxSections:
                    self.sliderMaxSections.setValue(clamp_int(ms, self.sliderMaxSections.minimum(), self.sliderMaxSections.maximum()))
                # Load MA model into comboMAModel if present in task.json (inherit on GUI launch)
                try:
                    ma_model = j.get("model")
                    if ma_model and getattr(self, "comboMAModel", None):
                        _set_combobox_text(self.comboMAModel, str(ma_model))
                    # Load follow_guidelines into main window checkbox if present
                    try:
                        fg = j.get("follow_guidelines")
                        if fg is not None and getattr(self.main_window, "checkFollowGuidelines", None) is not None:
                            self.main_window.checkFollowGuidelines.setChecked(bool(fg))
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception as e:
                print(f"[WARN] Could not load {self.ma_task_json}: {e}", flush=True)

        except Exception as e:
            show_error(f"Failed to initialize GPTR/MA UI from configs: {e}")

    def gather_values(self) -> Dict[str, Any]:
        """
        Collect slider values for GPTR and MA sections.
        Returns a dictionary suitable for merging into main vals.
        """
        vals: Dict[str, Any] = {}

        # GPTR (default.py)
        if self.sliderFastTokenLimit:
            vals["FAST_TOKEN_LIMIT"] = int(self.sliderFastTokenLimit.value())
        if self.sliderSmartTokenLimit:
            vals["SMART_TOKEN_LIMIT"] = int(self.sliderSmartTokenLimit.value())
        if self.sliderStrategicTokenLimit:
            vals["STRATEGIC_TOKEN_LIMIT"] = int(self.sliderStrategicTokenLimit.value())
        if self.sliderBrowseChunkMaxLength:
            vals["BROWSE_CHUNK_MAX_LENGTH"] = int(self.sliderBrowseChunkMaxLength.value())
        if self.sliderSummaryTokenLimit:
            vals["SUMMARY_TOKEN_LIMIT"] = int(self.sliderSummaryTokenLimit.value())
        if self.sliderTemperature:
            vals["TEMPERATURE"] = float(temp_from_slider(int(self.sliderTemperature.value())))
        if self.sliderMaxSearchResultsPerQuery:
            vals["MAX_SEARCH_RESULTS_PER_QUERY"] = int(self.sliderMaxSearchResultsPerQuery.value())
        if self.sliderTotalWords:
            vals["TOTAL_WORDS"] = int(self.sliderTotalWords.value())
        if self.sliderMaxIterations:
            vals["MAX_ITERATIONS"] = int(self.sliderMaxIterations.value())
        if self.sliderMaxSubtopics:
            vals["MAX_SUBTOPICS"] = int(self.sliderMaxSubtopics.value())

        # DR (default.py)
        if self.sliderDeepResearchBreadth:
            vals["DEEP_RESEARCH_BREADTH"] = int(self.sliderDeepResearchBreadth.value())
        if self.sliderDeepResearchDepth:
            vals["DEEP_RESEARCH_DEPTH"] = int(self.sliderDeepResearchDepth.value())

        # Provider/model selections for GPTR/DR (they share the same underlying LLM).
        # Persist under vals["providers"]["gptr"] and mirror into vals["providers"]["dr"] so
        # the write path can update default.py consistently.
        try:
            prov = None
            model = None
            if getattr(self, "comboGPTRProvider", None):
                prov = str(self.comboGPTRProvider.currentText())
            if getattr(self, "comboGPTRModel", None):
                model = str(self.comboGPTRModel.currentText())
            if prov or model:
                vals.setdefault("providers", {})["gptr"] = {}
                if prov:
                    vals["providers"]["gptr"]["provider"] = prov
                if model:
                    vals["providers"]["gptr"]["model"] = model
                # Mirror into DR so UI DR selectors effectively edit the same underlying provider/model
                vals.setdefault("providers", {})["dr"] = {}
                if prov:
                    vals["providers"]["dr"]["provider"] = prov
                if model:
                    vals["providers"]["dr"]["model"] = model
        except Exception:
            pass

        # MA (task.json)
        if self.sliderMaxSections:
            vals.setdefault("ma", {})["max_sections"] = int(self.sliderMaxSections.value())
            
        # Enable flags from checkable groupboxes (only for this section)
        enables: Dict[str, bool] = {}
        if self.groupProvidersGPTR is not None:
            enables["gptr"] = bool(self.groupProvidersGPTR.isChecked())
        if self.groupProvidersDR is not None:
            enables["dr"] = bool(self.groupProvidersDR.isChecked())
        if self.groupProvidersMA is not None:
            enables["ma"] = bool(self.groupProvidersMA.isChecked())
        if enables:
            vals["enable"] = enables

        return vals

    def write_configs(self, vals: Dict[str, Any]) -> None:
        """
        Persist collected slider values into GPTR default.py and MA task.json files.
        """
        # gpt-researcher/gpt_researcher/config/variables/default.py
        try:
            t = read_text(self.gptr_default_py)
            if not t:
                raise RuntimeError("default.py not found or empty")
            # Safety: ensure we're editing the expected DEFAULT_CONFIG block/header
            if "DEFAULT_CONFIG" not in t or "from .base import BaseConfig" not in t:
                raise RuntimeError("default.py missing DEFAULT_CONFIG header; aborting write")
            keys_to_update = [
                "FAST_TOKEN_LIMIT",
                "SMART_TOKEN_LIMIT",
                "STRATEGIC_TOKEN_LIMIT",
                "BROWSE_CHUNK_MAX_LENGTH",
                "SUMMARY_TOKEN_LIMIT",
                "TEMPERATURE",
                "MAX_SEARCH_RESULTS_PER_QUERY",
                "TOTAL_WORDS",
                "MAX_ITERATIONS",
                "MAX_SUBTOPICS",
                "DEEP_RESEARCH_BREADTH",
                "DEEP_RESEARCH_DEPTH",
            ]
            replaced_any = False
            missing: list[str] = []
            updated_keys: list[str] = []
            for k in keys_to_update:
                if k == "TEMPERATURE":
                    if "TEMPERATURE" in vals:
                        t2, ok = replace_number_in_default_py(t, "TEMPERATURE", float(vals["TEMPERATURE"]))
                        if ok:
                            t = t2
                            replaced_any = True
                            updated_keys.append("TEMPERATURE")
                        else:
                            missing.append(k)
                else:
                    if k in vals: # Check if key is present in the provided vals
                        try:
                            newv = float(vals[k])
                        except Exception: # Fallback in case of type issues, though should not happen with direct slider vals
                            newv = float(vals[k])
                        t2, ok = replace_number_in_default_py(t, k, float(newv))
                        if ok:
                            t = t2
                            replaced_any = True
                            updated_keys.append(k)
                        else:
                            missing.append(k)
            if replaced_any:
                write_text(self.gptr_default_py, t)
                try:
                    print("[OK] Wrote to", self.gptr_default_py)
                    for k in updated_keys:
                        val_display = vals.get(k) if k != "TEMPERATURE" else vals.get("TEMPERATURE")
                        print(f"  - Wrote {k} = {val_display!r} -> {self.gptr_default_py}")
                except Exception:
                    print(f"[OK] Wrote {self.gptr_default_py}", flush=True)

            # Persist provider:model for GPTR (SMART_LLM / STRATEGIC_LLM)
            # Prefer values passed via vals['providers']['gptr'], otherwise fall back to the current combobox values.
            try:
                prov_info = (vals.get("providers") or {}).get("gptr") if isinstance(vals.get("providers"), dict) else None
                prov = None
                pmodel = None
                if isinstance(prov_info, dict):
                    prov = prov_info.get("provider")
                    pmodel = prov_info.get("model")
                # Fallback to combobox values if vals did not include provider/model
                try:
                    if not prov and getattr(self, "comboGPTRProvider", None):
                        prov = str(self.comboGPTRProvider.currentText()) or None
                    if not pmodel and getattr(self, "comboGPTRModel", None):
                        pmodel = str(self.comboGPTRModel.currentText()) or None
                except Exception:
                    pass

                # Debug output to confirm what will be written
                try:
                    print(f"[DEBUG] GPTR write: vals.providers.gptr={prov_info!r}, combobox_provider={getattr(self, 'comboGPTRProvider', None).currentText() if getattr(self, 'comboGPTRProvider', None) else None}, combobox_model={getattr(self, 'comboGPTRModel', None).currentText() if getattr(self, 'comboGPTRModel', None) else None}", flush=True)
                except Exception:
                    pass

                if prov and pmodel:
                    combined = f"{prov}:{pmodel}"
                    try:
                        t = re.sub(r'("SMART_LLM"\s*:\s*")[^"]*(")', rf'\1{combined}\2', t)
                        t = re.sub(r'("STRATEGIC_LLM"\s*:\s*")[^"]*(")', rf'\1{combined}\2', t)
                        write_text(self.gptr_default_py, t)
                        try:
                            print(f"[OK] Wrote GPTR provider/model = {combined!r} -> {self.gptr_default_py}", flush=True)
                        except Exception:
                            print(f"[OK] Wrote GPTR provider/model -> {self.gptr_default_py}", flush=True)
                    except Exception:
                        print(f"[ERROR] Failed to write GPTR provider/model to {self.gptr_default_py}", flush=True)
            except Exception as e:
                print(f"[ERROR] Exception while attempting to write GPTR provider/model: {e}", flush=True)
                pass

            if missing:
                print(f"[WARN] Some keys were not found for update in default.py: {', '.join(missing)}", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to write {self.gptr_default_py}: {e}")

        # gpt-researcher/multi_agents/task.json
        try:
            j = read_json(self.ma_task_json)
            # Support both top-level 'ma.max_sections' or nested 'ma' dict in vals
            ms = vals.get("ma", {}).get("max_sections")
            if ms is None:
                ms = vals.get("ma.max_sections")
            if ms is not None:
                j["max_sections"] = int(ms)

            # Persist MA model into task.json:
            try:
                ma_info = (vals.get("providers") or {}).get("ma") if isinstance(vals.get("providers"), dict) else None
                ma_model = None
                if isinstance(ma_info, dict):
                    ma_model = ma_info.get("model")
                # fallback to combobox value if not supplied in vals
                try:
                    if not ma_model and getattr(self, "comboMAModel", None):
                        ma_model = str(self.comboMAModel.currentText()) or None
                except Exception:
                    pass
                if ma_model:
                    j["model"] = ma_model
                    try:
                        print(f"[OK] Wrote MA model = {ma_model!r} -> {self.ma_task_json}", flush=True)
                    except Exception:
                        pass
            except Exception:
                pass

            # Persist follow_guidelines if provided in vals or read from main window checkbox
            try:
                fg_val = None
                if isinstance(vals.get("follow_guidelines", None), bool):
                    fg_val = bool(vals.get("follow_guidelines"))
                elif getattr(self.main_window, "checkFollowGuidelines", None) is not None:
                    try:
                        fg_val = bool(self.main_window.checkFollowGuidelines.isChecked())
                    except Exception:
                        fg_val = None
                if fg_val is not None:
                    j["follow_guidelines"] = bool(fg_val)
            except Exception:
                pass

            write_json(self.ma_task_json, j)
            try:
                if ms is not None:
                    print("[OK] Wrote to", self.ma_task_json)
                    print(f"  - Wrote ma.max_sections = {int(ms)} -> {self.ma_task_json}")
                else:
                    print(f"[OK] Wrote {self.ma_task_json} (no ma.max_sections in vals)", flush=True)
            except Exception:
                print(f"[OK] Wrote {self.ma_task_json}", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to write {self.ma_task_json}: {e}")

    def on_open_gptr_config(self) -> None:
        """Open the GPT Researcher default.py file in the system editor (if present)."""
        try:
            if self.gptr_default_py.exists():
                _open_in_file_explorer(str(self.gptr_default_py))
            else:
                show_info(f"GPT-R default.py not found at {self.gptr_default_py}")
        except Exception as e:
            print(f"[WARN] on_open_gptr_config failed: {e}", flush=True)

    def on_open_ma_config(self) -> None:
        """Open the multi-agent task.json file in the system editor (if present)."""
        try:
            if self.ma_task_json.exists():
                _open_in_file_explorer(str(self.ma_task_json))
            else:
                show_info(f"MA task.json not found at {self.ma_task_json}")
        except Exception as e:
            print(f"[WARN] on_open_ma_config failed: {e}", flush=True)

    def _on_groupbox_toggled(self, key: str, checked: bool) -> None:
        """
        Handler when a checkable groupbox is toggled for this section.
        """
        try:
            status = f"GPTR/MA {key} enabled" if checked else f"GPTR/MA {key} disabled"
            if self.main_window.statusBar(): # Check if status bar exists
                self.main_window.statusBar().showMessage(status, 3000)
        except Exception:
            print(f"[INFO] {status}", flush=True)

    def apply_master_quality_to_sliders(self, percent: float) -> None:
        """
        Applies master quality percentage to all sliders managed by this handler.
        """
        sliders = [
            self.sliderFastTokenLimit,
            self.sliderSmartTokenLimit,
            self.sliderStrategicTokenLimit,
            self.sliderBrowseChunkMaxLength,
            self.sliderSummaryTokenLimit,
            self.sliderTemperature,
            self.sliderMaxSearchResultsPerQuery,
            self.sliderTotalWords,
            self.sliderMaxIterations,
            self.sliderMaxSubtopics,
            self.sliderDeepResearchBreadth,
            self.sliderDeepResearchDepth,
            self.sliderMaxSections,
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
            print(f"[WARN] Scaling slider failed in GPTRMA_UI_Handler: {e}", flush=True)

    def apply_preset(self, data: Dict[str, Any]) -> None:
        """Apply preset dict to UI widgets for GPTR/MA section."""
        try:
            # Providers
            provs = data.get("providers", {})
            if isinstance(provs, dict):
                gptr = provs.get("gptr", {})
                if isinstance(gptr, dict):
                    if "provider" in gptr and self.comboGPTRProvider:
                        _set_combobox_text(self.comboGPTRProvider, str(gptr["provider"]))
                    if "model" in gptr and self.comboGPTRModel:
                        _set_combobox_text(self.comboGPTRModel, str(gptr["model"]))
                dr = provs.get("dr", {})
                if isinstance(dr, dict):
                    if "provider" in dr and self.comboDRProvider:
                        _set_combobox_text(self.comboDRProvider, str(dr["provider"]))
                    if "model" in dr and self.comboDRModel:
                        _set_combobox_text(self.comboDRModel, str(dr["model"]))
                ma = provs.get("ma", {})
                if isinstance(ma, dict):
                    if "provider" in ma and self.comboMAProvider:
                        _set_combobox_text(self.comboMAProvider, str(ma["provider"]))
                    if "model" in ma and self.comboMAModel:
                        _set_combobox_text(self.comboMAModel, str(ma["model"]))

            # Enables
            en = data.get("enable", {})
            if isinstance(en, dict):
                if "gptr" in en and self.groupProvidersGPTR:
                    self.groupProvidersGPTR.setChecked(bool(en["gptr"]))
                if "dr" in en and self.groupProvidersDR:
                    self.groupProvidersDR.setChecked(bool(en["dr"]))
                if "ma" in en and self.groupProvidersMA:
                    self.groupProvidersMA.setChecked(bool(en["ma"]))

            # Sliders (managed by this handler)
            if "FAST_TOKEN_LIMIT" in data and self.sliderFastTokenLimit:
                self.sliderFastTokenLimit.setValue(int(data["FAST_TOKEN_LIMIT"]))
            if "SMART_TOKEN_LIMIT" in data and self.sliderSmartTokenLimit:
                self.sliderSmartTokenLimit.setValue(int(data["SMART_TOKEN_LIMIT"]))
            if "STRATEGIC_TOKEN_LIMIT" in data and self.sliderStrategicTokenLimit:
                self.sliderStrategicTokenLimit.setValue(int(data["STRATEGIC_TOKEN_LIMIT"]))
            if "BROWSE_CHUNK_MAX_LENGTH" in data and self.sliderBrowseChunkMaxLength:
                self.sliderBrowseChunkMaxLength.setValue(int(data["BROWSE_CHUNK_MAX_LENGTH"]))
            if "SUMMARY_TOKEN_LIMIT" in data and self.sliderSummaryTokenLimit:
                self.sliderSummaryTokenLimit.setValue(int(data["SUMMARY_TOKEN_LIMIT"]))
            if "TEMPERATURE" in data and self.sliderTemperature:
                self.sliderTemperature.setValue(int(round(float(data["TEMPERATURE"]) * 100.0)))
            if "MAX_SEARCH_RESULTS_PER_QUERY" in data and self.sliderMaxSearchResultsPerQuery:
                self.sliderMaxSearchResultsPerQuery.setValue(int(data["MAX_SEARCH_RESULTS_PER_QUERY"]))
            if "TOTAL_WORDS" in data and self.sliderTotalWords:
                self.sliderTotalWords.setValue(int(data["TOTAL_WORDS"]))
            if "MAX_ITERATIONS" in data and self.sliderMaxIterations:
                self.sliderMaxIterations.setValue(int(data["MAX_ITERATIONS"]))
            if "MAX_SUBTOPICS" in data and self.sliderMaxSubtopics:
                self.sliderMaxSubtopics.setValue(int(data["MAX_SUBTOPICS"]))
            if "DEEP_RESEARCH_BREADTH" in data and self.sliderDeepResearchBreadth:
                self.sliderDeepResearchBreadth.setValue(int(data["DEEP_RESEARCH_BREADTH"]))
            if "DEEP_RESEARCH_DEPTH" in data and self.sliderDeepResearchDepth:
                self.sliderDeepResearchDepth.setValue(int(data["DEEP_RESEARCH_DEPTH"]))
            if "ma" in data and isinstance(data["ma"], dict) and "max_sections" in data["ma"] and self.sliderMaxSections:
                self.sliderMaxSections.setValue(int(data["ma"]["max_sections"]))

        except Exception as e:
            print(f"[WARN] apply_preset failed in GPTRMA_UI_Handler: {e}", flush=True)
