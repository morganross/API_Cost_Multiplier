from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from .gui_utils import read_yaml, write_yaml


# New global-only schema defaults (no per_provider, no burst)
# All runs are staggered by at least 1/qps; require qps > 0.
DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "max_concurrency": 12,
    "qps": 2.0,
}


def get_fpf_yaml_path(pm_dir: Path) -> Path:
    """
    Resolve path to FilePromptForge fpf_config.yaml given the project root (pm_dir).
    """
    return pm_dir / "FilePromptForge" / "fpf_config.yaml"


def read_fpf_yaml(fpf_yaml: Path) -> Dict[str, Any]:
    """
    Read FPF YAML. Returns {} on error/missing file.
    """
    try:
        return read_yaml(fpf_yaml)
    except Exception:
        return {}  # Treat as empty; caller can fill defaults as needed.


def write_fpf_yaml(fpf_yaml: Path, data: Dict[str, Any]) -> None:
    """
    Write FPF YAML, creating parent directories if needed.
    """
    fpf_yaml.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(fpf_yaml, data)


def _deep_update(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """
    In-place-like deep update: returns a new dict containing dst overlaid with src.
    Dicts are merged; other types are replaced.
    """
    out = dict(dst or {})
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def merge_concurrency(old_root: Dict[str, Any], new_concurrency: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a new root dict where only the 'concurrency' subtree is deep-merged
    with the provided new_concurrency subtree. Preserves all other keys.
    """
    res = dict(old_root or {})
    existing = res.get("concurrency", {})
    merged = _deep_update(existing, new_concurrency or {})
    res["concurrency"] = merged
    return res


def _map_old_schema_to_new(conc_old: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map legacy concurrency schema (with per_provider/rate_limit/burst) to the new global-only schema.
    - qps: choose the minimum positive per-provider qps if present, else DEFAULTS['qps']
    - max_concurrency: keep top-level max_concurrency if present
    - enabled: keep top-level enabled if present
    Ignore per-provider max_concurrency and any burst values entirely.
    """
    if not isinstance(conc_old, dict):
        return {}

    out: Dict[str, Any] = {}
    # enabled
    if "enabled" in conc_old:
        try:
            out["enabled"] = bool(conc_old.get("enabled"))
        except Exception:
            pass
    # max_concurrency
    if "max_concurrency" in conc_old:
        try:
            out["max_concurrency"] = int(conc_old.get("max_concurrency"))
        except Exception:
            pass

    # qps from per_provider.*.rate_limit.qps (min positive), if available
    pp = conc_old.get("per_provider") or {}
    if isinstance(pp, dict) and pp:
        min_pos_qps = None
        for _k, pv in pp.items():
            if not isinstance(pv, dict):
                continue
            rl = pv.get("rate_limit") or {}
            try:
                qps = float(rl.get("qps", 0.0))
            except Exception:
                qps = 0.0
            if qps and qps > 0.0:
                if min_pos_qps is None or qps < min_pos_qps:
                    min_pos_qps = qps
        if min_pos_qps is not None:
            out["qps"] = float(min_pos_qps)

    return out


def validate_concurrency(c: Dict[str, Any]) -> None:
    """
    Validate basic invariants for new global-only concurrency settings.
    Raises ValueError on invalid input.
    - max_concurrency must be an integer >= 1
    - qps must be a float > 0.0 (staggering is always enforced)
    """
    if not isinstance(c, dict):
        raise ValueError("concurrency must be a dict")

    try:
        global_mc = int(c.get("max_concurrency", DEFAULTS["max_concurrency"]))
    except Exception:
        raise ValueError("max_concurrency must be an integer")
    if global_mc < 1:
        raise ValueError("max_concurrency must be >= 1")

    try:
        qps = float(c.get("qps", DEFAULTS["qps"]))
    except Exception:
        raise ValueError("qps must be a float")
    if qps <= 0.0:
        raise ValueError("qps must be > 0.0 (staggering enforces at least 1/qps seconds between starts)")


def effective_concurrency(existing_root: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute the effective concurrency dict by overlaying DEFAULTS with any existing values.
    Existing values win. DEFAULTS fill missing keys.
    Also maps legacy per_provider schema to new fields when found.
    Returns only the 'concurrency' subtree (not the full root).
    """
    existing_conc = {}
    if isinstance(existing_root, dict):
        existing_conc = existing_root.get("concurrency", {}) or {}
        if not isinstance(existing_conc, dict):
            existing_conc = {}

    # If old schema keys present, derive new keys
    mapped_from_old = _map_old_schema_to_new(existing_conc)

    # Overlay in order: DEFAULTS <- existing_conc (new keys if any) <- mapped_from_old
    # mapped_from_old takes precedence for derived qps if user hasn't explicitly set a top-level qps yet.
    base = _deep_update(DEFAULTS, existing_conc)
    eff = _deep_update(base, mapped_from_old)

    # Ensure required keys exist
    if "enabled" not in eff:
        eff["enabled"] = DEFAULTS["enabled"]
    if "max_concurrency" not in eff:
        eff["max_concurrency"] = DEFAULTS["max_concurrency"]
    if "qps" not in eff:
        eff["qps"] = DEFAULTS["qps"]

    return eff
