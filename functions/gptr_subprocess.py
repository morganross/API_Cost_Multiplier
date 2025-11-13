import argparse
import asyncio
import json
import os
import sys

# Ensure project/package roots are on sys.path so absolute and relative imports work
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))       # .../api_cost_multiplier
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))  # .../
for _p in (_PROJECT_ROOT, _PACKAGE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Ensure monkey patches apply inside the subprocess as well
from api_cost_multiplier.patches import sitecustomize as _patches  # noqa: F401

try:
    from functions.gpt_researcher_client import run_gpt_researcher_programmatic  # type: ignore
except Exception:
    # Fallback in case the relative import path differs
    from api_cost_multiplier.functions.gpt_researcher_client import run_gpt_researcher_programmatic  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single GPT-Researcher report in a fresh subprocess.")
    parser.add_argument("--prompt-file", required=True, help="Path to a text file containing the query prompt.")
    parser.add_argument("--report-type", required=True, choices=["research_report", "deep"], help="Report type to generate.")
    return parser.parse_args()


async def _amain() -> int:
    args = parse_args()
    # Normalize to absolute path and retry a few short times to absorb races
    prompt_path = os.path.abspath(args.prompt_file)
    if not os.path.exists(prompt_path):
        import time
        retries = 5
        for _ in range(retries):
            time.sleep(0.2)
            if os.path.exists(prompt_path):
                break
        if not os.path.exists(prompt_path):
            print(json.dumps({"error": f"Prompt file not found: {prompt_path}"}), file=sys.stderr)
            return 2

    with open(args.prompt_file, "r", encoding="utf-8") as fh:
        prompt = fh.read()

    try:
        path, model = await run_gpt_researcher_programmatic(prompt, report_type=args.report_type)
    except Exception as e:
        print(json.dumps({"error": f"gpt-researcher failed: {e}"}), file=sys.stderr)
        return 1

    # Emit a single JSON line with the results to stdout
    print(json.dumps({"path": path, "model": model}, ensure_ascii=False))
    return 0


def main() -> None:
    # Ensure UTF-8 is enforced for subprocess IO on platforms (Windows in particular).
    # This sets the interpreter and stdio encoding so prints and file writes use UTF-8.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        rc = asyncio.run(_amain())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
