"""
GPT-Researcher runner adapter.

Provides:
- async run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="research_report") -> list[(path, model)]
"""

from __future__ import annotations

from typing import List
from process_markdown.EXAMPLE_fucntions import gpt_researcher_client
from process_markdown.functions.pm_utils import normalize_report_entries


async def run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> List:
    """
    Use existing gpt_researcher_client to run concurrent research.
    Returns list of absolute paths (or tuples) to generated reports (may be empty on failures).
    """
    try:
        raw = await gpt_researcher_client.run_concurrent_research(query_prompt, num_runs=num_runs, report_type=report_type)
    except Exception as e:
        print(f"  GPT-Researcher ({report_type}) runs failed: {e}")
        return []
    return normalize_report_entries(raw)
