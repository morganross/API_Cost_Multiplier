Proposed Plan — Avoid copying the multi_agents tree into temp directories

- Decision: Stop copying the multi_agents code to temporary run directories. The current copy-then-write approach was intended to ensure a runtime `task.json` was present for the multi_agents example, but it has introduced complexity and intermittent failures (missing task.json in preserved temp dirs, race conditions, and mismatched paths).
- New approach (recommended):
  1. Do not copy files into temp directories. Instead, call the existing multi_agents code in-place by importing it and passing the merged `task` (runtime task dict) directly into the multi_agents runner API (e.g., call `run_research_task(task_dict)` if available).
     - Rationale: This avoids filesystem races, ensures the code executed is the single canonical source in the repo, and lets us pass the runtime configuration programmatically.
     - Implementation notes:
       - If `multi_agents.main` exposes `run_research_task` (or similar), call it directly with the merged runtime task dict. If it does not, add a small entrypoint wrapper in `gpt-researcher-3.2.9/multi_agents/main.py` that accepts a task dict and runs the workflow in-process.
       - Ensure environment variables (.env) are loaded before calling, and run under the same process so relative imports and resources resolve consistently.
  2. Keep writing a runtime `task.json` only for audit/debug purposes (optional), but do not rely on it for the run. If a file is still needed, write it to a single known location (e.g., `./temp_runtime_task.json`) and pass the dict directly as the primary source of truth.
  3. Preserve the current `ma_runner` safeguards (atomic write and preserved tmp dirs) for debugging, but make them secondary; the main runner should call the code directly and programmatically.
  4. Update `ma_runner_wrapper` and `process-markdown-ma/ma_runner.py` to prefer programmatic invocation over copying. Only fall back to a copy-based approach if the in-process API is not available.
  5. Benefits:
     - Eliminates file-copy race conditions and the "missing task.json" errors.
     - Simplifies debugging because only one code path is executed.
     - Faster runs (no file copy overhead) and easier to instrument (in-process logging).
  6. Backward compatibility:
     - Keep a minimal compatibility shim that, if passed a `task.json` path, loads it and calls the same programmatic runner — enabling manual runs if desired.

MA Issue Log — "missing task.json / intermittent MA run failures"
Summary
- Symptom: Intermittent MA (multi_agents) runs failing with FileNotFoundError for the runtime task.json in temp run directories, e.g.:
  - One MA run failed: [Errno 2] No such file or directory: './outputs/run_1755464768_Report on changes to the entity over tim/3783f33850774df9b0df6eccbcd78a89.md'
- Recent MA retry result (successful): C:\dev\postop\temp_gpt_researcher_reports\ma_report_8b4a9233de634cfeaa6881abb4a2ce6b.md

Number of attempted fixes so far: 4

Chronological record of fixes & actions attempted (4 attempts)
1) Initial discovery and small fixes
   - Action: Ensured gpt_researcher_client returns (report_path, model_name) and used model_name for filenames.
   - Rationale: Helpful for traceability.

2) Atomic write + chdir (first major fix)
   - Action: Updated process-markdown-ma/ma_runner.py to write the merged runtime task.json atomically (write to .tmp then os.replace) and chdir into the temp run directory before importing/running the multi_agents code.
   - Rationale: Prevent the MA runtime from reading the repo task.json or a partially-written file.

3) Copy-then-write approach (strengthening)
   - Action: Copy the multi_agents tree into the temp run directory while skipping the task.json, then atomically write the runtime task.json into the temp copy.
   - Rationale: Eliminates race where copying might overwrite the written runtime task.json.

4) Retries + wrapper changes + reorder execution
   - Action A: Added a retry wrapper in process-markdown/ma_runner_wrapper.py to attempt MA runs twice (with backoff).
   - Action B: Reordered process-markdown-noeval to run MA runs first and abort the run if any MA fails (per your instruction).
   - Action C: Added scripts/run_ma_retry.py to re-run MA-only tasks for validation.

Files examined & findings (these entries are now recorded after reading the code)

1) process-markdown-ma/ma_runner.py
- Purpose: Creates a temporary run directory, copies a prototype multi_agents tree into it (now copying all files except task.json), writes a merged runtime task.json into that temp copy atomically, chdirs into the temp run dir, imports multi_agents.main and calls run_research_task, then saves the returned report to temp_gpt_researcher_reports.
- Key behaviors impacting issue:
  - Uses tempfile.mkdtemp to create tmp_root.
  - Copies files except task.json; writes runtime task.json with os.replace for atomicity.
  - Changes cwd to tmp_root and inserts tmp_root at start of sys.path before import, ensuring imports resolve to the temp copy.
  - Cleans up tmp_root after run (rmtree in finally).
- Notes:
  - This copy-then-write approach addresses prior races where copying could overwrite runtime task.json.
  - Because tmp_root is removed in finally, failing runs remove artifacts; for debugging we sometimes need to preserve them — current code removes tmp_root (we could modify to preserve on failure).

