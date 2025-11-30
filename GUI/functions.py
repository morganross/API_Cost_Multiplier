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
from .combine_ui import Combine_UI_Handler
from . import model_catalog
from .fpf_concurrency_section import FPFConcurrencySection


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
        self.evaluate_py = self.pm_dir / "evaluate.py"

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
                    try:
                        self.fpf_concurrency_section = FPFConcurrencySection(self)
                        right_layout.addWidget(self.fpf_concurrency_section)
                        try:
                            self.fpf_concurrency_section.concurrencyApplied.connect(self._compute_total_reports)
                        except Exception:
                            pass
                    except Exception:
                        pass
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
                        try:
                            self.fpf_concurrency_section = FPFConcurrencySection(self)
                            v.addWidget(self.fpf_concurrency_section)
                            try:
                                self.fpf_concurrency_section.concurrencyApplied.connect(self._compute_total_reports)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        row_layout.insertWidget(1, container)
                        inserted = True
            print(f"[DEBUG] providers.ui inserted={inserted}", flush=True)
            try:
                self._build_model_checklists()
            except Exception as e:
                print(f"[WARN] Failed to build model checklists: {e}", flush=True)
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
        self.sliderEvaluationIterations: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderEvaluationIterations") # Evaluation iterations slider
        self.sliderPairwiseTopN: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderPairwiseTopN") # Top N to pairwise slider

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

        # Evaluation Output/Export Path widgets
        self.lineEvalOutputFolder: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineEvalOutputFolder")
        self.btnBrowseEvalOutputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseEvalOutputFolder")
        self.btnOpenEvalOutputFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenEvalOutputFolder")

        self.lineEvalExportFolder: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, "lineEvalExportFolder")
        self.btnBrowseEvalExportFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnBrowseEvalExportFolder")
        self.btnOpenEvalExportFolder: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnOpenEvalExportFolder")

        # Auto-run Evaluation Checkbox
        self.checkEvalAutoRun: QtWidgets.QCheckBox = self.findChild(QtWidgets.QCheckBox, "checkEvalAutoRun")

        # Buttons
        self.btn_write_configs: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "pushButton_3")  # "Write to Configs"
        self.btn_run: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnAction7")  # "Run"
        self.btn_evaluate: QtWidgets.QPushButton = self.findChild(QtWidgets.QPushButton, "btnEvaluate")  # "Evaluate"

        # Checkable groupboxes (remaining in main window for global control)
        self.groupEvaluation: Optional[QtWidgets.QGroupBox] = self.findChild(QtWidgets.QGroupBox, "groupEvaluation")
        self.groupEvaluation2: Optional[QtWidgets.QGroupBox] = self.findChild(QtWidgets.QGroupBox, "groupEvaluation2")

        # Instantiate UI Handlers
        self.gptr_ma_handler = GPTRMA_UI_Handler(self)
        self.fpf_handler = FPF_UI_Handler(self)
        self.combine_handler = Combine_UI_Handler(self)

        # Connect general signals (remaining in MainWindow)
        if self.btn_write_configs:
            self.btn_write_configs.clicked.connect(self.on_write_clicked)
        if self.btn_run:
            self.btn_run.clicked.connect(self.on_run_clicked)
        if getattr(self, "btn_evaluate", None):
            self.btn_evaluate.clicked.connect(self.on_evaluate_clicked)
        if self.sliderMasterQuality:
            self.sliderMasterQuality.valueChanged.connect(self.on_master_quality_changed)
        
        # Connect signals for handlers
        self.gptr_ma_handler.connect_signals()
        self.fpf_handler.connect_signals()
        self.combine_handler.setup_ui()
        self.combine_handler.populate_models()

        # Populate Evaluation judges checkbox list from FPF
        try:
            self._populate_eval_model_checkboxes()
        except Exception as e:
            try:
                print(f"[WARN] Failed to populate eval model checkboxes: {e}", flush=True)
            except Exception:
                pass

        # Populate Unified Evaluation controls (Model A/B)
        try:
            self._populate_unified_eval_controls()
        except Exception as e:
            try:
                print(f"[WARN] Failed to populate unified eval controls: {e}", flush=True)
            except Exception:
                pass

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

        # Connect provider groupboxes so toggling them recomputes the total.
        report_groupbox_names = [
            ("fpf", getattr(self.fpf_handler, "groupProvidersFPF", None)),
            ("gptr", getattr(self.gptr_ma_handler, "groupProvidersGPTR", None)),
            ("dr", getattr(self.gptr_ma_handler, "groupProvidersDR", None)),
            ("ma", getattr(self.gptr_ma_handler, "groupProvidersMA", None)),
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

        # Connect new evaluation path browse/open buttons
        if getattr(self, "btnBrowseEvalOutputFolder", None):
            self.btnBrowseEvalOutputFolder.clicked.connect(self.on_browse_eval_output_folder)
        if getattr(self, "btnOpenEvalOutputFolder", None):
            self.btnOpenEvalOutputFolder.clicked.connect(self.on_open_eval_output_folder)
        if getattr(self, "btnBrowseEvalExportFolder", None):
            self.btnBrowseEvalExportFolder.clicked.connect(self.on_browse_eval_export_folder)
        if getattr(self, "btnOpenEvalExportFolder", None):
            self.btnOpenEvalExportFolder.clicked.connect(self.on_open_eval_export_folder)

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
        # Pre-check boxes from config.yaml runs[] and recompute totals
        try:
            self._precheck_runs_from_config()
            self._compute_total_reports()
        except Exception:
            pass

    # ----- Runs-only UI helpers -----
    def _iter_model_checkboxes(self):
        try:
            for cb in self.findChildren(QtWidgets.QCheckBox):
                try:
                    name = cb.objectName() or ""
                    # Runs-only: include providers sections; exclude evaluation judges
                    if name.startswith("check_fpf_") or name.startswith("check_gptr_") or name.startswith("check_dr_") or name.startswith("check_ma_"):
                        yield cb
                except Exception:
                    continue
        except Exception:
            return

    def _build_model_checklists(self) -> None:
        """
        Build provider:model checkbox lists for FPF, GPTR, DR, MA sections using model_catalog.
        """
        try:
            catalog = model_catalog.load_all(self.pm_dir)
            try:
                print(f"[DEBUG][RUNS_UI] catalog sizes: fpf={len(catalog.get('fpf', []))}, gptr={len(catalog.get('gptr', []))}, dr={len(catalog.get('dr', []))}, ma={len(catalog.get('ma', []))}", flush=True)
            except Exception:
                pass
        except Exception as e:
            catalog = {"fpf": [], "gptr": [], "dr": [], "ma": []}
            try:
                print(f"[WARN][RUNS_UI] catalog load failed: {e}", flush=True)
            except Exception:
                pass

        # Prefer targeting the container widgets and fetching/creating their layouts at runtime
        mapping = {
            "fpf": "containerFPFModels",
            "gptr": "containerGPTRModels",
            "dr": "containerDRModels",
            "ma": "containerMAModels",
        }

        for type_key, layout_name in mapping.items():
            try:
                # Try to get the container widget first, then its layout (or create one)
                layout = None
                container = self.findChild(QtWidgets.QWidget, layout_name)
                if container is not None:
                    try:
                        layout = container.layout()
                    except Exception:
                        layout = None
                    if layout is None:
                        try:
                            layout = QtWidgets.QVBoxLayout(container)
                            layout.setContentsMargins(2, 2, 2, 2)
                            layout.setSpacing(2)
                        except Exception:
                            layout = None
                if layout is None:
                    # Fallback to old direct-layout lookup by name (in case UI used named layouts)
                    layout = self.findChild(QtWidgets.QVBoxLayout, layout_name)
                if layout is None:
                    try:
                        print(f"[WARN][RUNS_UI] container/layout not found for type={type_key} name={layout_name}", flush=True)
                    except Exception:
                        pass
                    # Nothing to do for this section
                    continue

                # Clear existing
                try:
                    while layout.count():
                        item = layout.takeAt(0)
                        w = item.widget()
                        if w:
                            w.setParent(None)
                            w.deleteLater()
                except Exception:
                    pass

                # Populate checkboxes
                created = 0
                for pm in catalog.get(type_key, []):
                    try:
                        cb = QtWidgets.QCheckBox(pm)
                        cb.setObjectName(model_catalog.checkbox_object_name(type_key, pm))
                        layout.addWidget(cb)
                        created += 1
                        # Hook into total reports update
                        try:
                            cb.toggled.connect(self._compute_total_reports)
                        except Exception:
                            pass
                    except Exception:
                        continue
                try:
                    print(f"[DEBUG][RUNS_UI] built {created} checkbox(es) for {type_key}", flush=True)
                except Exception:
                    pass
            except Exception:
                continue

    def _precheck_runs_from_config(self) -> None:
        """
        Read config.yaml runs[] and pre-check matching provider:model boxes.
        For MA (model-only), check any box whose text endswith :model.
        Only affects runs sections (fpf/gptr/dr/ma), not evaluation judges.
        """
        try:
            y = read_yaml(self.pm_config_yaml)
        except Exception:
            y = {}
        runs = y.get("runs") or []
        if not isinstance(runs, list):
            return

        # Build per-type lookup of 'provider:model' label -> checkbox
        type_to_map = {"fpf": {}, "gptr": {}, "dr": {}, "ma": {}}
        try:
            for cb in self._iter_model_checkboxes():
                try:
                    name = cb.objectName() or ""
                    parts = name.split("_")
                    if len(parts) < 2:
                        continue
                    type_key = parts[1].strip().lower()
                    if type_key not in type_to_map:
                        continue
                    label = (cb.text() or "").strip()
                    if label:
                        type_to_map[type_key][label] = cb
                except Exception:
                    continue
        except Exception:
            pass

        for entry in runs:
            try:
                rtype = str(entry.get("type", "")).strip().lower()
                provider = str(entry.get("provider", "")).strip()
                model = str(entry.get("model", "")).strip()
                if not model:
                    continue
                # Prefer exact provider:model within matching type
                if provider:
                    label = f"{provider}:{model}"
                    cb = type_to_map.get(rtype, {}).get(label)
                    if cb:
                        try:
                            cb.setChecked(True)
                        except Exception:
                            pass
                else:
                    # MA entries may lack provider; match any provider with same model suffix in MA only
                    if rtype == "ma":
                        for text, cb in type_to_map.get("ma", {}).items():
                            try:
                                if text.endswith(f":{model}"):
                                    cb.setChecked(True)
                                    break
                            except Exception:
                                continue
            except Exception:
                continue

    def _gather_runs_from_checkboxes(self):
        """
        Collect checked provider:model boxes into runs[] per type, using checkbox objectName.
        """
        runs = []
        for cb in self._iter_model_checkboxes():
            try:
                if not cb.isChecked():
                    continue
                name = cb.objectName() or ""
                # objectName format: check_{type}_{sanitized_provider}_{sanitized_model}
                parts = name.split("_")
                if len(parts) < 2:
                    continue
                type_key = parts[1]
                label = cb.text().strip()
                prov, mod = model_catalog.split_provider_model(label)
                if type_key == "ma":
                    if mod:
                        runs.append({"type": "ma", "model": mod})
                else:
                    if prov and mod:
                        runs.append({"type": type_key, "provider": prov, "model": mod})
            except Exception:
                continue
        return runs

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

            # Set paths from config.yaml, with fallbacks to defaults if not present or empty
            if self.lineInputFolder:
                input_path = y.get("input_folder")
                if input_path:
                    self.lineInputFolder.setText(str(input_path))
                elif not self.lineInputFolder.text():
                    self.lineInputFolder.setText(str(self.pm_dir / "test" / "mdinputs"))
            if self.lineOutputFolder:
                output_path = y.get("output_folder")
                if output_path:
                    self.lineOutputFolder.setText(str(output_path))
                elif not self.lineOutputFolder.text():
                    self.lineOutputFolder.setText(str(self.pm_dir / "test" / "mdoutputs"))
            if self.lineInstructionsFile:
                instructions_path = y.get("instructions_file")
                if instructions_path:
                    self.lineInstructionsFile.setText(str(instructions_path))
                elif not self.lineInstructionsFile.text():
                    self.lineInstructionsFile.setText(str(self.pm_dir / "test" / "instructions.txt"))
            # Guidelines file populates from config.yaml if present, otherwise default if empty
            if getattr(self, "lineGuidelinesFile", None):
                gf = y.get("guidelines_file")
                if gf:
                    self.lineGuidelinesFile.setText(str(gf))
                elif not self.lineGuidelinesFile.text():
                    # Set a default specific to the project's structure if it exists
                    default_guidelines_path = self.pm_dir / "test" / "report must be in spanish.txt"
                    if default_guidelines_path.exists():
                        self.lineGuidelinesFile.setText(str(default_guidelines_path))

            # Set evaluation output/export paths from config.yaml, with fallbacks
            eval_config = y.get("eval", {})
            if self.sliderEvaluationIterations:
                eval_iterations = int(eval_config.get("iterations", 1) or 1)
                self.sliderEvaluationIterations.setValue(clamp_int(eval_iterations, self.sliderEvaluationIterations.minimum(), self.sliderEvaluationIterations.maximum()))

            # Pairwise top N (default 3)
            if self.sliderPairwiseTopN:
                pairwise_top_n = int(eval_config.get("pairwise_top_n", 3) or 3)
                self.sliderPairwiseTopN.setValue(clamp_int(pairwise_top_n, self.sliderPairwiseTopN.minimum(), self.sliderPairwiseTopN.maximum()))

            if self.lineEvalOutputFolder:
                eval_output_path = eval_config.get("output_directory")
                if eval_output_path:
                    self.lineEvalOutputFolder.setText(str(eval_output_path))
                elif not self.lineEvalOutputFolder.text():
                    self.lineEvalOutputFolder.setText(str(self.pm_dir / "gptr-eval-process" / "final_reports")) # Default

            if self.lineEvalExportFolder:
                eval_export_path = eval_config.get("export_directory")
                if eval_export_path:
                    self.lineEvalExportFolder.setText(str(eval_export_path))
                elif not self.lineEvalExportFolder.text():
                    self.lineEvalExportFolder.setText(str(self.pm_dir / "gptr-eval-process" / "exports")) # Default

            # Set auto_run checkbox state
            if getattr(self, "checkEvalAutoRun", None):
                self.checkEvalAutoRun.setChecked(eval_config.get("auto_run", False))

            # Set auto_run checkbox state
            if getattr(self, "checkEvalAutoRun", None):
                self.checkEvalAutoRun.setChecked(eval_config.get("auto_run", False))

            # Set auto_run checkbox state
            if getattr(self, "checkEvalAutoRun", None):
                self.checkEvalAutoRun.setChecked(eval_config.get("auto_run", False))

            # Set auto_run checkbox state
            if getattr(self, "checkEvalAutoRun", None):
                self.checkEvalAutoRun.setChecked(eval_config.get("auto_run", False))

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

            except Exception:
                pass

            # Apply defaults for Evaluation judges and mode from main config.yaml's eval.judges
            try:
                self._apply_eval_defaults_from_models()
            except Exception:
                pass

            # Load Combine & Revise settings
            try:
                self.combine_handler.load_config(y)
            except Exception as e:
                print(f"[WARN] Failed to load combine settings: {e}", flush=True)

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

        # Evaluation output/export paths and auto_run flag
        eval_vals = vals.get("eval", {})
        if getattr(self, "sliderEvaluationIterations", None):
            eval_vals["iterations"] = int(self.sliderEvaluationIterations.value())
        if getattr(self, "sliderPairwiseTopN", None):
            eval_vals["pairwise_top_n"] = int(self.sliderPairwiseTopN.value())
        if getattr(self, "lineEvalOutputFolder", None):
            eval_vals["output_directory"] = str(self.lineEvalOutputFolder.text())
        if getattr(self, "lineEvalExportFolder", None):
            eval_vals["export_directory"] = str(self.lineEvalExportFolder.text())
        if getattr(self, "checkEvalAutoRun", None):
            eval_vals["auto_run"] = bool(self.checkEvalAutoRun.isChecked())
        vals["eval"] = eval_vals
        
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

        # Collect evaluation judges (checkboxes) and mode (llm-doc-eval)
        try:
            container = self.findChild(QtWidgets.QWidget, "containerEvalModels")
            selected = []
            if container is not None:
                for cb in container.findChildren(QtWidgets.QCheckBox):
                    try:
                        if not cb.isChecked():
                            continue
                        label = (cb.text() or "").strip()
                        if ":" in label:
                            prov, mod = label.split(":", 1)
                            prov = prov.strip()
                            mod = mod.strip()
                            if prov and mod:
                                selected.append({"provider": prov, "model": mod})
                    except Exception:
                        continue
            rb_both = self.findChild(QtWidgets.QRadioButton, "radioEvalBoth")
            rb_pair = self.findChild(QtWidgets.QRadioButton, "radioEvalPairwise")
            rb_grad = self.findChild(QtWidgets.QRadioButton, "radioEvalGraded")
            mode = "both"
            try:
                if rb_pair and rb_pair.isChecked():
                    mode = "pairwise"
                elif rb_grad and rb_grad.isChecked():
                    mode = "single"
            except Exception:
                pass
            vals["llm_eval"] = {
                "models": list(selected),
                "mode": mode,
            }
            
            # Collect Model A and Model B from unified controls
            comboA = self.findChild(QtWidgets.QComboBox, "comboEvalModelA")
            comboB = self.findChild(QtWidgets.QComboBox, "comboEvalModelB")
            if comboA:
                txt = comboA.currentText().strip()
                if ":" in txt:
                    p, m = txt.split(":", 1)
                    vals["llm_eval"]["model_a"] = {"provider": p.strip(), "model": m.strip()}
            if comboB:
                txt = comboB.currentText().strip()
                if ":" in txt:
                    p, m = txt.split(":", 1)
                    vals["llm_eval"]["model_b"] = {"provider": p.strip(), "model": m.strip()}

        except Exception:
            pass

        # Build runs[] from provider:model checkboxes
        try:
            vals["runs"] = self._gather_runs_from_checkboxes()
        except Exception:
            pass

        # --- Combine & Revise Section ---
        try:
            vals["combine"] = self.combine_handler.gather_values()
        except Exception as e:
            print(f"[WARN] Failed to gather combine values: {e}", flush=True)

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


            # runs-only: persist runs[] and remove legacy keys
            try:
                y["runs"] = list(vals.get("runs", []))
                if "additional_models" in y:
                    del y["additional_models"]
                if "iterations" in y:
                    del y["iterations"]
            except Exception:
                pass

            # Persist eval.* keys (output_directory, export_directory, auto_run)
            try:
                eval_vals_from_gui_for_persist = vals.get("eval", {})
                if isinstance(eval_vals_from_gui_for_persist, dict):
                    y_eval = y.get("eval", {})
                    if not isinstance(y_eval, dict):
                        y_eval = {}
                    if "output_directory" in eval_vals_from_gui_for_persist:
                        y_eval["output_directory"] = eval_vals_from_gui_for_persist["output_directory"]
                    if "export_directory" in eval_vals_from_gui_for_persist:
                        y_eval["export_directory"] = eval_vals_from_gui_for_persist["export_directory"]
                    if "auto_run" in eval_vals_from_gui_for_persist:
                        y_eval["auto_run"] = bool(eval_vals_from_gui_for_persist["auto_run"])
                    if "iterations" in eval_vals_from_gui_for_persist:
                        y_eval["iterations"] = int(eval_vals_from_gui_for_persist["iterations"])
                    if "pairwise_top_n" in eval_vals_from_gui_for_persist:
                        y_eval["pairwise_top_n"] = int(eval_vals_from_gui_for_persist["pairwise_top_n"])
                    y["eval"] = y_eval
            except Exception:
                pass

            # Persist combine section
            try:
                combine_vals = vals.get("combine", {})
                if combine_vals:
                    y["combine"] = combine_vals
            except Exception:
                pass

            write_yaml(self.pm_config_yaml, y)

            # Detailed console output: list each written variable and destination file
            try:
                log_lines = []
                # Paths
                for k in ("input_folder", "output_folder", "instructions_file"):
                    if k in vals:
                        log_lines.append(f"Wrote {k} = {vals[k]!r} -> {self.pm_config_yaml}")
                # Guidelines file
                if "guidelines_file" in vals:
                    log_lines.append(f"Wrote guidelines_file = {vals['guidelines_file']!r} -> {self.pm_config_yaml}")
                # Evaluation output/export paths
                eval_vals_from_gui = vals.get("eval", {})
                if "output_directory" in eval_vals_from_gui:
                    log_lines.append(f"Wrote eval.output_directory = {eval_vals_from_gui['output_directory']!r} -> {self.pm_config_yaml}")
                if "export_directory" in eval_vals_from_gui:
                    log_lines.append(f"Wrote eval.export_directory = {eval_vals_from_gui['export_directory']!r} -> {self.pm_config_yaml}")
                if "auto_run" in eval_vals_from_gui:
                    log_lines.append(f"Wrote eval.auto_run = {eval_vals_from_gui['auto_run']!r} -> {self.pm_config_yaml}")
                if "iterations" in eval_vals_from_gui:
                    log_lines.append(f"Wrote eval.iterations = {eval_vals_from_gui['iterations']!r} -> {self.pm_config_yaml}")
                if "pairwise_top_n" in eval_vals_from_gui:
                    log_lines.append(f"Wrote eval.pairwise_top_n = {eval_vals_from_gui['pairwise_top_n']!r} -> {self.pm_config_yaml}")
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

        # Also persist GPT‑Researcher configs from GUI
        try:
            if hasattr(self, "gptr_ma_handler") and self.gptr_ma_handler:
                self.gptr_ma_handler.write_configs(vals)
        except Exception as e:
            print(f"[ERROR] Failed to write GPT‑R configs: {e}", flush=True)

        # Persist eval.judges and eval.mode to main config.yaml (not llm-doc-eval config)
        try:
            main_cfg_path = self.pm_dir / "config.yaml"
            try:
                y_main = read_yaml(main_cfg_path)
            except Exception:
                y_main = {}
            if not isinstance(y_main, dict):
                y_main = {}
            
            le = vals.get("llm_eval", {}) if isinstance(vals, dict) else {}
            selected = le.get("models") or []
            mode = le.get("mode")
            
            # Build judges list from selected checkboxes
            judges_list = []
            for item in selected:
                try:
                    prov = (item.get("provider") or "").strip()
                    mod = (item.get("model") or "").strip()
                    if prov and mod:
                        judges_list.append({"provider": prov, "model": mod})
                except Exception:
                    continue
            
            # Update eval section in main config
            y_main.setdefault("eval", {})
            if judges_list:
                y_main["eval"]["judges"] = judges_list
            if mode:
                y_main["eval"]["mode"] = str(mode)
            
            write_yaml(main_cfg_path, y_main)
            try:
                print(f"[OK] Wrote eval.judges to main config -> {main_cfg_path}", flush=True)
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Failed to write eval.judges to main config: {e}", flush=True)

        # Also persist FPF Concurrency (global settings) from the new section
        try:
            if hasattr(self, "fpf_concurrency_section") and self.fpf_concurrency_section:
                self.fpf_concurrency_section.write_configs(vals)
        except Exception as e:
            print(f"[ERROR] Failed to write FPF concurrency: {e}", flush=True)


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

    def on_evaluate_clicked(self) -> None:
        """
        Run the evaluation process (evaluate.py) in a background thread to keep the GUI responsive.
        """
        # Disable the button while running
        if getattr(self, "btn_evaluate", None):
            self.btn_evaluate.setEnabled(False)

        # Write latest configs first so evaluation picks up current settings (e.g., evaluation mode in config.yaml)
        try:
            vals = self.gather_values()
            self.write_configs(vals)
        except Exception as e:
            if getattr(self, "btn_evaluate", None):
                self.btn_evaluate.setEnabled(True)
            show_error(str(e))
            return

        # Launch evaluate.py in a thread so GUI stays responsive
        try:
            self.eval_thread = RunnerThread(self.pm_dir, self.evaluate_py, self)
            self.eval_thread.finished_ok.connect(self._on_evaluate_finished)
            self.eval_thread.start()
        except Exception as e:
            if getattr(self, "btn_evaluate", None):
                self.btn_evaluate.setEnabled(True)
            show_error(f"Failed to start evaluation: {e}")

    def _on_evaluate_finished(self, ok: bool, code: int, message: str) -> None:
        """
        Handler called when the evaluation process finishes.
        """
        if getattr(self, "btn_evaluate", None):
            self.btn_evaluate.setEnabled(True)
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
            ("sliderEvaluationIterations", "labelEvaluationIterationsMin", "labelEvaluationIterationsMax"),
            ("sliderPairwiseTopN", "labelPairwiseTopNMin", "labelPairwiseTopNMax"),
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
        if getattr(self, "sliderEvaluationIterations", None):
            all_sliders.append((self.sliderEvaluationIterations, "sliderEvaluationIterations"))
        if getattr(self, "sliderPairwiseTopN", None):
            all_sliders.append((self.sliderPairwiseTopN, "sliderPairwiseTopN"))

        # Add sliders from handlers
        for handler in [self.gptr_ma_handler, self.fpf_handler, self.combine_handler]:
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
            for handler in [self.gptr_ma_handler, self.fpf_handler, self.combine_handler]:
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
        Total reports = iterations_default * number of checked model checkboxes across all types.
        """
        try:
            iterations = 0
            if getattr(self, "sliderIterations_2", None):
                try:
                    iterations = int(self.sliderIterations_2.value())
                except Exception:
                    iterations = 0

            checked = 0
            try:
                for cb in self._iter_model_checkboxes():
                    try:
                        if cb.isChecked():
                            checked += 1
                    except Exception:
                        continue
            except Exception:
                pass

            total = int(iterations * checked)
            lbl = getattr(self, "labelTotalReports", None) or self.findChild(QtWidgets.QLabel, "label_2")
            if lbl:
                try:
                    lbl.setText(str(total))
                except Exception:
                    lbl.setText(str(total))
        except Exception:
            return
    # ---- Evaluation provider/model dynamic population (FPF-sourced) ----
    def _get_eval_combo_pairs(self):
        """
        Return list of (provider_combo, model_combo) pairs across:
          - Graded Evaluation (comboEvaluationProvider, comboEvaluationModel)
          - Pairwise Evaluation (comboEvaluationProvider2, comboEvaluationModel2)
        """
        pairs = []
        names = [
            ("comboEvaluationProvider", "comboEvaluationModel"),
            ("comboEvaluationProvider2", "comboEvaluationModel2"),
        ]
        for prov_name, model_name in names:
            try:
                cp = self.findChild(QtWidgets.QComboBox, prov_name)
                cm = self.findChild(QtWidgets.QComboBox, model_name)
                if cp is not None and cm is not None:
                    pairs.append((cp, cm))
            except Exception:
                continue
        return pairs

    def _populate_eval_provider_model_combos(self) -> None:
        """
        Fill all evaluation provider/model comboboxes from the same source as FPF:
          - Providers discovered from FilePromptForge/providers/*
          - Models loaded via FPF allowed models for the selected provider
        """
        prov_map = {}
        try:
            # Reuse FPF discovery helpers
            prov_map = self.fpf_handler._discover_fpf_providers() if getattr(self, "fpf_handler", None) else {}
        except Exception:
            prov_map = {}

        # Cache for subsequent provider->model refresh
        self._fpf_eval_prov_map = prov_map or {}
        providers = sorted(self._fpf_eval_prov_map.keys())

        for combo_provider, combo_model in self._get_eval_combo_pairs():
            try:
                combo_provider.blockSignals(True)
                combo_provider.clear()
                if providers:
                    combo_provider.addItems(providers)
                    combo_provider.setEnabled(True)
                else:
                    combo_provider.addItem("No FPF providers found")
                    combo_provider.setEnabled(False)
                combo_provider.blockSignals(False)
            except Exception:
                pass

            # Connect provider change -> refresh corresponding model list
            try:
                combo_provider.currentIndexChanged.connect(
                    lambda _=0, cp=combo_provider, cm=combo_model: self._on_eval_provider_changed(cp, cm)
                )
            except Exception:
                pass

            # Initial model population for current provider selection
            try:
                self._on_eval_provider_changed(combo_provider, combo_model)
            except Exception:
                pass

    def _on_eval_provider_changed(self, combo_provider: QtWidgets.QComboBox, combo_model: QtWidgets.QComboBox) -> None:
        """
        When an evaluation provider changes, reload the corresponding model combobox
        using FPF's allowed models for that provider.
        """
        if not combo_provider or not combo_model:
            return

        try:
            provider = (combo_provider.currentText() or "").strip()
        except Exception:
            provider = ""

        prov_map = getattr(self, "_fpf_eval_prov_map", {}) or {}
        ppath = prov_map.get(provider)

        models = []
        if ppath:
            try:
                models = self.fpf_handler._load_allowed_models(ppath) if getattr(self, "fpf_handler", None) else []
            except Exception:
                models = []

        try:
            combo_model.blockSignals(True)
            combo_model.clear()
            if models:
                combo_model.addItems(models)
                combo_model.setEnabled(True)
            else:
                combo_model.addItem("No models available")
                combo_model.setEnabled(False)
            combo_model.blockSignals(False)
        except Exception:
            pass

    def _apply_eval_defaults_from_config(self, y: Dict[str, Any]) -> None:
        """
        Read defaults for Evaluation provider/model from config.yaml.
        Strategy: pick the first 'fpf' run entry (provider+model) and apply it to:
          - Graded Evaluation and Pairwise Evaluation dropdowns.
        """
        if not isinstance(y, dict):
            return
        runs = y.get("runs") or []
        if not isinstance(runs, list):
            return

        default_provider = None
        default_model = None
        for entry in runs:
            try:
                if str(entry.get("type", "")).strip().lower() == "fpf":
                    dp = str(entry.get("provider", "")).strip()
                    dm = str(entry.get("model", "")).strip()
                    if dp and dm:
                        default_provider = dp
                        default_model = dm
                        break
            except Exception:
                continue

        if not (default_provider and default_model):
            return

        # Only apply to the first two (graded, pairwise)
        pairs = self._get_eval_combo_pairs()
        for idx, (combo_provider, combo_model) in enumerate(pairs):
            if idx >= 2:
                break
            try:
                # Set provider selection if present
                prov_index = -1
                for i in range(combo_provider.count()):
                    try:
                        if (combo_provider.itemText(i) or "").strip().lower() == default_provider.lower():
                            prov_index = i
                            break
                    except Exception:
                        continue
                if prov_index >= 0:
                    combo_provider.setCurrentIndex(prov_index)
                    # Refresh models for this provider
                    self._on_eval_provider_changed(combo_provider, combo_model)
                    # Set model selection if present
                    mod_index = -1
                    for j in range(combo_model.count()):
                        try:
                            if (combo_model.itemText(j) or "").strip().lower() == default_model.lower():
                                mod_index = j
                                break
                        except Exception:
                            continue
                    if mod_index >= 0:
                        combo_model.setCurrentIndex(mod_index)
            except Exception:
                continue

    # ---- Evaluation controls (unified Model A/B + mode) ----
    def _build_fpf_provider_model_list(self):
        flat = []
        prov_map = {}
        try:
            prov_map = self.fpf_handler._discover_fpf_providers() if getattr(self, "fpf_handler", None) else {}
        except Exception:
            prov_map = {}
        providers = sorted(prov_map.keys())
        for prov in providers:
            ppath = prov_map.get(prov)
            models = []
            if ppath:
                try:
                    models = self.fpf_handler._load_allowed_models(ppath) if getattr(self, "fpf_handler", None) else []
                except Exception:
                    models = []
            for m in models or []:
                try:
                    flat.append(f"{prov}:{m}")
                except Exception:
                    continue
        return flat

    def _set_combobox_to_text(self, combo: QtWidgets.QComboBox, text: str) -> None:
        if not combo or not text:
            return
        try:
            target = (text or "").strip().lower()
            for i in range(combo.count()):
                try:
                    if (combo.itemText(i) or "").strip().lower() == target:
                        combo.setCurrentIndex(i)
                        return
                except Exception:
                    continue
        except Exception:
            return

    def _apply_eval_unified_defaults_from_llm_eval(self) -> None:
        # Read model_a, model_b from main config's eval section and mode from eval.mode
        main_cfg_path = self.pm_dir / "config.yaml"
        try:
            y = read_yaml(main_cfg_path)
        except Exception:
            y = {}
        try:
            eval_cfg = y.get("eval") or {}
            # Model A and B might be stored as separate keys or we use first two judges
            judges = eval_cfg.get("judges") or []
            ma = judges[0] if len(judges) > 0 else {}
            mb = judges[1] if len(judges) > 1 else {}
            mode = (eval_cfg.get("mode") or "").strip().lower()
        except Exception:
            ma, mb, mode = {}, {}, ""

        comboA = self.findChild(QtWidgets.QComboBox, "comboEvalModelA")
        comboB = self.findChild(QtWidgets.QComboBox, "comboEvalModelB")
        if comboA and ma.get("provider") and ma.get("model"):
            self._set_combobox_to_text(comboA, f"{ma.get('provider')}:{ma.get('model')}")
        if comboB and mb.get("provider") and mb.get("model"):
            self._set_combobox_to_text(comboB, f"{mb.get('provider')}:{mb.get('model')}")

        # Radio mode
        try:
            rb_both = self.findChild(QtWidgets.QRadioButton, "radioEvalBoth")
            rb_pair = self.findChild(QtWidgets.QRadioButton, "radioEvalPairwise")
            rb_grad = self.findChild(QtWidgets.QRadioButton, "radioEvalGraded")
            if mode == "pairwise":
                if rb_pair: rb_pair.setChecked(True)
            elif mode == "single" or mode == "graded":
                if rb_grad: rb_grad.setChecked(True)
            else:
                if rb_both: rb_both.setChecked(True)
        except Exception:
            pass

    def _populate_unified_eval_controls(self) -> None:
        comboA = self.findChild(QtWidgets.QComboBox, "comboEvalModelA")
        comboB = self.findChild(QtWidgets.QComboBox, "comboEvalModelB")
        flat = self._build_fpf_provider_model_list()
        for combo in (comboA, comboB):
            try:
                if combo is None:
                    continue
                combo.blockSignals(True)
                combo.clear()
                if flat:
                    combo.addItems(flat)
                    combo.setEnabled(True)
                else:
                    combo.addItem("No FPF models available")
                    combo.setEnabled(False)
                combo.blockSignals(False)
            except Exception:
                continue
        try:
            self._apply_eval_unified_defaults_from_llm_eval()
        except Exception:
            pass

    # ---- Evaluation judges checkbox population and defaults ----
    def _get_eval_models_layout(self):
        container = self.findChild(QtWidgets.QWidget, "containerEvalModels")
        layout = None
        if container is not None:
            try:
                layout = container.layout()
            except Exception:
                layout = None
        if layout is None:
            layout = self.findChild(QtWidgets.QVBoxLayout, "layoutEvalModels")
        return layout

    def _clear_layout_widgets(self, layout):
        if not layout:
            return
        try:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
        except Exception:
            pass

    def _populate_eval_model_checkboxes(self) -> None:
        layout = self._get_eval_models_layout()
        if layout is None:
            try:
                print("[WARN] containerEvalModels layout not found", flush=True)
            except Exception:
                pass
            return
        self._clear_layout_widgets(layout)
        flat = self._build_fpf_provider_model_list()
        created = 0
        for label in flat:
            try:
                cb = QtWidgets.QCheckBox(label)
                # objectName: check_eval_provider_model
                safe = label.replace(":", "_").replace("/", "_").replace(" ", "_")
                cb.setObjectName(f"check_eval_{safe}")
                layout.addWidget(cb)
                created += 1
            except Exception:
                continue
        try:
            print(f"[DEBUG][EVAL_UI] built {created} judge checkbox(es)", flush=True)
        except Exception:
            pass

    def _apply_eval_defaults_from_models(self) -> None:
        # Pre-check any models listed in main config.yaml's eval.judges and apply mode radios
        main_cfg_path = self.pm_dir / "config.yaml"
        try:
            y = read_yaml(main_cfg_path)
        except Exception:
            y = {}

        # Collect wanted provider:model labels from the eval.judges list
        wanted = set()
        try:
            judges_list = (y.get("eval") or {}).get("judges") or []
            if isinstance(judges_list, list):
                for m in judges_list:
                    try:
                        if not isinstance(m, dict):
                            continue
                        prov = (m.get("provider") or "").strip()
                        mod = (m.get("model") or "").strip()
                        if prov and mod:
                            wanted.add(f"{prov}:{mod}")
                    except Exception:
                        continue
        except Exception:
            wanted = set()

        # Check corresponding checkboxes in the judges container
        try:
            container = self.findChild(QtWidgets.QWidget, "containerEvalModels")
            if container is not None and wanted:
                for cb in container.findChildren(QtWidgets.QCheckBox):
                    try:
                        text = (cb.text() or "").strip()
                        if text in wanted:
                            cb.setChecked(True)
                    except Exception:
                        continue
        except Exception:
            pass

        # Apply evaluation mode radio buttons
        mode = ""
        try:
            mode = ((y.get("eval") or {}).get("mode") or "").strip().lower()
        except Exception:
            mode = ""
        try:
            rb_both = self.findChild(QtWidgets.QRadioButton, "radioEvalBoth")
            rb_pair = self.findChild(QtWidgets.QRadioButton, "radioEvalPairwise")
            rb_grad = self.findChild(QtWidgets.QRadioButton, "radioEvalGraded")
            if mode == "pairwise":
                if rb_pair: rb_pair.setChecked(True)
            elif mode == "single" or mode == "graded":
                if rb_grad: rb_grad.setChecked(True)
            else:
                if rb_both: rb_both.setChecked(True)
        except Exception:
            pass

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

    def on_browse_eval_output_folder(self) -> None:
        """Open a folder dialog and set evaluation output folder line edit."""
        try:
            dlg = QtWidgets.QFileDialog(self, "Select Evaluation Output Folder")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            if dlg.exec_():
                sel = dlg.selectedFiles()
                if sel:
                    path = sel[0]
                    if getattr(self, "lineEvalOutputFolder", None):
                        self.lineEvalOutputFolder.setText(path)
        except Exception as e:
            print(f"[WARN] on_browse_eval_output_folder failed: {e}", flush=True)

    def on_open_eval_output_folder(self) -> None:
        """Open OS explorer at evaluation output folder path."""
        try:
            path = None
            if getattr(self, "lineEvalOutputFolder", None):
                path = self.lineEvalOutputFolder.text()
            if not path:
                return
            _open_in_file_explorer(path)
        except Exception as e:
            print(f"[WARN] on_open_eval_output_folder failed: {e}", flush=True)

    def on_browse_eval_export_folder(self) -> None:
        """Open a folder dialog and set evaluation export folder line edit."""
        try:
            dlg = QtWidgets.QFileDialog(self, "Select Evaluation Export Folder")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            if dlg.exec_():
                sel = dlg.selectedFiles()
                if sel:
                    path = sel[0]
                    if getattr(self, "lineEvalExportFolder", None):
                        self.lineEvalExportFolder.setText(path)
        except Exception as e:
            print(f"[WARN] on_browse_eval_export_folder failed: {e}", flush=True)

    def on_open_eval_export_folder(self) -> None:
        """Open OS explorer at evaluation export folder path."""
        try:
            path = None
            if getattr(self, "lineEvalExportFolder", None):
                path = self.lineEvalExportFolder.text()
            if not path:
                return
            _open_in_file_explorer(path)
        except Exception as e:
            print(f"[WARN] on_open_eval_export_folder failed: {e}", flush=True)

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
