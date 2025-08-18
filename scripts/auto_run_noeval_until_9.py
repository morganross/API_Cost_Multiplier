#!/usr/bin/env python3
"""
Auto-run the no-eval pipeline until it produces 9 reports (or max attempts reached).
Runs process_markdown_noeval.py and parses its stdout for produced counts.

Usage:
  python scripts/auto_run_noeval_until_9.py

Behavior:
- Repeatedly runs the no-eval script.
- Parses lines like "Produced X reports for <file>:" and accumulates the produced count.
- Stops when total produced >= 9 or attempts >= max_attempts.
- Saves the last run's stdout/stderr to scripts/auto_run_noeval_last.log for debugging.
- Preserves temp run dirs when MA failures occur (ma_runner already preserves on failure).
"""
import subprocess
import sys
import os
import re
from pathlib import Path
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
NOEVAL_SCRIPT = REPO_ROOT / "process-markdown-noeval" / "process_markdown_noeval.py"
PYTHON = sys.executable
MAX_ATTEMPTS = 100
SLEEP_BETWEEN = 2  # seconds between attempts when quick retry

def run_once():
    env = os.environ.copy()
    # Ensure process-markdown is on PYTHONPATH so imports work
    pm_path = str(REPO_ROOT / "process-markdown")
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = pm_path + (os.pathsep + old_pythonpath if old_pythonpath else "")
    cmd = [PYTHON, str(NOEVAL_SCRIPT)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=str(REPO_ROOT))
    stdout_lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            text = line.decode("utf-8", errors="replace").rstrip("\n")
        except Exception:
            text = str(line)
        print(text)
        stdout_lines.append(text)
    proc.wait()
    return proc.returncode, "\n".join(stdout_lines)

def parse_produced_count(output_text):
    # Find lines like: "Produced N reports for <basename>:"
    matches = re.findall(r"Produced (\d+) reports? for", output_text)
    total = sum(int(m) for m in matches) if matches else 0
    return total

def main():
    total_produced = 0
    attempt = 0
    log_file = REPO_ROOT / "scripts" / "auto_run_noeval_last.log"
    while attempt < MAX_ATTEMPTS and total_produced < 9:
        attempt += 1
        print(f"\n=== Attempt {attempt} ===")
        rc, out = run_once()
        # save output for analysis
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(out)
        produced = parse_produced_count(out)
        total_produced = produced  # each run re-creates run folders; we consider per-run produced count
        print(f"Attempt {attempt} produced {produced} report(s). Total (this run): {total_produced}")
        if total_produced >= 9:
            print("Success: reached >= 9 reports.")
            break
        if attempt < MAX_ATTEMPTS:
            print(f"Will retry after {SLEEP_BETWEEN}s...")
            time.sleep(SLEEP_BETWEEN)
    if total_produced < 9:
        print(f"Stopped after {attempt} attempts. Produced {total_produced} reports (target 9). Check scripts/auto_run_noeval_last.log for details.")
        sys.exit(2)
    else:
        print("Completed: produced >= 9 reports.")
        sys.exit(0)

if __name__ == "__main__":
    main()