2) process-markdown/ma_runner_wrapper.py
- Purpose: Dynamically load process-markdown-ma/ma_runner.py and call run_ma_for_query concurrently. Loads repository multi_agents/task.json as base_overrides and merges with per-run overrides.
- Key behaviors:
  - Loads base task.json once and passes it into each MA run as overrides.
  - Originally invoked runs via asyncio.gather with direct calls; was modified to wrap each call with a retry helper (2 attempts, backoff).
  - On exception prints "One MA run failed: {res}" and continues (initially); we later relied on noeval orchestrator to abort if MA fails.
- Notes:
  - Wrapper dynamically imports the ma_runner module from the process-markdown-ma directory (prototype), not the gpt-researcher multi_agents folder. That is intentional, to let the prototype be a stable runner.
  - Base task.json is read and merged; if load fails it proceeds without base overrides.

3) process-markdown-noeval/process_markdown_noeval.py
- Purpose: Orchestrator used for safe/no-eval tests. It now runs MA runs first (3 attempts), aborting the entire process if any MA run fails (per your instruction). It then runs research_report and deep runs.
- Key behaviors:
  - Calls run_concurrent_ma(query_prompt, num_runs=1) serially three times.
  - On MA failure, prints and returns early (abort).
  - Moves produced reports into a run-specific folder.
- Notes:
  - This enforces MA-first behavior and early termination on MA failure as requested.
  - Helpful for CI/testing to detect MA instability immediately.

4) process-markdown/process_markdown.py
- Purpose: Production orchestrator (original main). It previously ran research, deep, then MA; we observed MA issues and implemented a separate noeval variant and wrapper changes. Current production file still calls MA after research/deep (was not modified here in this session).
- Key behaviors:
  - Builds query prompt, runs run_concurrent_research for research and deep, then calls ma_runner_wrapper.run_concurrent_ma for MA (3 runs) and combines generated candidates for evaluation.
- Notes:
  - To strictly enforce MA-first behavior in production, the same reordering we applied in process-markdown-noeval should be applied here (if desired). Currently only the noeval script was updated to abort early; process_markdown.py still follows original order.

5) process-markdown/gpt_researcher_client.py
- Purpose: Programmatic interface to gpt-researcher. Builds the prompt, runs GPTResearcher programmatically, saves returned content to temp_gpt_researcher_reports, and returns (path, model_name).
- Key behaviors:
  - run_gpt_researcher_programmatic returns (path, model_name) now.
  - run_concurrent_research uses loop.run_in_executor with asyncio.run inside to call the async function multiple times concurrently — this spawns nested event loops in worker threads; it works but is fragile.
- Notes:
  - Model name extraction is best-effort: checks researcher.cfg, researcher.llm attributes, then environment fallback.
  - Concurrency approach could be improved by creating tasks directly if using same event loop.

6) process-markdown/llm_doc_eval_client.py
- Purpose: Prepares temporary directory for evaluation, copies candidate reports into temp_eval_dir, calls llm_doc_eval.api.run_pairwise_evaluation(temp_eval_dir) and uses get_best_report_by_elo to pick the winner.
- Key behaviors:
  - Creates temp_eval_dir (unique), clears DOC_PATHS, copies report files, runs run_pairwise_evaluation, calls get_best_report_by_elo(DB_PATH, DOC_PATHS).
  - No longer auto-deletes the temp eval dir (cleanup handled by caller).
- Notes:
  - If MA produced a report path that points into outputs/ and that file was removed or moved before evaluation, copy could fail — ensure report paths are valid and accessible.

7) process-markdown/file_manager.py
- Purpose: Utility for locating md files, computing mirrored output paths, creating output directories, and copying files.
- Key behaviors:
  - get_output_path computes a mirrored path relative to input_base_dir.
  - create_output_dirs uses os.makedirs with exist_ok=True and raises on error.
- Notes:
  - File copy/move errors reported here should be surfaced to understand "No such file or directory" errors when copying best report into outputs.

8) gpt-researcher-3.2.9/multi_agents/main.py (read)
- Purpose: Multi-agent example entrypoint (LangGraph-based). The prototype exposes a coroutine run_research_task which reads task.json (from cwd multi_agents/task.json) and runs the LangGraph orchestrated agents.
- Key behaviors observed:
  - The implementation reads multi_agents/task.json relative to cwd (not necessarily via an argument).
  - The runner triggers multiple agents and writes artifacts into outputs directories under current working dir.
- Notes:
  - Because ma_runner chdirs into the temp_parent (tmp_root) before import, multi_agents.main reading task.json relative to cwd should read the task.json we wrote into the temp copy (dst_multi_agents/task.json) — this is the intended behavior of the copy-then-write approach.
  - However there are code paths inside the multi_agents example that may create additional temp dirs or expect files at other paths; those could cause "No such file" errors if outputs are written to a different location and the wrapper expects them elsewhere.

