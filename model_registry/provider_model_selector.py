#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Provider/Model selector example using PyQt5.

- First dropdown (provider): one entry per YAML file found in ./providers
  (e.g., openai.yaml -> "openai", anthropic.yaml -> "anthropic").
- Second dropdown (model): model names parsed from the selected provider's YAML.

UI file: provider_model_selector.ui (in the same folder)
"""

import os
import sys
from typing import Dict, List, Tuple

import yaml
from PyQt5 import QtWidgets, uic


HERE = os.path.abspath(os.path.dirname(__file__))
UI_PATH = os.path.join(HERE, "provider_model_selector.ui")
PROVIDERS_DIR = os.path.join(HERE, "providers")


def discover_providers(providers_dir: str) -> Dict[str, str]:
    """
    Discover provider YAML files and return mapping of provider_name -> file_path.
    Provider name is derived from the filename stem (e.g., 'openai.yaml' -> 'openai').
    """
    mapping: Dict[str, str] = {}
    if not os.path.isdir(providers_dir):
        return mapping
    for fname in os.listdir(providers_dir):
        if not fname.lower().endswith(".yaml"):
            continue
        stem = os.path.splitext(fname)[0]
        full = os.path.join(providers_dir, fname)
        mapping[stem] = full
    return mapping


def extract_models_from_yaml(provider_name: str, yaml_path: str) -> Tuple[List[str], str]:
    """
    Parse a provider YAML and return (models, detected_provider_key).

    Expected structure based on repo examples:
    openai.yaml:
      openai:
        gpt-5: {...}
        gpt-5-mini: {...}
        ...

    We will:
    - Prefer data[provider_name] if present and is a dict of model entries.
    - Else, if the top-level is a dict with a single key whose value is a dict, use that.
    - Else, if the top-level itself looks like {model_name: {...}}, use those keys.
    """
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return ([], "")

    if not isinstance(data, dict):
        return ([], "")

    # Preferred path: top-level key equals provider_name
    if provider_name in data and isinstance(data[provider_name], dict):
        models_dict = data[provider_name]
        models = [k for k, v in models_dict.items() if isinstance(v, dict)]
        return (sorted(models), provider_name)

    # If a single top-level key that maps to dict of models
    if len(data) == 1:
        only_key = next(iter(data))
        if isinstance(data[only_key], dict):
            models_dict = data[only_key]
            models = list(models_dict.keys())
            return (sorted(models), only_key)

    # Fallback: top-level might directly be {model_name: {...}}
    # Heuristic: take keys that map to dict values.
    model_like_keys = [k for k, v in data.items() if isinstance(v, dict)]
    if model_like_keys:
        return (sorted(model_like_keys), "")

    return ([], "")


class ProviderModelSelector(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Load .ui
        self.ui = uic.loadUi(UI_PATH, self)

        # Widgets from UI
        self.comboProvider: QtWidgets.QComboBox = self.findChild(QtWidgets.QComboBox, "comboProvider")
        self.comboModel: QtWidgets.QComboBox = self.findChild(QtWidgets.QComboBox, "comboModel")

        # Internal state
        self._provider_to_path = discover_providers(PROVIDERS_DIR)

        # Populate providers
        providers = sorted(self._provider_to_path.keys())
        self.comboProvider.clear()
        self.comboProvider.addItems(providers)

        # Wire events
        self.comboProvider.currentTextChanged.connect(self.on_provider_changed)

        # Initialize models list for the first provider (if any)
        if providers:
            self.on_provider_changed(providers[0])

    def on_provider_changed(self, provider_name: str) -> None:
        path = self._provider_to_path.get(provider_name)
        self.comboModel.clear()
        if not path or not os.path.isfile(path):
            self.comboModel.setEnabled(False)
            return

        models, detected_key = extract_models_from_yaml(provider_name, path)
        if not models:
            self.comboModel.setEnabled(False)
            return

        self.comboModel.addItems(models)
        self.comboModel.setEnabled(True)

    def selection(self) -> Tuple[str, str]:
        """
        Return (provider_name, model_name) currently selected.
        """
        provider = self.comboProvider.currentText().strip() if self.comboProvider else ""
        model = self.comboModel.currentText().strip() if self.comboModel else ""
        return (provider, model)


def launch_dialog() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    dlg = ProviderModelSelector()
    dlg.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(launch_dialog())
