import sys
import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml  # PyYAML
except Exception:  # pragma: no cover
    yaml = None  # we will guard uses and show message box if missing

from PyQt5 import QtWidgets, QtCore, uic # Keeping this import as it might be used by classes moved here


def show_error(text: str) -> None:
    QtWidgets.QMessageBox.critical(None, "Error", text)

def show_info(text: str) -> None:
    QtWidgets.QMessageBox.information(None, "Info", text)

def clamp_int(value: int, min_v: int, max_v: int) -> int:
    return max(min_v, min(max_v, int(value)))


def temp_from_slider(v: int) -> float:
    # Scale 0-100 slider to [0.0, 1.0] with two decimals
    f = round((float(v) / 100.0), 2)
    if f < 0.0:
        f = 0.0
    if f > 1.0:
        f = 1.0
    return f


def backup_once(path: Path) -> None:
    # Backup functionality disabled - no longer creating .bak files
    pass


def read_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Please install PyYAML.")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        data = {}
    return data


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Please install PyYAML.")
    backup_once(path)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, indent=2, sort_keys=False, allow_unicode=True)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    backup_once(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8") as fh:
        return fh.read()


def write_text(path: Path, content: str) -> None:
    backup_once(path)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(content)


def extract_number_from_default_py(text: str, key: str) -> Optional[float]:
    """
    Extract numeric (int/float) value for a given key inside DEFAULT_CONFIG.
    Matches patterns like: "KEY": 123 or "KEY": 0.45
    """
    # Restrict to DEFAULT_CONFIG block to reduce false positives
    # but keep robust if formatting changes.
    # First, try to find within DEFAULT_CONFIG {...}
    m_cfg = re.search(r"DEFAULT_CONFIG\s*:\s*BaseConfig\s*=\s*\{(.*?)\}\s*$", text, re.DOTALL | re.MULTILINE)
    scope = m_cfg.group(1) if m_cfg else text
    pattern = rf'("{re.escape(key)}"\s*:\s*)(-?\d+(?:\.\d+)?)'
    m = re.search(pattern, scope)
    if not m:
        # Try a more permissive search on whole text
        m = re.search(pattern, text)
    if m:
        try:
            return float(m.group(2))
        except Exception:
            return None
    return None


def replace_number_in_default_py(text: str, key: str, new_value: float) -> (str, bool):
    """
    Replace numeric (int/float) for a given key inside DEFAULT_CONFIG.
    Keeps trailing commas / comments intact by replacing only the numeric literal.
    Returns (new_text, replaced_flag).
    """
    def _fmt(v: float) -> str:
        # Keep ints as ints, floats with up to two decimals
        if abs(v - int(v)) < 1e-9:
            return str(int(v))
        return f"{v:.2f}"

    pattern = rf'("{re.escape(key)}"\s*:\s*)(-?\d+(?:\.\d+)?)'
    def _repl(m):
        return m.group(1) + _fmt(new_value)
    new_text, n = re.subn(pattern, _repl, text, count=1)
    return new_text, n > 0

def _open_in_file_explorer(path: str) -> None:
    """Open path in OS file explorer (cross-platform)."""
    try:
        p = Path(path)
        if not p.exists():
            return
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception as e:
        print(f"[WARN] _open_in_file_explorer failed: {e}", flush=True)

def _set_combobox_text(combo: QtWidgets.QComboBox, text: str) -> None:
    """Set combobox current text if exists; otherwise add and select."""
    try:
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.addItem(text)
            combo.setCurrentIndex(combo.count() - 1)
    except Exception as e:
        print(f"[WARN] _set_combobox_text failed: {e}", flush=True)


class RunnerThread(QtCore.QThread):
    finished_ok = QtCore.pyqtSignal(bool, int, str)  # (success, returncode, message)

    def __init__(self, pm_dir: Path, generate_py: Path, parent=None):
        super().__init__(parent)
        self.pm_dir = pm_dir
        self.generate_py = generate_py

    def run(self) -> None:  # type: ignore[override]
        try:
            cmd = [sys.executable, "-u", str(self.generate_py)]
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            print(f"[INFO] Starting generate.py with: {cmd}", flush=True)

            # On Windows, create a new console window so users can see the live output.
            # We do not capture stdout/stderr in that case; the child process will own the console.
            if sys.platform.startswith("win"):
                try:
                    creationflags = subprocess.CREATE_NEW_CONSOLE
                except AttributeError:
                    creationflags = 0
                # Use cmd.exe /k to open a console window and keep it open after the process exits.
                runner_cmd = ["cmd.exe", "/k", sys.executable, "-u", str(self.generate_py)]
                proc = subprocess.Popen(
                    runner_cmd,
                    cwd=str(self.pm_dir),
                    env=env,
                    creationflags=creationflags,
                )
                proc.wait()
                ok = proc.returncode == 0
                msg = "generate.py finished successfully" if ok else f"generate.py exited with code {proc.returncode}"
                self.finished_ok.emit(ok, proc.returncode, msg)
                return

            # Non-Windows: keep previous streaming behavior so output appears in the same terminal.
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.pm_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            # Stream output
            assert proc.stdout is not None
            assert proc.stderr is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
            for line in proc.stderr:
                print(line, end="", flush=True)

            proc.wait()
            ok = proc.returncode == 0
            msg = "generate.py finished successfully" if ok else f"generate.py exited with code {proc.returncode}"
            self.finished_ok.emit(ok, proc.returncode, msg)
        except Exception as e:
            self.finished_ok.emit(False, -1, f"Failed to run generate.py: {e}")


class DownloadThread(QtCore.QThread):
    """
    Run download_and_extract.py in a background thread, streaming stdout/stderr to console
    and emitting a finished_ok(bool, returncode, message) signal on completion.
    """
    finished_ok = QtCore.pyqtSignal(bool, int, str)

    def __init__(self, pm_dir: Path, script: Path, parent=None):
        super().__init__(parent)
        self.pm_dir = pm_dir
        self.script = script

    def run(self) -> None:  # type: ignore[override]
        try:
            cmd = [sys.executable, "-u", str(self.script)]
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            print(f"[INFO] Starting download_and_extract.py with: {cmd}", flush=True)
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.pm_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            # Stream output
            assert proc.stdout is not None
            assert proc.stderr is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
            for line in proc.stderr:
                print(line, end="", flush=True)

            proc.wait()
            ok = proc.returncode == 0
            msg = "download_and_extract.py finished successfully" if ok else f"download_and_extract.py exited with code {proc.returncode}"
            self.finished_ok.emit(ok, proc.returncode, msg)
        except Exception as e:
            self.finished_ok.emit(False, -1, f"Failed to run download_and_extract.py: {e}")
