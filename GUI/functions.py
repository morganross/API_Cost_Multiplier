import sys
import os
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5 import QtWidgets, uic

from .gui_utils import (
    clamp_int, temp_from_slider, read_yaml, read_json, read_text, write_yaml, write_json, write_text,
    extract_number_from_default_py, replace_number_in_default_py,
    RunnerThread, DownloadThread, show_error, show_info, _open_in_file_explorer
)
from .gptr_ma_ui import GPTRMA_UI_Handler
from .fpf_ui import FPF_UI_Handler


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # Paths
        self.this_file = Path(__file__).resolve()
        self.pm_dir = self.this_file.parents[1]  # process_markdown/
        self.repo_root = self.pm_dir.parent

        # UI file is located in the GUI directory next to this file
        self.ui_path = self.this_file.parent / "main_window.ui"

        self.pm_config_yaml = self.pm_dir / "config.yaml"
        self.fpf_yaml = self.pm_dir / "FilePromptForge" / "fpf_config.yaml" # Updated to new FPF schema
        self.gptr_default_py = self.pm_dir / "gpt-researcher" / "gpt_researcher" / "config" / "variables" / "default.py" # Keep original reference for handlers
        self.ma_task_json = self.pm_dir / "gpt-researcher" / "multi_agents" / "task.json" # Keep original reference for handlers
        self.generate_py = self.pm_dir / "generate.py"

        # Load UI
        self.ui = uic.loadUi(str(self.ui_path), self)

        # Replace right panel with providers.ui (incremental split of config_sliders.ui) with robust fallbacks
        try:
            inserted = False
            providers_ui_path = self.this_file.parent / "providers.ui"
            if providers_ui_path.exists():
                providers_widget = uic.loadUi(str(providers_ui_path))
                # Preferred: add to rightLayout if present
                right_layout = self.findChild(QtWidgets.QVBoxLayout, "rightLayout")
                if right_layout:
                    while right_layout.count():
                        item = right_layout.takeAt(0)
                        w = item.widget()
                        if w:
                            w.setParent(None)
                            w.deleteLater()
                    right_layout.addWidget(providers_widget)
                    inserted = True
                # Fallback: insert a container widget into rowLayout position 1
                if not inserted:
                    row_layout = self.findChild(QtWidgets.QHBoxLayout, "rowLayout")
                    if row_layout:
                        container = QtWidgets.QWidget()
                        v = QtWidgets.QVBoxLayout(container)
                        v.setContentsMargins(2, 2, 2, 2)
                        v.setSpacing(1)
                        v.addWidget(providers_widget)
                        row_layout.insertWidget(1, container)
                        inserted = True
            print(f"[DEBUG] providers.ui inserted={inserted}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed to load providers.ui into layout: {e}", flush=True)

        # Replace paths/evaluations column with paths_evaluations.ui (with fallbacks)
        try:
            inserted = False
            pe_ui_path = self.this_file.parent / "paths_evaluations.ui"
            if pe_ui_path.exists():
                pe_widget = uic.loadUi(str(pe_ui_path))
                paths_layout = self.findChild(QtWidgets.QVBoxLayout, "pathsLayout")
                if paths_layout:
                    while paths_layout.count():
                        item = paths_layout.takeAt(0)
                        w = item.widget()
                        if w:
                            w.setParent(None)
                            w.deleteLater()
                    paths_layout.addWidget(pe_widget)
                    inserted = True
                if not inserted:
                    row_layout = self.findChild(QtWidgets.QHBoxLayout, "rowLayout")
                    if row_layout:
                        container = QtWidgets.QWidget()
                        v = QtWidgets.QVBoxLayout(container)
                        v.setContentsMargins(2, 2, 2, 2)
                        v.setSpacing(2)
                        v.addWidget(pe_widget)
                        # index 2: after scroll area (0) and providers (1)
                        row_layout.insertWidget(2, container)
                        inserted = True
            print(f"[DEBUG] paths_evaluations.ui inserted={inserted}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed to load paths_evaluations.ui into layout: {e}", flush=True)

        # Replace 'Presets' and 'General' (left scroll top) with presets_general.ui and report_configs.ui (robust)
        try:
            pg_ui_path = self.this_file.parent / "presets_general.ui"
            rc_ui_path = self.this_file.parent / "report_configs.ui"
            pg_widget = uic.loadUi(str(pg_ui_path)) if pg_ui_path.exists() else None
            rc_widget = uic.loadUi(str(rc_ui_path)) if rc_ui_path.exists() else None

            inserted_pg = False
            inserted_rc = False

            main_layout = self.findChild(QtWidgets.QVBoxLayout, "mainLayout")
            if main_layout:
                # Clean any old remnants (defensive)
                for obj_name in ("groupGeneral", "groupGeneral_2"):
                    w = self.findChild(QtWidgets.QGroupBox, obj_name)
                    if w:
                        try:
                            main_layout.removeWidget(w)
                        except Exception:
                            pass
                        w.setParent(None)
                        w.deleteLater()
                if pg_widget:
                    main_layout.insertWidget(0, pg_widget)
                    inserted_pg = True
                if rc_widget:
                    main_layout.insertWidget(1, rc_widget)
                    inserted_rc = True
            else:
                # Fallback: attach to scrollAreaWidgetContents
                sac = self.findChild(QtWidgets.QWidget, "scrollAreaWidgetContents")
                if sac:
                    vbox = sac.layout()
                    if vbox is None:
                        vbox = QtWidgets.QVBoxLayout(sac)
                        vbox.setContentsMargins(0, 0, 0, 0)
                        vbox.setSpacing(2)
                    if pg_widget:
                        vbox.insertWidget(0, pg_widget)
                        inserted_pg = True
                    if rc_widget:
                        vbox.insertWidget(1, rc_widget)
                        inserted_rc = True
            print(f"[DEBUG] presets_general inserted={inserted_pg}, report_configs inserted={inserted_rc}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed to load left panels into scroll area: {e}", flush=True)

        # Cache widgets still managed by MainWindow
        self.sliderIterations_2: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderIterations_2")
        self.sliderMasterQuality: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderIterations") # Master quality slider (Presets)

        # Path widgets (line edits + browse/open buttons)
        self.lineInputFolder: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineInputFolder")
        self.btnBrowseInputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseInputFolder")
        self.btnOpenInputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenInputFolder")

        self.lineOutputFolder: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineOutputFolder")
        self.btnBrowseOutputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseOutputFolder")
        self.btnOpenOutputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenOutputFolder")

        self.lineInstructionsFile: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineInstructionsFile")
        self.btnBrowseInstructionsFile: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseInstructionsFile")
        self.btnOpenInstructionsFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenInstructionsFolder")

        # Guidelines file widgets
        self.lineGuidelinesFile: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineGuidelinesFile")
        self.btnBrowseGuidelinesFile: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseGuidelinesFile")
        self.btnOpenGuidelinesFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenGuidelinesFolder")
        self.checkFollowGuidelines: QtWidgets.QCheckBox = self.findChild(QtWidgets.QCheckBox, "checkFollowGuidelines")

        # Buttons
        self.btn_write_configs: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "pushButton_3")  # "Write to Configs"
        self.btn_run: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnAction7")  # "Run"

        # Checkable groupboxes (remaining in main window for global control)
        self.groupEvaluation: Optional[QtWidgets.QGroupBox] = self.findChild(QtWidgets.QGroupBox, "groupEvaluation")
        self.groupEvaluation2: Optional[QtWidgets.QGroupBox] = self.findChild(QtWidgets.QGroupBox, "groupEvaluation2")

        # Instantiate UI Handlers
        self.gptr_ma_handler = GPTRMA_UI_Handler(self)
        self.fpf_handler = FPF_UI_Handler(self)

        # Connect general signals (remaining in MainWindow)
        if self.btn_write_configs:
            self.btn_write_configs.clicked.connect(self.on_write_clicked)
        if self.btn_run:
            self.btn_run.clicked.connect(self.on_run_clicked)
        if self.sliderMasterQuality:
            self.sliderMasterQuality.valueChanged.connect(self.on_master_quality_changed)
        
        # Connect signals for handlers
        self.gptr_ma_handler.connect_signals()
        self.fpf_handler.connect_signals()

        # Ensure FPF provider/model dropdowns are populated in the main UI.
        # Some UI loading sequences can make handler lookups unreliable, so populate directly here.
        try:
            combo_provider = self.findChild(QtWidgets.QComboBox, "comboFPFProvider")
            combo_model = self.findChild(QtWidgets.QComboBox, "comboFPFModel")
            if combo_provider is not None:
                # Discover FPF providers dynamically from FilePromptForge/providers
                prov_map = {}
                try:
                    prov_map = self.fpf_handler._discover_fpf_providers() if getattr(self, "fpf_handler", None) else {}
                except Exception:
                    prov_map = {}
                providers = sorted(prov_map.keys())
                try:
                    combo_provider.clear()
                except Exception:
                    pass
                if providers:
                    try:
                        combo_provider.addItems(providers)
                        # populate models for first provider if model combo is present
                        if combo_model is not None:
                            try:
                                first_path = prov_map.get(providers[0], "")
                                models = self.fpf_handler._load_allowed_models(first_path) if getattr(self, "fpf_handler", None) else []
                                combo_model.clear()
                                if models:
                                    combo_model.addItems(models)
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            # non-fatal; existing handler logic still attempts population
            pass

        # Connect live-updating metric for "Total Reports":
        # - Cache the label widget used to display total reports (named "label_2" in the .ui file)
        # - Wire sliderIterations_2 and all report-type/group provider groupboxes to recompute total
        try:
            self.labelTotalReports = self.findChild(QtWidgets.QLabel, "label_2")
        except Exception:
            self.labelTotalReports = None

        # Connect the main "general iterations" slider to recalc total on change
        if self.sliderIterations_2:
            try:
                self.sliderIterations_2.valueChanged.connect(self._compute_total_reports)
            except Exception:
                pass

        # Connect exactly the eight report-type groupboxes so toggling them recomputes the total.
        report_groupbox_names = [
            ("fpf", getattr(self.fpf_handler, "groupProvidersFPF", None)),
            ("gptr", getattr(self.gptr_ma_handler, "groupProvidersGPTR", None)),
            ("dr", getattr(self.gptr_ma_handler, "groupProvidersDR", None)),
            ("ma", getattr(self.gptr_ma_handler, "groupProvidersMA", None)),
            ("groupAdditionalModel", self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel")),
            ("groupAdditionalModel2", self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel2")),
            ("groupAdditionalModel3", self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel3")),
            ("groupAdditionalModel4", self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel4")),
        ]
        for name, gb in report_groupbox_names:
            try:
                if gb:
                    gb.toggled.connect(self._compute_total_reports)
            except Exception:
                pass

        # Bottom toolbar button connections (wire UI buttons to handlers or local methods)
        # Note: objectNames are taken from config_sliders.ui
        try:
            btn = self.findChild(QtWidgets.QPushButton, "pushButton_2")  # Download and Install
            if btn:
                btn.clicked.connect(self.on_download_and_install)
        except Exception:
            pass
        try:
            btn = self.findChild(QtWidgets.QPushButton, "btnOpenPMConfig")  # Open PM Config (file)
            if btn:
                btn.clicked.connect(self.on_open_pm_config)
        except Exception:
            pass
        try:
            btn = self.findChild(QtWidgets.QPushButton, "btnAction8")  # Open .env
            if btn:
                btn.clicked.connect(self.on_open_env)
        except Exception:
            pass
        try:
            btn = self.findChild(QtWidgets.QPushButton, "pushButton")  # Install .env
            if btn:
                btn.clicked.connect(self.on_install_env)
        except Exception:
            pass
        # on_open_gptr_config and on_open_fpf_config and on_open_ma_config are now handled by respective UI handlers
        try:
            btn = self.findChild(QtWidgets.QPushButton, "btnAction4")  # Load Preset
            if btn:
                btn.clicked.connect(self.on_load_preset)
        except Exception:
            pass
        try:
            btn = self.findChild(QtWidgets.QPushButton, "btnAction5")  # Save Preset
            if btn:
                btn.clicked.connect(self.on_save_preset)
        except Exception:
            pass
        try:
            btn = self.findChild(QtWidgets.QPushButton, "btnAction6")  # Run One File
            if btn:
                btn.clicked.connect(self.on_run_one_file)
        except Exception:
            pass

        # Connect path browse/open buttons
        if self.btnBrowseInputFolder:
            self.btnBrowseInputFolder.clicked.connect(self.on_browse_input_folder)
        if self.btnOpenInputFolder:
            self.btnOpenInputFolder.clicked.connect(self.on_open_input_folder)
        if self.btnBrowseOutputFolder:
            self.btnBrowseOutputFolder.clicked.connect(self.on_browse_output_folder)
        if self.btnOpenOutputFolder:
            self.btnOpenOutputFolder.clicked.connect(self.on_open_output_folder)
        if self.btnBrowseInstructionsFile:
            self.btnBrowseInstructionsFile.clicked.connect(self.on_browse_instructions_file)
        if self.btnOpenInstructionsFolder:
            self.btnOpenInstructionsFolder.clicked.connect(self.on_open_instructions_folder)
        # Guidelines browse/open
        if getattr(self, "btnBrowseGuidelinesFile", None):
            self.btnBrowseGuidelinesFile.clicked.connect(self.on_browse_guidelines_file)
        if getattr(self, "btnOpenGuidelinesFolder", None):
            self.btnOpenGuidelinesFolder.clicked.connect(self.on_open_guidelines_folder)

        # Connect groupbox toggles (fpf, gptr, dr, ma already connected in their handlers)
        if self.groupEvaluation:
            self.groupEvaluation.toggled.connect(lambda v, k="evaluation": self.on_groupbox_toggled(k, v))
        if self.groupEvaluation2:
            self.groupEvaluation2.toggled.connect(lambda v, k="pairwise": self.on_groupbox_toggled(k, v))

        # Set up dynamic readouts that show current slider value next to max label
        self._setup_slider_readouts()

        # Initial load (configs -> UI)
        self.load_current_values()
        # Refresh readouts to reflect initial values
        self._refresh_all_readouts()
        # Initialize total reports label based on current slider/groupbox state
        try:
            self._compute_total_reports()
        except Exception:
            pass

    def show_error(self, text: str) -> None:
        show_error(text)

    def show_info(self, text: str) -> None:
        show_info(text)

    def load_current_values(self) -> None:
        """
        Read config files and set slider values accordingly.
        """
        try:
            # process_markdown/config.yaml
            y = {}
            try:
                y = read_yaml(self.pm_config_yaml)
            except FileNotFoundError:
                print(f"[INFO] {self.pm_config_yaml} not found, using defaults.")
            except Exception as e:
                print(f"[WARN] Could not load {self.pm_config_yaml}: {e}", flush=True)

            iterations_default = int(y.get("iterations_default", 1) or 1)
            if self.sliderIterations_2:
                self.sliderIterations_2.setValue(clamp_int(iterations_default, self.sliderIterations_2.minimum(), self.sliderIterations_2.maximum()))

            # Set default paths if not loaded from config
            if self.lineInputFolder and not self.lineInputFolder.text():
                self.lineInputFolder.setText(str(self.pm_dir / "test" / "mdinputs"))
            if self.lineOutputFolder and not self.lineOutputFolder.text():
                self.lineOutputFolder.setText(str(self.pm_dir / "test" / "mdoutputs"))
            if self.lineInstructionsFile and not self.lineInstructionsFile.text():
                self.lineInstructionsFile.setText(str(self.pm_dir / "test" / "instructions.txt"))
            # Guidelines file populates from config.yaml if present, otherwise no strong default
            if getattr(self, "lineGuidelinesFile", None):
                gf = y.get("guidelines_file")
                if gf:
                    self.lineGuidelinesFile.setText(str(gf))
                elif not self.lineGuidelinesFile.text():
                    # Set a default specific to the project's structure if it exists
                    default_guidelines_path = self.pm_dir / "test" / "report must be in spanish.txt"
                    if default_guidelines_path.exists():
                        self.lineGuidelinesFile.setText(str(default_guidelines_path))

            # Load Additional Models (if present) from config.yaml and apply to UI
            try:
                additional = y.get("additional_models", []) or []
                # UI element defs in order for up to 4 additional model slots
                slots = [
                    ("groupAdditionalModel", "comboAdditionalType", "comboAdditionalProvider", "comboAdditionalModel"),
                    ("groupAdditionalModel2", "comboAdditionalType2", "comboAdditionalProvider2", "comboAdditionalModel2"),
                    ("groupAdditionalModel3", "comboAdditionalType3", "comboAdditionalProvider3", "comboAdditionalModel3"),
                    ("groupAdditionalModel4", "comboAdditionalType4", "comboAdditionalProvider4", "comboAdditionalModel4"),
                ]
                for idx, slot in enumerate(slots):
                    gb_name, combo_type_name, combo_provider_name, combo_model_name = slot
                    gb = self.findChild(QtWidgets.QGroupBox, gb_name)
                    combo_type = self.findChild(QtWidgets.QComboBox, combo_type_name)
                    combo_provider = self.findChild(QtWidgets.QComboBox, combo_provider_name)
                    combo_model = self.findChild(QtWidgets.QComboBox, combo_model_name)
                    if idx < len(additional):
                        entry = additional[idx] or {}
                        rtype = entry.get("type", "")
                        provider = entry.get("provider", "")
                        model = entry.get("model", "")
                        # Map canonical types back to UI display text where needed
                        type_display = None
                        if rtype == "fpf":
                            type_display = "FPF (FilePromptForge)"
                        elif rtype == "gptr":
                            type_display = "GPTR (GPT Researcher)"
                        elif rtype == "dr":
                            type_display = "DR (Deep Research)"
                        elif rtype == "ma":
                            type_display = "MA (Multi-Agent Task)"
                        elif rtype == "all":
                            type_display = "All Selected Types"
                        # Set groupbox checked and combobox selections
                        try:
                            if gb:
                                gb.setChecked(True)
                        except Exception:
                            pass
                        if combo_type and type_display:
                            _set_combobox_text(combo_type, type_display)
                        if combo_provider and provider:
                            _set_combobox_text(combo_provider, provider)
                        if combo_model and model:
                            _set_combobox_text(combo_model, model)
                    else:
                        # No config entry for this slot; ensure unchecked
                        try:
                            if gb:
                                gb.setChecked(False)
                        except Exception:
                            pass
            except Exception:
                # Non-fatal: fail silently to avoid blocking UI load
                pass

            self.fpf_handler.load_values()
            self.gptr_ma_handler.load_values()

            # Set checked state for main provider groupboxes based on iterations in config.yaml
            try:
                iterations = y.get("iterations", {}) if isinstance(y, dict) else {}
                def _is_enabled(k):
                    try:
                        return int(iterations.get(k, 1)) != 0
                    except Exception:
                        return True
                if getattr(self.fpf_handler, "groupProvidersFPF", None) is not None:
                    try:
                        self.fpf_handler.groupProvidersFPF.setChecked(bool(_is_enabled("fpf")))
                    except Exception:
                        pass
                if getattr(self.gptr_ma_handler, "groupProvidersGPTR", None) is not None:
                    try:
                        self.gptr_ma_handler.groupProvidersGPTR.setChecked(bool(_is_enabled("gptr")))
                    except Exception:
                        pass
                if getattr(self.gptr_ma_handler, "groupProvidersDR", None) is not None:
                    try:
                        self.gptr_ma_handler.groupProvidersDR.setChecked(bool(_is_enabled("dr")))
                    except Exception:
                        pass
                if getattr(self.gptr_ma_handler, "groupProvidersMA", None) is not None:
                    try:
                        self.gptr_ma_handler.groupProvidersMA.setChecked(bool(_is_enabled("ma")))
                    except Exception:
                        pass
            except Exception:
                pass

            # Load provider/model from individual config files and apply to comboboxes (only remaining handlers)
            try:
                # GPTR default.py
                try:
                    t = read_text(self.gptr_default_py)
                    def _extract_str(key):
                        m = re.search(rf'["\']{key}["\']\s*:\s*["\']([^"\']+)["\']', t)
                        return m.group(1) if m else None
                    smart = _extract_str("SMART_LLM")
                    strategic = _extract_str("STRATEGIC_LLM")
                    gmodel = smart or strategic
                    if gmodel and getattr(self.gptr_ma_handler, "comboGPTRModel", None):
                        _set_combobox_text(self.gptr_ma_handler.comboGPTRModel, str(gmodel))
                except Exception:
                    pass
                # MA task.json
                try:
                    j = read_json(self.ma_task_json)
                    ma_model = j.get("model")
                    if ma_model and getattr(self.gptr_ma_handler, "comboMAModel", None):
                        _set_combobox_text(self.gptr_ma_handler.comboMAModel, str(ma_model))
                except Exception:
                    pass

                # LOG what was loaded and current combobox states for debugging
                try:
                    # GPTR
                    gptr_smart = None
                    if 't' in locals():
                        m = re.search(r'"SMART_LLM"\s*:\s*"([^"]+)"', t)
                        gptr_smart = m.group(1) if m else None
                    print(f"[GUI INIT] GPTR SMART_LLM from file: {gptr_smart!r}, GPTR model combobox: {getattr(self.gptr_ma_handler, 'comboGPTRModel', None).currentText() if getattr(self.gptr_ma_handler, 'comboGPTRModel', None) else None}", flush=True)

                    # MA
                    ma_model_check = j.get("model") if 'j' in locals() else None
                    print(f"[GUI INIT] MA model from task.json: {ma_model_check!r}, MA model combobox: {getattr(self.gptr_ma_handler, 'comboMAModel', None).currentText() if getattr(self.gptr_ma_handler, 'comboMAModel', None) else None}", flush=True)
                except Exception:
                    pass

                # Populate Additional Model slots with sensible defaults from the loaded provider sections
                # If user hasn't configured additional_models in config.yaml, pre-fill the provider/model
                # combos for each additional slot from the corresponding handler comboboxes.
                try:
                    add_slots = [
                        ("groupAdditionalModel", "comboAdditionalType", "comboAdditionalProvider", "comboAdditionalModel"),
                        ("groupAdditionalModel2", "comboAdditionalType2", "comboAdditionalProvider2", "comboAdditionalModel2"),
                        ("groupAdditionalModel3", "comboAdditionalType3", "comboAdditionalProvider3", "comboAdditionalModel3"),
                        ("groupAdditionalModel4", "comboAdditionalType4", "comboAdditionalProvider4", "comboAdditionalModel4"),
                    ]
                    for gb_name, combo_type_name, combo_provider_name, combo_model_name in add_slots:
                        combo_type = self.findChild(QtWidgets.QComboBox, combo_type_name)
                        combo_provider = self.findChild(QtWidgets.QComboBox, combo_provider_name)
                        combo_model = self.findChild(QtWidgets.QComboBox, combo_model_name)
                        # Only pre-fill when both provider and model are empty (avoid overwriting explicit config.yaml entries)
                        try:
                            provider_empty = not combo_provider or not combo_provider.currentText().strip()
                            model_empty = not combo_model or not combo_model.currentText().strip()
                        except Exception:
                            provider_empty = model_empty = False
                        if not (provider_empty and model_empty):
                            continue
                        if not combo_type:
                            continue
                        ttxt = combo_type.currentText() or ""

                        # GPTR
                        if "GPTR" in ttxt and getattr(self.gptr_ma_handler, "comboGPTRProvider", None):
                            try:
                                _set_combobox_text(combo_provider, self.gptr_ma_handler.comboGPTRProvider.currentText())
                                _set_combobox_text(combo_model, self.gptr_ma_handler.comboGPTRModel.currentText() if getattr(self.gptr_ma_handler, "comboGPTRModel", None) else "")
                            except Exception:
                                pass
                        # DR
                        elif "DR" in ttxt and getattr(self.gptr_ma_handler, "comboDRProvider", None):
                            try:
                                _set_combobox_text(combo_provider, self.gptr_ma_handler.comboDRProvider.currentText())
                                _set_combobox_text(combo_model, self.gptr_ma_handler.comboDRModel.currentText() if getattr(self.gptr_ma_handler, "comboDRModel", None) else "")
                            except Exception:
                                pass
                        # MA
                        elif "MA" in ttxt and getattr(self.gptr_ma_handler, "comboMAProvider", None):
                            try:
                                _set_combobox_text(combo_provider, self.gptr_ma_handler.comboMAProvider.currentText())
                                _set_combobox_text(combo_model, self.gptr_ma_handler.comboMAModel.currentText() if getattr(self.gptr_ma_handler, "comboMAModel", None) else "")
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                pass

        except Exception as e:
            show_error(f"Failed to initialize UI from configs: {e}")

    def gather_values(self) -> Dict[str, Any]:
        """
        Collect slider values and other UI selections from UI.
        Returns a nested dict with keys for config, providers and enable flags.
        """
        vals: Dict[str, Any] = {}

        # General (config.yaml)
        if self.sliderIterations_2:
            vals["iterations_default"] = int(self.sliderIterations_2.value())

        # Paths (config.yaml)
        if self.lineInputFolder:
            vals["input_folder"] = str(self.lineInputFolder.text())
        if self.lineOutputFolder:
            vals["output_folder"] = str(self.lineOutputFolder.text())
        if self.lineInstructionsFile:
            vals["instructions_file"] = str(self.lineInstructionsFile.text())

        # Guidelines file (config.yaml) and follow_guidelines checkbox (task.json)
        if getattr(self, "lineGuidelinesFile", None):
            vals["guidelines_file"] = str(self.lineGuidelinesFile.text())
        if getattr(self, "checkFollowGuidelines", None):
            vals["follow_guidelines"] = bool(self.checkFollowGuidelines.isChecked())
        
        # Merge values from handlers
        # Deep-merge 'providers' so FPF providers aren't overwritten by GPTR/DR providers
        _fpf_vals = self.fpf_handler.gather_values()
        _gptr_vals = self.gptr_ma_handler.gather_values()

        _providers: Dict[str, Any] = {}
        try:
            if isinstance(_fpf_vals.get("providers"), dict):
                _providers.update(_fpf_vals["providers"])
            if isinstance(_gptr_vals.get("providers"), dict):
                _providers.update(_gptr_vals["providers"])
        except Exception:
            pass

        # Remove providers from child dicts to avoid shallow overwrite
        if isinstance(_fpf_vals, dict) and "providers" in _fpf_vals:
            try:
                del _fpf_vals["providers"]
            except Exception:
                pass
        if isinstance(_gptr_vals, dict) and "providers" in _gptr_vals:
            try:
                del _gptr_vals["providers"]
            except Exception:
                pass

        # Now apply remaining keys
        vals.update(_fpf_vals)
        vals.update(_gptr_vals)

        # Reattach merged providers if any
        if _providers:
            vals["providers"] = _providers

        # Enable flags from checkable groupboxes (if unchecked, intent is to disable)
        # These are collected from the main window's groupboxes
        enables: Dict[str, bool] = {}
        if self.groupEvaluation is not None:
            enables["evaluation"] = bool(self.groupEvaluation.isChecked())
        if self.groupEvaluation2 is not None:
            enables["pairwise"] = bool(self.groupEvaluation2.isChecked())

        # Merge enable flags from handlers
        # Assuming handlers also return 'enable' in their gather_values
        if "enable" in vals:
            enables.update(vals["enable"])
            del vals["enable"] # Remove the nested enable from vals, it's merged now

        if enables:
            vals["enable"] = enables

        # Provider/model selections are UI-only and are NOT persisted to process_markdown/config.yaml.
        # We intentionally do not collect or write providers/models into vals for config.yaml.
        # If we want to remember providers/models, use presets.yaml (separate persistence).

        # --- Additional models (UI-defined extra runs) ---
        # Gather any checked "Additional Model" groupboxes. Each additional entry contains:
        #   - type: one of "fpf", "gptr", "dr", "ma" or "all"
        #   - provider: provider string (e.g. "google", "openai", "openrouter")
        #   - model: model string (e.g. "gpt-4.1", "gemini-2.5-flash")
        additional_models = []
        add_defs = [
            ("groupAdditionalModel", "comboAdditionalType", "comboAdditionalProvider", "comboAdditionalModel"),
            ("groupAdditionalModel2", "comboAdditionalType2", "comboAdditionalProvider2", "comboAdditionalModel2"),
            ("groupAdditionalModel3", "comboAdditionalType3", "comboAdditionalProvider3", "comboAdditionalModel3"),
            ("groupAdditionalModel4", "comboAdditionalType4", "comboAdditionalProvider4", "comboAdditionalModel4"),
        ]
        type_map = {
            "FPF (FilePromptForge)": "fpf",
            "GPTR (GPT Researcher)": "gptr",
            "DR (Deep Research)": "dr",
            "MA (Multi-Agent Task)": "ma",
            "All Selected Types": "all",
            "Both Evaluations": "all"
        }
        for gb_name, combo_type_name, combo_provider_name, combo_model_name in add_defs:
            try:
                gb = self.findChild(QtWidgets.QGroupBox, gb_name)
                if not gb or not getattr(gb, "isChecked", lambda: False)():
                    continue
                combo_type = self.findChild(QtWidgets.QComboBox, combo_type_name)
                combo_provider = self.findChild(QtWidgets.QComboBox, combo_provider_name)
                combo_model = self.findChild(QtWidgets.QComboBox, combo_model_name)
                rtype_text = combo_type.currentText() if combo_type else ""
                rtype = type_map.get(rtype_text, None)
                provider = combo_provider.currentText() if combo_provider else ""
                model = combo_model.currentText() if combo_model else ""
                if rtype:
                    additional_models.append({"type": rtype, "provider": provider, "model": model})
            except Exception:
                continue

        if additional_models:
            vals["additional_models"] = additional_models

        return vals

    def write_configs(self, vals: Dict[str, Any]) -> None:
        """
        Persist collected slider values into the underlying config files.
        """
        # process_markdown/config.yaml
        try:
            y = read_yaml(self.pm_config_yaml)

            # Paths
            if "input_folder" in vals:
                y["input_folder"] = vals["input_folder"]
            if "output_folder" in vals:
                y["output_folder"] = vals["output_folder"]
            if "instructions_file" in vals:
                y["instructions_file"] = vals["instructions_file"]
            # Guidelines file path (optional)
            try:
                if "guidelines_file" in vals:
                    gf = vals.get("guidelines_file")
                    if gf:
                        y["guidelines_file"] = gf
                    else:
                        if "guidelines_file" in y:
                            del y["guidelines_file"]
            except Exception:
                pass

            # iterations_default
            y["iterations_default"] = int(vals.get("iterations_default", y.get("iterations_default", 1) or 1))

            # Enable/disable iteration flags and set explicit per-report-type iteration counts.
            # For each report type: if disabled -> 0, if enabled -> set to iterations_default.
            it = y.get("iterations", {})
            if not isinstance(it, dict):
                it = {}
            en = vals.get("enable", {})
            if not isinstance(en, dict):
                en = {}
            for rpt in ("fpf", "gptr", "dr", "ma"):
                # Use directly from en if available, otherwise default to True
                is_enabled = en.get(rpt, True) # if a handler didn't return an enable for its groupbox, assume it's enabled
                if not is_enabled:
                    it[rpt] = 0
                else:
                    # Use iterations_default when enabled (or preserve existing non-zero)
                    it[rpt] = int(vals.get("iterations_default", it.get(rpt) or 1))
            y["iterations"] = it


            # providers section are UI-only and are normally not written to pm_config_yaml
            # (handled by presets if needed). However we persist the GUI-controlled
            # additional_models list into config.yaml so the runner can pick it up.
            try:
                if "additional_models" in vals and vals["additional_models"]:
                    y["additional_models"] = vals["additional_models"]
                else:
                    # Remove any lingering key if GUI has none checked
                    if "additional_models" in y:
                        del y["additional_models"]
            except Exception:
                # Non-fatal; continue to write config
                pass

            write_yaml(self.pm_config_yaml, y)

            # Detailed console output: list each written variable and destination file
            try:
                log_lines = []
                # Paths
                for k in ("input_folder", "output_folder", "instructions_file"):
                    if k in vals:
                        log_lines.append(f"Wrote {k} = {vals[k]!r} -> {self.pm_config_yaml}")
                # iterations_default
                if "iterations_default" in vals:
                    log_lines.append(f"Wrote iterations_default = {vals['iterations_default']} -> {self.pm_config_yaml}")
                # enable flags
                for k, v in vals.get("enable", {}).items():
                    log_lines.append(f"Wrote enable.{k} = {bool(v)} -> {self.pm_config_yaml}")
                if log_lines:
                    print("[OK] Wrote to", self.pm_config_yaml)
                    for ln in log_lines:
                        print("  -", ln)
                else:
                    print(f"[OK] Wrote {self.pm_config_yaml} (no detailed keys found in vals)", flush=True)
            except Exception:
                print(f"[OK] Wrote {self.pm_config_yaml}", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to write {self.pm_config_yaml}: {e}")

        # Delegate writes to handlers
        self.fpf_handler.write_configs(vals)
        self.gptr_ma_handler.write_configs(vals)


    def on_write_clicked(self) -> None:
        try:
            vals = self.gather_values()
            self.write_configs(vals)
            show_info("Configurations have been written successfully.")
        except Exception as e:
            show_error(str(e))

    def on_run_clicked(self) -> None:
        if self.btn_run:
            self.btn_run.setEnabled(False)
        try:
            vals = self.gather_values()
            self.write_configs(vals)
        except Exception as e:
            if self.btn_run:
                self.btn_run.setEnabled(True)
            show_error(str(e))
            return

        # Launch generate.py in a thread so GUI stays responsive
        self.runner_thread = RunnerThread(self.pm_dir, self.generate_py, self)
        self.runner_thread.finished_ok.connect(self._on_generate_finished)
        self.runner_thread.start()

    def _on_generate_finished(self, ok: bool, code: int, message: str) -> None:
        if self.btn_run:
            self.btn_run.setEnabled(True)
        if ok:
            show_info(message)
        else:
            show_error(message)


    def on_master_quality_changed(self, value: int) -> None:
        """
        When the 'Master Quality' slider changes, proportionally adjust all other sliders
        based on their own min/max ranges. This only affects in-UI values; config files
        are still written only on 'Write to Configs' or 'Run'.
        """
        try:
            s = getattr(self, "sliderMasterQuality", None)
            if not s:
                return
            smin, smax = s.minimum(), s.maximum()
            if smax <= smin:
                percent = 0.0
            else:
                percent = (float(value) - float(smin)) / float(smax - smin)
                if percent < 0.0:
                    percent = 0.0
                if percent > 1.0:
                    percent = 1.0
            self._apply_master_quality(percent)
        except Exception as e:
            print(f"[WARN] Master quality change failed: {e}", flush=True)

    def _apply_master_quality(self, percent: float) -> None:
        """
        Apply proportional scaling to all controlled sliders using the given percent in [0,1].
        """
        # Sliders now belong to handlers, need to access via handlers
        self.gptr_ma_handler.apply_master_quality_to_sliders(percent)
        self.fpf_handler.apply_master_quality_to_sliders(percent)

        # After programmatic changes, refresh value readouts since signals are blocked
        self._refresh_all_readouts()

    def _display_value_for(self, slider_name: str, value: int) -> str:
        """
        Convert a slider integer value to display text.
        Temperature uses mapped float 0.00-1.00; others show integer.
        """
        if slider_name == "sliderTemperature":
            return f"{temp_from_slider(value):.2f}"
        return str(int(value))

    def _setup_slider_readouts(self) -> None:
        """
        Bind valueChanged handlers for each slider to update the 'max' label to show
        'current / max' while the min label remains as-is. This provides live feedback.
        """
        self._readout_map = [
            ("sliderIterations", "labelIterationsMin", "labelIterationsMax"),
            ("sliderIterations_2", "labelIterationsMin_2", "labelIterationsMax_2"),
            # Handler-specific sliders will need to be added to their respective handlers' _readout_map
            # or directly updated by handlers. MainWindow only cares about its own sliders now.
            ("sliderGroundingMaxResults", "labelGroundingMaxResultsMin", "labelGroundingMaxResultsMax"),
            ("sliderGoogleMaxTokens", "labelGoogleMaxTokensMin", "labelGoogleMaxTokensMax"),
            ("sliderFastTokenLimit", "labelFastTokenLimitMin", "labelFastTokenLimitMax"),
            ("sliderSmartTokenLimit", "labelSmartTokenLimitMin", "labelSmartTokenLimitMax"),
            ("sliderStrategicTokenLimit", "labelStrategicTokenLimitMin", "labelStrategicTokenLimitMax"),
            ("sliderBrowseChunkMaxLength", "labelBrowseChunkMaxLengthMin", "labelBrowseChunkMaxLengthMax"),
            ("sliderSummaryTokenLimit", "labelSummaryTokenLimitMin", "labelSummaryTokenLimitMax"),
            ("sliderTemperature", "labelTemperatureMin", "labelTemperatureMax"),
            ("sliderMaxSearchResultsPerQuery", "labelMaxSearchResultsPerQueryMin", "labelMaxSearchResultsPerQueryMax"),
            ("sliderTotalWords", "labelTotalWordsMin", "labelTotalWordsMax"),
            ("sliderMaxIterations", "labelMaxIterationsMin", "labelMaxIterationsMax"),
            ("sliderMaxSubtopics", "labelMaxSubtopicsMin", "labelMaxSubtopicsMax"),
            ("sliderDeepResearchBreadth", "labelDeepResearchBreadthMin", "labelDeepResearchBreadthMax"),
            ("sliderDeepResearchDepth", "labelDeepResearchDepthMin", "labelDeepResearchDepthMax"),
            ("sliderMaxSections", "labelMaxSectionsMin", "labelMaxSectionsMax"),
        ]
        
        # Consolidate slider finding logic to account for sliders in handlers
        all_sliders = []
        if self.sliderIterations_2:
            all_sliders.append((self.sliderIterations_2, "sliderIterations_2"))
        if self.sliderMasterQuality:
            all_sliders.append((self.sliderMasterQuality, "sliderIterations")) # This is the same name as in the map

        # Add sliders from handlers
        for handler in [self.gptr_ma_handler, self.fpf_handler]:
            for attr_name in vars(handler):
                if attr_name.startswith("slider") and isinstance(getattr(handler, attr_name), QtWidgets.QSlider):
                    all_sliders.append((getattr(handler, attr_name), attr_name))

        for slider_obj, slider_name in all_sliders:
            # Look up the actual name from _readout_map to ensure it matches
            map_entry = next((entry for entry in self._readout_map if entry[0] == slider_name), None)
            if map_entry:
                slider_obj.valueChanged.connect(lambda v, sn=map_entry[0]: self._update_slider_readout(sn))

    def _update_slider_readout(self, slider_name: str) -> None:
        """
        Update the 'max' label to show 'current / max'. For temperature, current shows 0.00-1.00,
        and max shows 1.0.
        """
        # First, try to find the slider in MainWindow's own attributes.
        slider = self.findChild(QtWidgets.QSlider, slider_name)
        
        # If not found, try to find it in the handlers
        if slider is None:
            for handler in [self.gptr_ma_handler, self.fpf_handler]:
                try:
                    # Access the slider object directly from handler's attributes
                    possible_slider = getattr(handler, slider_name, None)
                    if isinstance(possible_slider, QtWidgets.QSlider):
                        slider = possible_slider
                        break
                except AttributeError:
                    continue # Not found in this handler

        if slider is None:
            # Fallback if slider widget is not found anywhere
            # print(f"[WARN] Slider widget '{slider_name}' not found for readout update.", flush=True)
            return

        # Find associated max label by name from mapping (still uses main window to find labels)
        max_label_name = None
        for s_f_name, _min_name, max_name in getattr(self, "_readout_map", []):
            if s_f_name == slider_name:
                max_label_name = max_name
                break
        if not max_label_name:
            # print(f"[WARN] Max label for slider '{slider_name}' not found in _readout_map.", flush=True)
            return
        max_label = self.findChild(QtWidgets.QLabel, max_label_name)
        if max_label is None:
            # print(f"[WARN] Max label widget '{max_label_name}' not found.", flush=True)
            return

        current_disp = self._display_value_for(slider_name, int(slider.value()))
        # Special case for Temperature from gptr_ma_ui
        if slider_name == "sliderTemperature":
            max_disp = "1.0"
        else:
            max_disp = str(int(slider.maximum()))
        max_label.setText(f"{current_disp} / {max_disp}")

    def _refresh_all_readouts(self) -> None:
        """
        Call _update_slider_readout for all mapped sliders to sync labels with current values.
        """
        for s_name, _min_name, _max_name in getattr(self, "_readout_map", []):
            self._update_slider_readout(s_name)
    
    def _compute_total_reports(self, _=None) -> None:
        """
        Compute total reports = (general iterations slider) * (number of report-type groupboxes checked).
        Update the label named 'label_2' (cached as self.labelTotalReports) with the computed value.
        The optional parameter is present because this method is connected to signals that pass a boolean/int.
        """
        try:
            # Read iterations
            iterations = 0
            if getattr(self, "sliderIterations_2", None):
                try:
                    iterations = int(self.sliderIterations_2.value())
                except Exception:
                    iterations = 0

            # Candidate groupboxes that represent the eight report-type checkboxes
            groupboxes = [
                getattr(self.fpf_handler, "groupProvidersFPF", None),
                getattr(self.gptr_ma_handler, "groupProvidersGPTR", None),
                getattr(self.gptr_ma_handler, "groupProvidersDR", None),
                getattr(self.gptr_ma_handler, "groupProvidersMA", None),
                self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel"),
                self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel2"),
                self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel3"),
                self.findChild(QtWidgets.QGroupBox, "groupAdditionalModel4"),
            ]

            checked_count = 0
            for gb in groupboxes:
                try:
                    if gb and hasattr(gb, "isChecked") and gb.isChecked():
                        checked_count += 1
                except Exception:
                    continue

            total = int(iterations * checked_count)

            # Update label text. If label not found, silently skip.
            lbl = getattr(self, "labelTotalReports", None) or self.findChild(QtWidgets.QLabel, "label_2")
            if lbl:
                try:
                    lbl.setText(str(total))
                except Exception:
                    lbl.setText(str(total))
        except Exception:
            # Best-effort: do not raise during GUI init/update
            return
    # ---- Additional handlers wired for paths/providers/groupboxes ----
    def on_browse_input_folder(self) -> None:
        """Open a folder dialog and set input folder line edit."""
        try:
            dlg = QtWidgets.QFileDialog(self, "Select Input Folder")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            if dlg.exec_():
                sel = dlg.selectedFiles()
                if sel:
                    path = sel[0]
                    if self.lineInputFolder:
                        self.lineInputFolder.setText(path)
        except Exception as e:
            print(f"[WARN] on_browse_input_folder failed: {e}", flush=True)

    def on_open_input_folder(self) -> None:
        """Open OS explorer at input folder path."""
        try:
            path = None
            if self.lineInputFolder:
                path = self.lineInputFolder.text()
            if not path:
                return
            _open_in_file_explorer(path)
        except Exception as e:
            print(f"[WARN] on_open_input_folder failed: {e}", flush=True)

    def on_browse_output_folder(self) -> None:
        """Open a folder dialog and set output folder line edit."""
        try:
            dlg = QtWidgets.QFileDialog(self, "Select Output Folder")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            if dlg.exec_():
                sel = dlg.selectedFiles()
                if sel:
                    path = sel[0]
                    if self.lineOutputFolder:
                        self.lineOutputFolder.setText(path)
        except Exception as e:
            print(f"[WARN] on_browse_output_folder failed: {e}", flush=True)

    def on_open_output_folder(self) -> None:
        """Open OS explorer at output folder path."""
        try:
            path = None
            if self.lineOutputFolder:
                path = self.lineOutputFolder.text()
            if not path:
                return
            _open_in_file_explorer(path)
        except Exception as e:
            print(f"[WARN] on_open_output_folder failed: {e}", flush=True)

    def on_browse_instructions_file(self) -> None:
        """Open file dialog to pick instructions file."""
        try:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Instructions File", "", "Text Files (*.txt);;All Files (*)")
            if fname:
                if self.lineInstructionsFile:
                    self.lineInstructionsFile.setText(fname)
        except Exception as e:
            print(f"[WARN] on_browse_instructions_file failed: {e}", flush=True)

    def on_open_instructions_folder(self) -> None:
        """Open OS explorer at the folder containing the instructions file."""
        try:
            path = None
            if self.lineInstructionsFile:
                path = self.lineInstructionsFile.text()
            if not path:
                return
            p = Path(path)
            if p.exists():
                _open_in_file_explorer(str(p.parent))
        except Exception as e:
            print(f"[WARN] on_open_instructions_folder failed: {e}", flush=True)

    def on_browse_guidelines_file(self) -> None:
        """Open file dialog to pick guidelines file."""
        try:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Guidelines File", "", "Text Files (*.txt);;All Files (*)")
            if fname:
                if getattr(self, "lineGuidelinesFile", None):
                    self.lineGuidelinesFile.setText(fname)
        except Exception as e:
            print(f"[WARN] on_browse_guidelines_file failed: {e}", flush=True)

    def on_open_guidelines_folder(self) -> None:
        """Open OS explorer at the folder containing the guidelines file."""
        try:
            path = None
            if getattr(self, "lineGuidelinesFile", None):
                path = self.lineGuidelinesFile.text()
            if not path:
                return
            p = Path(path)
            if p.exists():
                _open_in_file_explorer(str(p.parent))
        except Exception as e:
            print(f"[WARN] on_open_guidelines_folder failed: {e}", flush=True)

    def on_groupbox_toggled(self, key: str, checked: bool) -> None:
        """
        Handler when a checkable groupbox is toggled.
        key is one of 'evaluation','pairwise' (fpf, gptr, dr, ma handled by their own handlers now)
        """
        # No immediate side-effect is required here; states are gathered and written by on_write_clicked/on_run_clicked.
        try:
            # Provide lightweight feedback by updating statusbar or printing
            status = f"{key} enabled" if checked else f"{key} disabled"
            try:
                self.statusBar().showMessage(status, 3000)
            except Exception:
                print(f"[INFO] {status}", flush=True)
        except Exception as e:
            print(f"[WARN] on_groupbox_toggled failed: {e}", flush=True)

    # ---- Bottom toolbar handlers ----
    def on_download_and_install(self) -> None:
        """Run download_and_extract.py in background (non-blocking) using DownloadThread."""
        try:
            script = self.pm_dir / "download_and_extract.py"
            if not script.exists():
                show_error(f"download_and_extract.py not found at {script}")
                return
            # Disable the button while running to prevent concurrent starts
            btn = self.findChild(QtWidgets.QPushButton, "pushButton_2")
            if btn:
                btn.setEnabled(False)
            # Start threaded download that streams output to console
            self.download_thread = DownloadThread(self.pm_dir, script, self)
            self.download_thread.finished_ok.connect(self._on_download_finished)
            self.download_thread.start()
            show_info("Download started in background. Check console for output.")
        except Exception as e:
            print(f"[WARN] on_download_and_install failed: {e}", flush=True)

    def _on_download_finished(self, ok: bool, code: int, message: str) -> None:
        """Handler called when DownloadThread finishes."""
        btn = self.findChild(QtWidgets.QPushButton, "pushButton_2")
        if btn:
            btn.setEnabled(True)
        if ok:
            try:
                show_info("Download and extraction completed successfully.")
            except Exception:
                print("[OK] Download and extraction completed successfully.", flush=True)
        else:
            try:
                show_error(f"Download failed: {message}")
            except Exception:
                print(f"[ERROR] Download failed: {message}", flush=True)

    def on_open_env(self) -> None:
        """Open the .env file (or .env.example) with the system default application, if present."""
        try:
            candidate = self.pm_dir / "gpt-researcher" / ".env"
            if not candidate.exists():
                candidate = self.pm_dir / "gpt-researcher" / ".env.example"
            if candidate.exists():
                _open_in_file_explorer(str(candidate))
            else:
                show_info("No .env or .env.example found in gpt-researcher.")
        except Exception as e:
            print(f"[WARN] on_open_env failed: {e}", flush=True)

    def on_install_env(self) -> None:
        """Create .env from .env.example if possible (ask for confirmation)."""
        try:
            example = self.pm_dir / "gpt-researcher" / ".env.example"
            target = self.pm_dir / "gpt-researcher" / ".env"
            if not example.exists():
                show_info("No .env.example found to install from.")
                return
            if target.exists():
                res = QtWidgets.QMessageBox.question(self, "Overwrite .env?", f".env already exists at {target}. Overwrite?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                if res != QtWidgets.QMessageBox.Yes:
                    return
            shutil.copy2(str(example), str(target))
            show_info(f"Installed .env from .env.example to {target}")
        except Exception as e:
            show_error(f"Failed to install .env: {e}")

    def on_open_pm_config(self) -> None:
        """Open process_markdown/config.yaml in default editor (if present)."""
        try:
            if self.pm_config_yaml.exists():
                _open_in_file_explorer(str(self.pm_config_yaml))
            else:
                show_info(f"PM config.yaml not found at {self.pm_config_yaml}")
        except Exception as e:
            print(f"[WARN] on_open_pm_config failed: {e}", flush=True)

    def on_save_preset(self) -> None:
        """Ask for a preset name and save current UI state to presets.yaml."""
        try:
            name, ok = QtWidgets.QInputDialog.getText(self, "Save Preset", "Preset name:")
            if not ok or not name:
                return
            presets_path = self.pm_dir / "presets.yaml"
            presets = {}
            try:
                presets = read_yaml(presets_path)
            except Exception:
                presets = {}
            vals = self.gather_values()
            presets[name] = vals
            write_yaml(presets_path, presets)
            show_info(f"Saved preset '{name}' to {presets_path}")
        except Exception as e:
            show_error(f"Failed to save preset: {e}")

    def on_load_preset(self) -> None:
        """Load a preset from presets.yaml and apply to UI."""
        try:
            presets_path = self.pm_dir / "presets.yaml"
            if not presets_path.exists():
                show_info("No presets found.")
                return
            presets = read_yaml(presets_path)
            if not isinstance(presets, dict) or not presets:
                show_info("No presets available.")
                return
            names = list(presets.keys())
            item, ok = QtWidgets.QInputDialog.getItem(self, "Load Preset", "Select preset:", names, 0, False)
            if not ok or not item:
                return
            data = presets.get(item, {})
            self._apply_preset(data)
            show_info(f"Applied preset '{item}'")
        except Exception as e:
            print(f"[WARN] Failed to load preset: {e}", flush=True)

    def _apply_preset(self, data: Dict[str, Any]) -> None:
        """Apply preset dict to UI widgets (partial, best-effort)."""
        try:
            # Paths
            if "input_folder" in data and self.lineInputFolder:
                self.lineInputFolder.setText(str(data["input_folder"]))
            if "output_folder" in data and self.lineOutputFolder:
                self.lineOutputFolder.setText(str(data["output_folder"]))
            if "instructions_file" in data and self.lineInstructionsFile:
                self.lineInstructionsFile.setText(str(data["instructions_file"]))

            # Providers and enables are handled by their respective handlers
            self.fpf_handler.apply_preset(data)
            self.gptr_ma_handler.apply_preset(data)

            # Sliders (only handle iterations_default in main window)
            if "iterations_default" in data and self.sliderIterations_2:
                self.sliderIterations_2.setValue(int(data["iterations_default"]))
        except Exception as e:
            print(f"[WARN] _apply_preset failed: {e}", flush=True)

    def on_run_one_file(self) -> None:
        """Prompt for a single input file and start generate.py with SINGLE_INPUT_FILE env var."""
        try:
            start_dir = str(self.pm_dir / "test" / "mdinputs")
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select input file to run", start_dir, "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)")
            if not fname:
                return
            cmd = [sys.executable, "-u", str(self.generate_py)]
            env = os.environ.copy()
            env["SINGLE_INPUT_FILE"] = fname
            try:
                proc = subprocess.Popen(cmd, cwd=str(self.pm_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                show_info("Started generate.py for single file in background. Check console for output.")
            except Exception as e:
                show_error(f"Failed to start generate for single file: {e}")
        except Exception as e:
            print(f"[WARN] on_run_one_file failed: {e}", flush=True)

def launch_gui() -> int:
    """
    Launcher entrypoint for the GUI (separate from module import).
    """
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec_()
