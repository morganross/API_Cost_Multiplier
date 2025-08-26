#!/usr/bin/env python3
"""
run_gptr_local.py

Side-effect wrapper that forces the local `gpt-researcher` source (process_markdown/gpt-researcher)
to be preferred on sys.path, and provides small helper functions to run GPT-Researcher
from the local source without using the installed package.

Usage:
- Import for side-effect (minimal change to callers):
    import process_markdown.run_gptr_local

  Doing this before any code that imports `gpt_researcher` will ensure the local
  source is used.

- Programmatic helpers:
    from process_markdown.run_gptr_local import run_cli_equivalent, run_detailed_report

    md = run_cli_equivalent("my query", report_type="detailed_report")
    # or (async)
    import asyncio
    from process_markdown.run_gptr_local import run_detailed_report_async
    result = asyncio.run(run_detailed_report_async("my query"))

- CLI:
    python process_markdown/run_gptr_local.py "why is X happening?" --report_type detailed_report

Notes:
- This file only manipulates sys.path for the running process; it does not uninstall
  or otherwise mutate installed packages.
- Make sure dependencies are installed in your environment (pip install -r process_markdown/gpt-researcher/requirements.txt).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
import asyncio

# Ensure local gpt-researcher source is preferred over installed package.
def ensure_local_gptr_precedence() -> None:
    """
    Insert the local process_markdown/gpt-researcher path (and its parent) at the
    front of sys.path so local sources take precedence over any installed package.
    This is idempotent and safe to call multiple times.
    """
    base = Path(__file__).resolve().parent  # process_markdown/
    local_gptr_src = base / "gpt-researcher"
    if local_gptr_src.is_dir():
        local_gptr_src_str = str(local_gptr_src)
        if local_gptr_src_str not in sys.path:
            sys.path.insert(0, local_gptr_src_str)
        # Also ensure the parent folder (repo root / process_markdown) is present (safety)
        repo_parent = str(local_gptr_src.parent)
        if repo_parent not in sys.path:
            # Insert after the direct gptr path so gptr dir is still first
            sys.path.insert(1, repo_parent)
    else:
        # If the folder doesn't exist, do nothing. Caller may still use installed package.
        pass

# Apply the precedence change immediately on import (side-effect).
ensure_local_gptr_precedence()

# Load .env if present in process_markdown folder (makes keys available to local gpt-researcher code)
try:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)
except Exception:
    # best-effort; do not fail import if dotenv isn't available or file missing
    try:
        load_dotenv()
    except Exception:
        pass

# Provide convenience helpers that call local gpt-researcher APIs
def _get_tone_enum(tone_str: str):
    """
    Map simple tone string to the local gpt_researcher Tone enum if available.
    Falls back to passing the string through if the enum isn't importable.
    """
    try:
        from gpt_researcher.utils.enum import Tone
        mapping = {
            "objective": Tone.Objective,
            "formal": Tone.Formal,
            "analytical": Tone.Analytical,
            "persuasive": Tone.Persuasive,
            "informative": Tone.Informative,
            "explanatory": Tone.Explanatory,
            "descriptive": Tone.Descriptive,
            "critical": Tone.Critical,
            "comparative": Tone.Comparative,
            "speculative": Tone.Speculative,
            "reflective": Tone.Reflective,
            "narrative": Tone.Narrative,
            "humorous": Tone.Humorous,
            "optimistic": Tone.Optimistic,
            "pessimistic": Tone.Pessimistic
        }
        return mapping.get(tone_str, Tone.Objective)
    except Exception:
        # If enum import fails, just return the raw string (some code paths may accept it)
        return tone_str

async def run_detailed_report_async(query: str, query_domains: Optional[List[str]] = None) -> str:
    """
    Async wrapper that runs backend.report_type.DetailedReport.run() and returns the report string.
    """
    # Import after sys.path adjustment so we pick up local backend package
    from backend.report_type import DetailedReport  # type: ignore

    detailed_report = DetailedReport(
        query=query,
        query_domains=query_domains or [],
        report_type="research_report",
        report_source="web_search",
    )

    report = await detailed_report.run()
    return report

def run_detailed_report(query: str, query_domains: Optional[List[str]] = None) -> str:
    """
    Sync wrapper around run_detailed_report_async
    """
    return asyncio.run(run_detailed_report_async(query, query_domains=query_domains))

async def _run_gpt_researcher_async(query: str, query_domains: Optional[List[str]], report_type: str, tone: str, encoding: str) -> str:
    """
    Internal async helper to run GPTResearcher for non-detailed report types.
    """
    from gpt_researcher import GPTResearcher  # type: ignore

    tone_val = _get_tone_enum(tone)

    researcher = GPTResearcher(
        query=query,
        query_domains=query_domains or [],
        report_type=report_type,
        tone=tone_val,
        encoding=encoding
    )

    await researcher.conduct_research()
    report = await researcher.write_report()
    return report

def run_cli_equivalent(query: str, report_type: str = "research_report", tone: str = "objective", encoding: str = "utf-8", query_domains: Optional[List[str]] = None) -> str:
    """
    Synchronous convenience function that mirrors the behavior of cli.py:
    - If report_type == 'detailed_report' -> uses backend.report_type.DetailedReport
    - Otherwise -> uses gpt_researcher.GPTResearcher
    Returns the generated report string (markdown).
    """
    if report_type == "detailed_report":
        return run_detailed_report(query, query_domains=query_domains)
    return asyncio.run(_run_gpt_researcher_async(query, query_domains=query_domains, report_type=report_type, tone=tone, encoding=encoding))

# Small CLI for quick manual usage (keeps parity with original cli but uses local source)
if __name__ == "__main__":
    import argparse
    from argparse import RawTextHelpFormatter
    from uuid import uuid4
    import os as _os

    parser = argparse.ArgumentParser(
        description="Run local gpt-researcher (prefer local source) and return markdown report.",
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument("query", type=str, help="The query to conduct research on.")
    parser.add_argument("--report_type", type=str, required=True, help="Report type (e.g., detailed_report or research_report)")
    parser.add_argument("--tone", type=str, default="objective", help="Tone of report")
    parser.add_argument("--encoding", type=str, default="utf-8", help="Encoding for output file")
    parser.add_argument("--query_domains", type=str, default="", help="Comma-separated list of domains")

    args = parser.parse_args()

    # run
    qd = args.query_domains.split(",") if args.query_domains else []
    if args.report_type == "detailed_report":
        result = run_detailed_report(args.query, query_domains=qd)
    else:
        result = run_cli_equivalent(args.query, report_type=args.report_type, tone=args.tone, encoding=args.encoding, query_domains=qd)

    # write to outputs/uuid.md to mimic CLI behavior
    out_dir = Path(_os.path.join(os.path.dirname(__file__), "outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid4()}.md"
    out_path.write_text(result, encoding="utf-8")
    print(f"Report written to: {out_path}")