9) gpt-researcher-3.2.9/multi_agents/task.json (read)
- Purpose: Template for MA runs (defines query, max_sections, publish formats, agent parameters).
- Key fields:
  - "query": string
  - "max_sections": integer (controls number of sections)
  - "publish_formats": dict (markdown/docx/pdf)
  - "guidelines", "max_iterations", etc.
- Notes:
  - Task.json used as base template and merged with overrides by the wrapper; important to ensure merged fields remain valid for the multi_agents runner.

Root causes & current diagnosis
- The original race condition (task.json overwritten/ignored) appears mitigated by:
  - Copy-then-write approach (we ensure the temp copy contains the runtime task.json).
  - Chdir into tmp_parent and insert temp_parent into sys.path before importing multi_agents.main.
- Residual intermittent failures happen at the MA runtime (file not found when moving outputs into expected outputs/ path). Causes:
  - MA runtime may fail to write expected output files in time, or writes to a different path than the wrapper expects.
  - MA may create sub-processes or use other temp dirs leading to missing files after the wrapper cleaned tmp_root (we remove tmp_root in finally; failing runs could be losing artifacts before collection).
  - External runtime errors (WeasyPrint lib missing, SSL errors scraping PDFs) cause some agents to error and possibly not produce output.

Immediate recommendations
- Preserve tmp_root for failed runs (do not delete on exception) so we can inspect exact multi_agents outputs and logs produced by the MA runtime (task.json, outputs dir, logs, etc.). Currently ma_runner deletes tmp_root in finally; change to preserve on failure.
- Increase retry attempts (we set 2 attempts; consider 3) with exponential backoff.
- Add instrumentation to multi_agents/main.py to log the absolute path of the task.json it reads and the outputs it writes (so we can confirm paths).
- For robust collection: after successful MA run, copy outputs from tmp_root/multi_agents/outputs or other paths into a central run_out_dir before deleting tmp_root — ensure wrapper looks for outputs in the same location.
- Modify ma_runner to not delete tmp_root until wrapper confirms output was successfully moved; or compress and archive tmp_root on failure for debugging.

Next steps I will take if you confirm
- Append these file summaries and recommendations to MA_issue_log.md (done here).
- Make one of the recommended code changes (e.g., preserve tmp_root on failure and increase retries) and re-run a MA-only test to collect preserved temp run dirs for forensic inspection (ACT mode).
- Or if you prefer, I can implement the instrumentation inside multi_agents/main.py to log the exact task.json path and output files (requires modifying gpt-researcher files).

Please confirm which change you want next:
- "preserve tmp_root on failure and retry MA-only" (recommended)
- "increase retries to 3 and rerun MA-only"
- "instrument multi_agents/main.py to log task.json & outputs" (requires editing multi_agents)
- "stop here and provide the MA_issue_log.md summary" (no further changes)

---

Append: Results of last auto-run & new thoughts

Last auto-run summary
- Auto-run attempts: 10 (auto_run_noeval_until_9.py; MAX_ATTEMPTS=100 but the session cycled; stopped when max attempts was reached in previous run)
- Per-attempt produced reports: each attempt produced 1 report (the MA report in temp_gpt_researcher_reports).
- Final result: 1 report produced per run; not reaching target 9 reports in a single run.
- Key failures observed in that run:
  - MA intermittent task.json missing errors (preserved temp run dirs printed: examples include C:\Users\kjhgf\AppData\Local\Temp\gptr_ma_run_7dujd31a, ..._kgrugwlv, ..._fbqcnwom, ..._4pr5w1pi, ..._d9bvi226, ..._0de4cv9g, etc.)
  - gpt-researcher errors:
    * 'charmap' codec can't encode characters — Windows encoding issue when writing/outputting certain characters.
    * OpenAI API 429 insufficient_quota — research and deep runs failed due to quota.
  - WeasyPrint native libs missing — PDF conversion failed but MD and DOCX were written.

New thoughts / next recommendations
- To reach 9 reports per run quickly, eliminate external blockers:
  1) Fix OpenAI quota (use an account with capacity or mock LLMs) — otherwise research/deep runs will fail with 429.
  2) Set PYTHONIOENCODING=utf-8 for subprocesses to avoid Windows charmap errors.
  3) Disable PDF publishing in the runtime task.json overrides (publish_formats -> markdown only) so missing native libs don't abort or cause errors.
- For the MA intermittent failure, examine preserved tmp run dirs now to find why task.json is reported missing in some preserved dirs (I can list and show their task.json and outputs).
- If you want me to continue attempts regardless of quota, I can keep the auto-run running longer, but without quota the research/deep steps will likely keep failing.
- Recommended immediate action: I will append this last-run summary (done) and if you confirm, I will inspect the preserved temp run dirs now and report exact file listings and the task.json contents.

Please confirm: I will now (choose one)
- "Inspect preserved tmp run dirs" (I will list the preserved dirs and read task.json + outputs)
- "Apply quick env fixes (set PYTHONIOENCODING + disable PDF) and re-run one attempt"
- "Stop and leave logs as-is"

</plan_mode_respond>
