import asyncio
import sys
from pathlib import Path

# Ensure process-markdown is on sys.path
repo_root = Path(__file__).resolve().parents[1]
proc_pm = repo_root / "process-markdown"
sys.path.insert(0, str(proc_pm))

from ma_runner_wrapper import run_concurrent_ma

async def main():
    query = "Report on changes to the entity over time."
    print("Starting MA retry for query:", query)
    results = await run_concurrent_ma(query, num_runs=2)
    print("MA retry results:", results)

if __name__ == "__main__":
    asyncio.run(main())
