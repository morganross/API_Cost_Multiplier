from typing import Dict, Any, List, Optional
from PyQt5 import QtWidgets
from . import model_catalog

class Combine_UI_Handler:
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = main_window
        
        # Widget references
        self.chk_enable: Optional[QtWidgets.QCheckBox] = None
        self.container_models: Optional[QtWidgets.QWidget] = None
        
        # Data
        self.fpf_models: List[str] = []

    def setup_ui(self):
        """Finds widgets by name and connects signals."""
        # Main Enable Checkbox
        self.chk_enable = self.ui.findChild(QtWidgets.QCheckBox, "chkEnableCombine")
        
        # Models Container
        self.container_models = self.ui.findChild(QtWidgets.QWidget, "containerCombineModels")

    def populate_models(self):
        """
        Discover FPF models and populate checkboxes in the container.
        """
        print("[DEBUG] Combine_UI_Handler.populate_models called", flush=True)
        
        scroll = self.ui.findChild(QtWidgets.QScrollArea, "scrollCombineModels")
        if not scroll:
            print("[WARN] scrollCombineModels not found", flush=True)
            return

        # Try to use existing container/layout
        container = self.container_models
        layout = None
        if container:
            layout = container.layout()
            if not layout:
                # Try finding by name
                layout = self.main_window.findChild(QtWidgets.QLayout, "layoutCombineModels")
        
        # If we still don't have a usable layout, replace the container
        if not container or not layout:
            print("[DEBUG] Layout not found or container missing. Replacing container.", flush=True)
            container = QtWidgets.QWidget()
            container.setObjectName("containerCombineModels")
            layout = QtWidgets.QVBoxLayout(container)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)
            scroll.setWidget(container)
            self.container_models = container
        else:
            print("[DEBUG] Using existing container and layout", flush=True)

        try:
            # Discover models using the unified catalog loader for consistency
            catalog = model_catalog.load_all(self.main_window.pm_dir)
            self.fpf_models = sorted(catalog.get("fpf", []))
            print(f"[DEBUG] Found {len(self.fpf_models)} FPF models", flush=True)
            
            # Clear existing items
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
            
            # Add checkboxes
            for model_str in self.fpf_models:
                cb = QtWidgets.QCheckBox(model_str)
                # Object name for easier finding later: check_combine_provider_model
                safe_name = model_str.replace(":", "_").replace(" ", "_").replace("/", "_")
                cb.setObjectName(f"check_combine_{safe_name}")
                layout.addWidget(cb)
                
        except Exception as e:
            print(f"[WARN] Combine_UI_Handler.populate_models failed: {e}", flush=True)

    def load_config(self, full_config: Dict[str, Any]):
        """Reads the 'combine' section and sets widget states."""
        try:
            combine_cfg = full_config.get("combine", {})
            
            # Enabled
            if self.chk_enable:
                self.chk_enable.setChecked(bool(combine_cfg.get("enabled", False)))
            
            # Models (check boxes)
            # Config format expected: models: [{provider: p, model: m}, ...]
            models_cfg = combine_cfg.get("models", [])
            if not isinstance(models_cfg, list):
                models_cfg = []
            
            # Create a set of "provider:model" strings from config for fast lookup
            selected_models = set()
            for m in models_cfg:
                if isinstance(m, dict):
                    p = m.get("provider", "").strip()
                    mod = m.get("model", "").strip()
                    if p and mod:
                        selected_models.add(f"{p}:{mod}")
            
            # Iterate checkboxes and set state
            if self.container_models:
                for cb in self.container_models.findChildren(QtWidgets.QCheckBox):
                    txt = cb.text().strip()
                    if txt in selected_models:
                        cb.setChecked(True)
                    else:
                        cb.setChecked(False)

        except Exception as e:
            print(f"[WARN] Combine_UI_Handler.load_config failed: {e}", flush=True)

    def gather_values(self) -> Dict[str, Any]:
        """Returns the 'combine' dictionary for config.yaml."""
        vals = {}
        try:
            # Enabled
            if self.chk_enable:
                vals["enabled"] = bool(self.chk_enable.isChecked())
            
            # Models
            selected_models = []
            if self.container_models:
                for cb in self.container_models.findChildren(QtWidgets.QCheckBox):
                    if cb.isChecked():
                        txt = cb.text().strip()
                        if ":" in txt:
                            prov, mod = txt.split(":", 1)
                            selected_models.append({
                                "provider": prov.strip(),
                                "model": mod.strip()
                            })
            vals["models"] = selected_models

        except Exception as e:
            print(f"[WARN] Combine_UI_Handler.gather_values failed: {e}", flush=True)
        
        return vals
