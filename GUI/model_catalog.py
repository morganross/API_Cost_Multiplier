from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import importlib.util
import re

# Minimal YAML reader without introducing new deps
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        if yaml is not None:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data
            return {}
        # Fallback: naive parser (expects simple key: mappings)
        out: dict = {}
        with path.open("r", encoding="utf-8") as f:
            current_root = None
            for line in f:
                if not line.strip():
                    continue
                if not line.startswith(" "):
                    # root key
                    m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*$", line.strip())
                    if m:
                        current_root = m.group(1)
                        out[current_root] = {}
                    else:
                        current_root = None
                else:
                    if current_root is None:
                        continue
                    m = re.match(r"^\s+([A-Za-z0-9._:\-]+)\s*:\s*$", line)
                    if m:
                        key = m.group(1)
                        out[current_root][key] = {}
        return out
    except Exception:
        return {}


def _sanitize_for_object_name(text: str) -> str:
    # Turn provider:model into a safe Qt objectName fragment
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def discover_fpf_models(pm_dir: Path) -> List[str]:
    """
    Discover FilePromptForge providers and their ALLOWED_MODELS.
    Returns a list of 'provider:model' strings.
    """
    results: List[str] = []
    providers_dir = pm_dir / "FilePromptForge" / "providers"
    if not providers_dir.exists():
        return results

    for entry in providers_dir.iterdir():
        try:
            if not entry.is_dir():
                continue
            provider_name = entry.name
            module_path = entry / f"fpf_{provider_name}_main.py"
            if not module_path.exists():
                continue

            spec = importlib.util.spec_from_file_location("fpf_provider_module", str(module_path))
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            allowed = getattr(mod, "ALLOWED_MODELS", None)
            if isinstance(allowed, (set, list, tuple)):
                for m in sorted(str(x) for x in allowed):
                    results.append(f"{provider_name}:{m}")
        except Exception:
            # Keep robust; skip broken providers
            continue
    return results


def discover_registry_models(pm_dir: Path) -> Dict[str, List[str]]:
    """
    Scan model_registry/providers/*.yaml and return models per provider key in the YAML.
    We flatten into provider:model strings.
    Example structure expected (simplified):
      openai:
        gpt-4.1: { ... }
        gpt-4o:  { ... }
      google:
        gemini-2.5-flash: { ... }
    """
    out: Dict[str, List[str]] = {}
    prov_dir = pm_dir / "model_registry" / "providers"
    if not prov_dir.exists():
        return out

    for yml in prov_dir.glob("*.yaml"):
        data = _read_yaml(yml)
        # Expect exactly one root key like 'openai' mapping to models mapping
        for provider_key, models_map in data.items():
            if not isinstance(models_map, dict):
                continue
            lst: List[str] = out.setdefault(provider_key, [])
            for model_key in models_map.keys():
                # model_key is the id (e.g., 'gpt-4.1')
                lst.append(f"{provider_key}:{model_key}")
            lst.sort()
    return out


def load_all(pm_dir: Path) -> Dict[str, List[str]]:
    """
    Build the catalog for each report type section:
      - 'gptr': provider:model from registry (e.g., openai, google, openrouter, anthropic)
      - 'dr'  : same as gptr (GPTR deep research uses same pool)
      - 'ma'  : same as gptr (runner stores only model field for MA, but we label as provider:model)
      - 'fpf' : provider:model from FilePromptForge ALLOWED_MODELS
    Returns { 'gptr': [...], 'dr': [...], 'ma': [...], 'fpf': [...] }
    """
    # From registry
    reg = discover_registry_models(pm_dir)
    # Flatten for GPT-R (standard + deep) and MA
    pool: List[str] = []
    for provider, models in reg.items():
        pool.extend(models)
    pool = sorted(set(pool))

    # FPF from providers modules
    fpf = sorted(set(discover_fpf_models(pm_dir)))

    return {
        "gptr": pool[:],
        "dr": pool[:],
        "ma": pool[:],
        "fpf": fpf,
    }


def split_provider_model(text: str) -> Tuple[str, str]:
    """
    Given 'provider:model' return (provider, model).
    If no colon, provider is '', model is text.
    """
    if ":" in text:
        p, m = text.split(":", 1)
        return p.strip(), m.strip()
    return "", text.strip()


def checkbox_object_name(type_key: str, provider_model: str) -> str:
    """
    Stable objectName for a checkbox representing a provider:model under a report type.
    """
    return f"check_{_sanitize_for_object_name(type_key)}_{_sanitize_for_object_name(provider_model)}"
