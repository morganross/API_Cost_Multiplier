from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import pyqtSignal

from .concurrency_config import (
    get_fpf_yaml_path,
    read_fpf_yaml,
    write_fpf_yaml,
    merge_concurrency,
    effective_concurrency,
    validate_concurrency,
    DEFAULTS,
)


class FPFConcurrencySection(QtWidgets.QWidget):
    """
    Single-page GUI section for configuring FPF concurrency (global only).
    Reads initial values from fpf_config.yaml and writes back when MainWindow's
    'Write to Configs' is clicked (no Apply/Reset here).

    Schema:
      concurrency:
        enabled: bool
        max_concurrency: int (>=1)
        qps: float (>0.0)  [slider value / 10.0]
    """
    concurrencyApplied = pyqtSignal(dict)  # kept for compatibility; emitted on write

    def __init__(self, main_window: QtWidgets.QMainWindow):
        super().__init__(parent=main_window)
        self.main_window = main_window
        self.pm_dir: Path = getattr(main_window, "pm_dir", Path(__file__).resolve().parents[1])

        ui_path = Path(__file__).parent / "fpf_concurrency_section.ui"
        uic.loadUi(str(ui_path), self)

        # Cache widgets (sliders + checkbox)
        self.checkConcurrencyEnabled: QtWidgets.QCheckBox = self.findChild(QtWidgets.QCheckBox, "checkConcurrencyEnabled")
        self.sliderGlobalMaxConcurrency: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderGlobalMaxConcurrency")
        self.sliderGlobalQPS: QtWidgets.QSlider = self.findChild(QtWidgets.QSlider, "sliderGlobalQPS")

        # End labels for sliders
        self.labelGlobalMaxConcurrencyMin: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelGlobalMaxConcurrencyMin")
        self.labelGlobalMaxConcurrencyMax: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelGlobalMaxConcurrencyMax")
        self.labelGlobalQPSMin: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelGlobalQPSMin")
        self.labelGlobalQPSMax: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelGlobalQPSMax")

        # Set up live readouts for concurrency sliders
        self._setup_readouts()

        # Initial load
        self.load_values()

        # Refresh readouts to reflect loaded values
        try:
            self._refresh_readouts()
        except Exception:
            pass

    def connect_signals(self) -> None:
        # No local apply/reset buttons; values are saved by MainWindow.on_write_clicked
        pass

    def _setup_readouts(self) -> None:
        """
        Initialize labels and connect valueChanged signals for concurrency sliders.
        Left labels show min values; right labels show 'current / max'.
        """
        try:
            if getattr(self, "labelGlobalMaxConcurrencyMin", None) and getattr(self, "sliderGlobalMaxConcurrency", None):
                self.labelGlobalMaxConcurrencyMin.setText(str(int(self.sliderGlobalMaxConcurrency.minimum())))
        except Exception:
            pass
        try:
            if getattr(self, "labelGlobalQPSMin", None) and getattr(self, "sliderGlobalQPS", None):
                mn = float(int(self.sliderGlobalQPS.minimum())) / 10.0
                if mn <= 0.0:
                    mn = 0.1
                self.labelGlobalQPSMin.setText(f"{mn:.1f}")
        except Exception:
            pass
        try:
            if getattr(self, "sliderGlobalMaxConcurrency", None):
                self.sliderGlobalMaxConcurrency.valueChanged.connect(self._update_readout_max_concurrency)
        except Exception:
            pass
        try:
            if getattr(self, "sliderGlobalQPS", None):
                self.sliderGlobalQPS.valueChanged.connect(self._update_readout_qps)
        except Exception:
            pass

    def _update_readout_max_concurrency(self, _val: int = 0) -> None:
        try:
            s = getattr(self, "sliderGlobalMaxConcurrency", None)
            lbl = getattr(self, "labelGlobalMaxConcurrencyMax", None)
            if not s or not lbl:
                return
            current = int(s.value())
            mx = int(s.maximum())
            lbl.setText(f"{current} / {mx}")
        except Exception:
            pass

    def _update_readout_qps(self, _val: int = 0) -> None:
        try:
            s = getattr(self, "sliderGlobalQPS", None)
            lbl = getattr(self, "labelGlobalQPSMax", None)
            if not s or not lbl:
                return
            sval = int(s.value())
            current = max(0.1, float(sval) / 10.0)
            mx = float(int(s.maximum())) / 10.0
            lbl.setText(f"{current:.1f} / {mx:.1f}")
        except Exception:
            pass

    def _refresh_readouts(self) -> None:
        try:
            self._update_readout_max_concurrency()
        except Exception:
            pass
        try:
            self._update_readout_qps()
        except Exception:
            pass

    def _clamp_slider(self, slider: QtWidgets.QSlider, value: int) -> int:
        if slider is None:
            return value
        try:
            mn, mx = slider.minimum(), slider.maximum()
            return max(mn, min(mx, int(value)))
        except Exception:
            return value

    # ---- Load / Gather / Write ----
    def load_values(self) -> None:
        """
        Read fpf_config.yaml and populate UI. Missing keys are filled by DEFAULTS.
        """
        try:
            fpf_yaml = get_fpf_yaml_path(self.pm_dir)
            root = read_fpf_yaml(fpf_yaml)
        except Exception:
            root = {}

        conc = effective_concurrency(root)

        # enabled
        try:
            if self.checkConcurrencyEnabled is not None:
                self.checkConcurrencyEnabled.setChecked(bool(conc.get("enabled", True)))
        except Exception:
            pass

        # max_concurrency -> slider
        try:
            mc = int(conc.get("max_concurrency", DEFAULTS["max_concurrency"]))
            if self.sliderGlobalMaxConcurrency is not None:
                self.sliderGlobalMaxConcurrency.setValue(self._clamp_slider(self.sliderGlobalMaxConcurrency, mc))
        except Exception:
            pass

        # qps -> slider value is qps*10 (int)
        try:
            qps = float(conc.get("qps", DEFAULTS["qps"]))
            qps_slider_val = int(round(qps * 10.0))
            if self.sliderGlobalQPS is not None:
                self.sliderGlobalQPS.setValue(self._clamp_slider(self.sliderGlobalQPS, qps_slider_val if qps_slider_val > 0 else 1))
        except Exception:
            pass

    def gather_values(self) -> Dict[str, Any]:
        """
        Collect current UI state as a concurrency subtree (no file I/O).
        Note: QPS slider value is encoded as slider/10.0.
        """
        conc: Dict[str, Any] = {}

        # enabled
        if self.checkConcurrencyEnabled is not None:
            conc["enabled"] = bool(self.checkConcurrencyEnabled.isChecked())

        # max_concurrency
        if self.sliderGlobalMaxConcurrency is not None:
            try:
                conc["max_concurrency"] = int(self.sliderGlobalMaxConcurrency.value())
            except Exception:
                conc["max_concurrency"] = DEFAULTS.get("max_concurrency", 12)

        # qps (slider / 10.0)
        if self.sliderGlobalQPS is not None:
            try:
                sval = int(self.sliderGlobalQPS.value())
                # Ensure > 0.0
                conc["qps"] = max(0.1, float(sval) / 10.0)
            except Exception:
                conc["qps"] = DEFAULTS.get("qps", 2.0)

        return {"concurrency": conc}

    def write_configs(self, _vals_from_main: Dict[str, Any]) -> None:
        """
        Persist only the concurrency subtree to fpf_config.yaml.
        Called by MainWindow.on_write_clicked().
        """
        try:
            # Build concurrency subtree from current UI
            gathered = self.gather_values()
            conc = gathered.get("concurrency", {})

            # Validate
            validate_concurrency(conc)

            # Merge + write
            fpf_yaml = get_fpf_yaml_path(self.pm_dir)
            root = read_fpf_yaml(fpf_yaml)
            merged = merge_concurrency(root, conc)
            write_fpf_yaml(fpf_yaml, merged)

            # Notify (optional)
            try:
                if hasattr(self.main_window, "show_info"):
                    self.main_window.show_info("FPF concurrency settings saved.")
            except Exception:
                pass
            self.concurrencyApplied.emit(conc)
        except Exception as e:
            try:
                if hasattr(self.main_window, "show_error"):
                    self.main_window.show_error(str(e))
            except Exception:
                pass
