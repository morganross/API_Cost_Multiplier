"""
Output manager: saving generated reports into mirrored output folder.

Provides:
- save_generated_reports(input_md_path, input_base_dir, output_base_dir, generated_paths) -> list[str]
"""

from __future__ import annotations

import os
import shutil
import yaml
from typing import List

from . import pm_utils


def save_generated_reports(input_md_path: str, input_base_dir: str, output_base_dir: str, generated_paths: dict) -> List[str]:
    """
    Copy generated files into the output folder that mirrors the input structure,
    using the naming scheme specified.

    generated_paths is expected to be a dict:
      {"ma": [...], "gptr": [...], "dr": [...]}
    where each list item may be either:
      - a path string, or
      - a tuple/list (path, model_name)
    The output filenames will include the report type (ma/gptr/dr), the run index,
    and the sanitized model name (model-only, no provider).
    """
    base_name = os.path.splitext(os.path.basename(input_md_path))[0]
    rel_output_path = os.path.relpath(input_md_path, input_base_dir)
    output_dir_for_file = os.path.dirname(os.path.join(output_base_dir, rel_output_path))
    os.makedirs(output_dir_for_file, exist_ok=True)

    saved: List[str] = []
    seen_src = set()

    def _unpack(item):
        if isinstance(item, (tuple, list)):
            p = item[0]
            model = item[1] if len(item) > 1 else None
        else:
            p = item
            model = None
        return p, model

    def _unique_dest(kind: str, idx: int, model_label: str) -> str:
        """
        Build a unique destination filename by appending a 3-char alphanumeric uid.
        Tries a few random uids; falls back to a counter suffix if necessary.
        """
        # Try random UIDs first
        for _ in range(10):
            uid = pm_utils.uid3()
            candidate = os.path.join(
                output_dir_for_file,
                f"{base_name}.{kind}.{idx}.{model_label}.{uid}.md",
            )
            if not os.path.exists(candidate):
                return candidate
        # Extremely unlikely fallback with a counter
        counter = 1
        while True:
            uid = pm_utils.uid3()
            candidate = os.path.join(
                output_dir_for_file,
                f"{base_name}.{kind}.{idx}.{model_label}.{uid}-{counter}.md",
            )
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    # Load one_file_only from config
    one_file_only = False
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cfg_path = os.path.join(repo_root, "config.yaml")
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as _fh:
                cfg = yaml.safe_load(_fh) or {}
                one_file_only = bool(cfg.get("one_file_only", False))
    except Exception:
        pass

    # Prepare MA list, optionally reduce to a single preferred artifact
    ma_items = list(generated_paths.get("ma", [])) if isinstance(generated_paths.get("ma", []), list) else []
    if one_file_only and ma_items:
        # Prefer .md, then .docx, then .pdf
        preferred_exts = [".md", ".docx", ".pdf"]
        selected = None
        for ext in preferred_exts:
            for it in ma_items:
                p, _m = _unpack(it)
                if isinstance(p, str) and os.path.splitext(p)[1].lower() == ext:
                    selected = [it]
                    break
            if selected:
                break
        if selected:
            ma_items = selected
        else:
            ma_items = [ma_items[0]]

    # MA
    for idx, item in enumerate(ma_items, start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("ma", idx, model_label)
        try:
            tmp_dest = dest + ".tmp"
            shutil.copy2(p, tmp_dest)
            try:
                os.replace(tmp_dest, dest)
            except Exception:
                shutil.move(tmp_dest, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            try:
                if os.path.exists(tmp_dest):
                    os.remove(tmp_dest)
            except Exception:
                pass
            print(f"    Failed to save MA report {p} -> {dest}: {e}")

    # GPT Researcher normal
    for idx, item in enumerate(generated_paths.get("gptr", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        if not model:
            # fallback to env if available
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("gptr", idx, model_label)
        try:
            tmp_dest = dest + ".tmp"
            shutil.copy2(p, tmp_dest)
            try:
                os.replace(tmp_dest, dest)
            except Exception:
                shutil.move(tmp_dest, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            try:
                if os.path.exists(tmp_dest):
                    os.remove(tmp_dest)
            except Exception:
                pass
            print(f"    Failed to save GPT-R report {p} -> {dest}: {e}")

    # Deep research
    for idx, item in enumerate(generated_paths.get("dr", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        if not model:
            model_env = os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM")
            model = model_env
        model_label = pm_utils.sanitize_model_for_filename(model)
        dest = _unique_dest("dr", idx, model_label)
        try:
            tmp_dest = dest + ".tmp"
            shutil.copy2(p, tmp_dest)
            try:
                os.replace(tmp_dest, dest)
            except Exception:
                shutil.move(tmp_dest, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            try:
                if os.path.exists(tmp_dest):
                    os.remove(tmp_dest)
            except Exception:
                pass
            print(f"    Failed to save Deep research report {p} -> {dest}: {e}")

    # FilePromptForge (FPF)
    for idx, item in enumerate(generated_paths.get("fpf", []), start=1):
        p, model = _unpack(item)
        if p in seen_src:
            continue
        model_label = pm_utils.sanitize_model_for_filename(model)
        # FPF writes .txt; keep a unique destination without changing extension
        # Reuse uid3 but with .txt suffix to reflect raw FPF responses
        # Build destination path mirroring the others but with .txt
        # We won't use _unique_dest because it appends .md; construct here explicitly
        # and ensure uniqueness with uid3 attempts.
        dest = None
        for _ in range(10):
            uid = pm_utils.uid3()
            candidate = os.path.join(
                output_dir_for_file,
                f"{base_name}.fpf.{idx}.{model_label}.{uid}.txt",
            )
            if not os.path.exists(candidate):
                dest = candidate
                break
        if dest is None:
            # Fallback with counter if somehow all 10 collided
            counter = 1
            while True:
                uid = pm_utils.uid3()
                candidate = os.path.join(
                    output_dir_for_file,
                    f"{base_name}.fpf.{idx}.{model_label}.{uid}-{counter}.txt",
                )
                if not os.path.exists(candidate):
                    dest = candidate
                    break
                counter += 1
        try:
            tmp_dest = dest + ".tmp"
            shutil.copy2(p, tmp_dest)
            try:
                os.replace(tmp_dest, dest)
            except Exception:
                shutil.move(tmp_dest, dest)
            saved.append(dest)
            seen_src.add(p)
        except Exception as e:
            try:
                if os.path.exists(tmp_dest):
                    os.remove(tmp_dest)
            except Exception:
                pass
            print(f"    Failed to save FPF report {p} -> {dest}: {e}")

    return saved
