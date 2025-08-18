Deep Dive Plan — Diagnose & Harden MA integration (process-markdown / multi_agents)

Objective
- Perform an extreme deep dive into why multi-agent (MA) runs sometimes fail and ensure each run uses the intended runtime task.json (query + config).
- Produce a reproducible, auditable procedure to inspect, run, and harden the codebase so MA runs succeed reliably.

Scope
- Codepaths: process-markdown, process-markdown-noeval, process-markdown-ma (ma_runner), process-markdown/ma_runner_wrapper.
- Supporting code: gpt_researcher_client, llm_doc_eval_client (only for later verification), gpt-researcher multi_agents tree.
- Runtime artifacts: temp run dirs (tmp_root), runtime task.json, produced reports, logs.

High-level approach
1. Catalog all files that participate in MA runs and configuration.
2. Add deterministic steps to write the final runtime task.json into the temp run copy.
3. Ensure MA runs execute with the temp copy as cwd so they read the copy.
4. Add logging and validation (dump merged task.json) before run.
5. Add retry and diagnostics to capture failures and preserved temp dirs for analysis.
6. Run controlled tests, inspect produced files, and iterate until stable.

Files to read (priority order)
- process-markdown-ma/ma_runner.py (how runtime task.json is built & MA run invoked)
- process-markdown/ma_runner_wrapper.py (how wrapper calls ma_runner; what overrides passed)
- process-markdown/gpt_researcher_client.py (how model name is returned; how query built)
- process-markdown-noeval/process_markdown_noeval.py (how runs are orchestrated; renaming/moving)
- process-markdown/process_markdown.py (primary orchestrator for real runs)
- gpt-researcher-3.2.9/multi_agents/task.json (base template)
- gpt-researcher-3.2.9/multi_agents/main.py (MA entrypoint run_research_task)
- gpt-researcher-3.2.9/gpt_researcher/agent.py (how researcher provides LLM/model info)
- process-markdown/llm_doc_eval_client.py (evaluate integration)
- process-markdown/file_manager.py (paths)
- llm_doc_eval/api.py and engine/evaluator.py (for later evaluation flow & concurrency)
- process-markdown/config.yaml and gpt-researcher-3.2.9/.env(.example)
- Any logging / outputs under process-markdown-ma/outputs and temp_gpt_researcher_reports/

Step-by-step plan to read every necessary file and gather context
1. Read and summarize MA runner logic
   - Open: process-markdown-ma/ma_runner.py
   - Extract:
     - Where tmp_root is created
     - How template_path is chosen
     - How merged task.json is produced and written
     - When and how CWD and sys.path are changed and when import(main) occurs
     - How report output is written
   - Note any atomic write, chdir, and cleanup behavior.

2. Read and summarize wrapper behavior
   - Open: process-markdown/ma_runner_wrapper.py
   - Extract:
     - Whether wrapper loads base task.json and passes full dict or only overrides
     - How concurrency/gather is handled and exceptions are reported
   - Decide single-writer ownership (wrapper vs ma_runner).

3. Read orchestrator clients and rename logic
   - Open: process-markdown/gpt_researcher_client.py and process-markdown-noeval/process_markdown_noeval.py
   - Extract:
     - How query_prompt is built
     - How model_name is returned (researcher.cfg or researcher.llm)
     - Where returned values are unpacked and used to name/move files
   - Verify run_concurrent_research returns (path, model_name) tuples.

4. Inspect multi_agents template & code
   - Open: gpt-researcher-3.2.9/multi_agents/task.json and main.py
   - Extract:
     - Keys present in task.json (query, max_sections, publish formats, agent settings)
     - How run_research_task reads task.json: relative path or absolute?
     - If main.py reads task.json from cwd or embedded path.

5. Check environment & config files
   - Open: process-markdown/config.yaml and gpt-researcher-3.2.9/.env(.example)
   - Confirm expected env keys (SMART_LLM, FAST_LLM, OPENAI_API_KEY, etc.)

6. Read MA outputs & logs
   - Inspect temp run directory and outputs created during previous runs:
     - temp_gpt_researcher_reports/run_<ts>/
     - process-markdown-ma/outputs/
   - Capture failing run temp dirs for evidence.

7. Read evaluation and LLM registry (for downstream effects)
   - llm_doc_eval/api.py, llm_doc_eval/engine/evaluator.py, llm_doc_eval/models/registry.py
   - Understand concurrency limits and how results are persisted.

Concrete modifications to implement (if desired)
- Ensure single-writer semantics: pick ma_runner as sole writer of runtime task.json; wrapper passes only overrides (we implemented).
- Atomic write + chdir + import (we implemented).
- Optionally, change wrapper to create temp dir, write runtime task.json into it BEFORE copying multi_agents tree (even stronger).
- Add retry logic around ma_runner invocation in wrapper:
  - e.g., 2 retries with exponential backoff; preserve failing tmp_root for mitigation.
- Add diagnostic capture:
  - If MA run fails, do not delete tmp_root; compress and store for offline analysis; dump merged task.json into outputs.
- Add model_name propagation consistently (we implemented).

Commands and checks to run locally
- Syntax check updated files:
  - python -m py_compile process-markdown-ma/ma_runner.py
  - python -m py_compile process-markdown/gpt_researcher_client.py
- Dry-run no-eval (safe mode, uses existing test inputs):
  - set PYTHONPATH to process-markdown then run:
    - python process-markdown-noeval/process_markdown_noeval.py
- Run single MA task manually for deeper debug:
  - python -c "from process_markdown_ma.ma_runner import run_ma_for_query; import asyncio; print(asyncio.run(run_ma_for_query('test query')))"
  - Inspect printed merged task.json and the tmp run dir if failure occurs.

Deliverable to create now
- A document (this file) containing the exhaustive step list above.
- Next actions: implement optional stronger fix (copy-then-write), add retries, or preserve failing tmp dirs for analysis.

If you want, I will:
- Apply the stronger change (copy-then-write) to ma_runner now and re-run the pipeline (ACT mode), or
- Add retry logic in ma_runner_wrapper and re-run (ACT mode), or
- Preserve failing tmp dirs and provide a zip for offline analysis.

Which of those options do you want next? (reply with the chosen option)
</response>
</plan_mode_respond>
