import asyncio
import importlib.util
import os
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
os.chdir(str(repo_root))

spec = importlib.util.spec_from_file_location("ma_runner", "process-markdown-ma/ma_runner.py")
ma_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ma_runner)

async def main():
    try:
        # Minimal runtime task overrides: small report, markdown only to avoid PDF/native deps
        overrides = {
            "max_sections": 1,
            "publish_formats": {"markdown": True, "pdf": False, "docx": False}
        }
        print("Starting MA run (test)...")
        path = await ma_runner.run_ma_for_query("Test run for MA (single)", overrides)
        print("MA produced:", path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("MA run failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
