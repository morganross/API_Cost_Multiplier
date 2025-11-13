# Implementation Plan — Fixes for Current Failures and Output Behavior (2025-11-03)

## Progress Log
- 2025-11-04:
  - Enforced single artifact for MA runs:
    - functions/MA_runner.py: publish_formats.docx set to False (only markdown emitted).
    - functions/output_manager.py: honors one_file_only from config.yaml, prefers .md for MA, and deduplicates saved sources across MA/GPTR/DR.
  - Constraint honored: no edits to vendor GPT‑Researcher files; any runtime adjustments will be applied via patches/sitecustomize.py.
  - Next steps (per plan):
    - Add GPTR prompt-file existence guard and one retry in our runner wrapper (no vendor edits).
    - Add OpenAI token parameter mapping and per-model caps via patches/sitecustomize.py (max_tokens → max_completion_tokens where required).
    - Strengthen FPF Google prompt preamble to require citations and reasoning; add a single targeted retry on validation failure (configurable).

- 2025-11-04:
  - FPF Google validation resilience implemented:
    - functions/fpf_runner.py: added Google-specific enhanced preamble for initial attempt (requires citations and a brief rationale). On validation failure, perform a single retry with a stronger preamble.
    - Retry preserves env/options and writes to response_<run>_retry.txt on success; logging integrated with logs/fpf_run.log.
    - No vendor edits to FilePromptForge internals; wrapper-only change.

Scope
- Session window: 2025-11-03 17:06:56–17:12:04 (latest timeline/chart).
- Addresses:
  1) FPF run failure despite grounding being “on”
  2) GPT‑Researcher string/type errors (“list has no attribute split” class of issues)
  3) GPTR missing prompt file
  4) Token cap errors on gpt‑4o (max_tokens too large)
  5) MA runs generating multiple artifacts (want exactly one per run)
- This plan references supporting docs found under /docs.

References (string/split issue)
- docs/generate_errors_report.md (Section: AttributeError: 'str' object has no attribute 'append')
- docs/MA_CLI_and_GPTR_integration_failure_report.md (Planner/writer normalization discussion)
- docs/ma_response_normalization_plan.md (Normalization approach and call sites)
- Additional mentions: docs/gptr_model_fix.md, docs/gemini_grounding_issue_report.md

Root Causes (from logs)
- FPF (Run 1 - google:gemini-2.5-flash-lite): Failure reason from logs:
  - “Provider response failed mandatory checks: missing grounding (web_search/citations) and reasoning (thinking/rationale). Enforcement is strict; no report may be written.”
  - fpf_run.log @ 2025-11-03 17:06:58.784/785
  - Note: Other FPF runs (earlier the same day) show “Run validated: web_search used and reasoning present.” Therefore grounding was configured, but this particular response lacked the required signals and strict validation blocked output.
- GPTR (Run 2 - gpt-4.1-mini): Missing prompt file path before GPTR_END.
- GPTR (Run 4 - gpt-4o): HTTP 400 — max_tokens too large (32000 vs model cap 16384).
- DR (Runs 6,7): gpt‑researcher programmatic run failed: 'list' object has no attribute 'split' (type normalization defect).
- MA runs (9–11): Multiple artifacts emitted per model (mix of .md + .docx and multiple outputs). Config has one_file_only: true but code does not enforce it.

Planned Changes

A) Fix the gpt‑researcher string/split normalization defects
- Goal: Ensure code never calls list/str methods on unexpected types; always normalize.
- Where to patch (local copy present):
  - api_cost_multiplier/gpt-researcher/gpt_researcher/skills/researcher.py
- Concrete change (from docs/generate_errors_report.md):
  - After: sub_queries = await self.plan_research(query, query_domains)
    normalize to list:
    ```
    if sub_queries is None:
        sub_queries = []
    elif isinstance(sub_queries, str):
        sub_queries = [sub_queries]
    elif not isinstance(sub_queries, (list, tuple)):
        try:
            sub_queries = list(sub_queries)
        except Exception:
            sub_queries = [str(sub_queries)]
    ```
  - Audit downstream concatenations:
    - If additional_research may be str OR list, guard joins:
      ```
      if isinstance(additional_research, str):
          research_data += additional_research
      else:
          research_data += ' '.join(additional_research)
      ```
- Rationale: Matches guidance from:
  - docs/generate_errors_report.md (#4)
  - docs/MA_CLI_and_GPTR_integration_failure_report.md
  - docs/ma_response_normalization_plan.md

B) Make MA produce exactly one artifact per run
- Current behavior:
  - MA_runner.run_multi_agent_runs() sets publish_formats = {markdown: True, pdf: False, docx: True}.
  - run_multi_agent_once() enumerates artifacts (.md/.docx/.pdf) and returns all found.
  - output_manager.save_generated_reports() saves all returned items (no regard to config one_file_only).
- Proposed changes:
  1) Disable DOCX by default for MA:
     - In api_cost_multiplier/functions/MA_runner.py, change publish_formats:
       ```
       "publish_formats": {
         "markdown": True,
         "pdf": False,
         "docx": False
       }
       ```
     - Make this read from top-level config (api_cost_multiplier/config.yaml) if present:
       - Add optional acm.ma.publish_formats override (future enhancement).
  2) Enforce one_file_only in code:
     - Respect config.yaml one_file_only: true in both MA_runner and output_manager:
       - In run_multi_agent_once(): after artifact discovery, if one_file_only:
         - Filter artifacts by preferred order: [".md", ".docx", ".pdf"] and pick the first matching file; ignore the rest.
       - Alternatively/in addition, in output_manager.save_generated_reports():
         - Before saving, if one_file_only: keep only the first item per run for each kind="ma".
  3) Deduplication safeguard:
     - In output_manager, skip saving duplicates of the same source “p” or classic double-writes (same stem) in the same batch.
- Outcome: MA rows 9–11 will emit exactly one .md file per model/run.

C) GPTR prompt file missing (Run 2)
- Observed: “Prompt file not found: C:\dev\silky\api_cost_multiplier\temp_process_markdown_noeval\tmp...txt”
- Fix:
  - In functions/gptr_runner.py (and/or functions/gptr_subprocess.py):
    - Pre-create the prompt file in a stable temp directory (api_cost_multiplier/temp_process_markdown_noeval).
    - After write, assert existence with os.path.exists before launching the subprocess.
    - If missing, auto-regenerate and retry once.
    - Ensure absolute paths are passed through to the child process (avoid CWD-dependent relative paths).
- Optional: Log the absolute prompt file path in acm_session.log before launch for easy forensics.

D) Token cap mapping and enforcement (Run 4 - gpt‑4o)
- Observed: OpenAI 400: max_tokens too large; some API variants require max_completion_tokens instead.
- Fixes:
  - For FPF (per docs/generate_errors_report.md “FPF/OpenAI BadRequestError: Unsupported parameter 'max_tokens'”):
    - Map to provider-aware parameter:
      - openai: max_completion_tokens
      - others: max_tokens (or provider-specific equivalent)
    - Add try/except fallback that retries with the alternate param if server rejects.
  - For GPTR:
    - Enforce per-model token caps in the request builder:
      - If requested > model_cap: cap to model_cap (e.g., gpt-4o → 16384).
    - Also align parameter name (max_completion_tokens for newer OpenAI endpoints).

E) FPF grounding/reasoning failure (Run 1) — analysis and corrective actions
- Log evidence (17:06:58): “missing grounding (web_search/citations) and reasoning … enforcement is strict”
- Context:
  - FPF config (FilePromptForge/fpf_config.yaml) shows a Google provider URL override.
  - Many runs same day validated “web_search used and reasoning present,” so feature is configured.
  - This failing run’s response lacked required signals; strict validator blocked output.
- Corrective actions (two tracks):
  1) Improve request to increase likelihood of passing validation:
     - For Google (gemini-2.5-flash-lite/flash), instruct the provider more forcefully to include:
       - Explicit citations/links and a short rationales/thinking section.
     - Add a provider/model specific prompt preamble for FPF google path: “You must include at least N citations and a short reasoning section. Your reply will be validated for web_search/citations and a rationale section.”
  2) Add a controlled retry-on-validation-failure:
     - On validation failure, retry once with:
       - Lower temperature,
       - Stronger instruction block,
       - If available, enable external web search fallback (e.g., Tavily) when provider-side web_search is absent.
     - If still missing, degrade enforcement from strict→warn if the policy allows (write a .md with banner header: “Ungrounded — requires manual review”).
- Notes:
  - FilePromptForge validator currently logs “parsed_json_found=False”. That is informational here.
  - If policy must remain strict, keep strict but add the targeted single retry with stronger instruction to reduce spurious fails.

F) Encoding/logging polish
- The chart shows mojibake for “—” (em‑dash) likely due to encoding/bom mismatches in downstream tooling.
- Save report/chart files as UTF‑8 without BOM and ensure consumers open with UTF‑8.
- Keep Python subprocess environment with PYTHONIOENCODING=utf-8 (already set for MA).

Implementation Steps by File (proposed)

1) gpt_researcher/skills/researcher.py (local copy)
- Add normalization block for sub_queries in _get_context_by_web_search.
- Audit joins/concatenations to handle str vs list.
- Testing: add a unit-style repro for a str return path.

2) functions/MA_runner.py
- Change default publish_formats.docx = False.
- Read config.one_file_only and pass into artifact selection logic.
- After artifact enumeration, if one_file_only: pick best single file by ext priority.

3) functions/output_manager.py
- Accept a one_file_only flag (passed in from processor/runner).
- If true, only save the first artifact per kind (“ma”, “gptr”, “dr”) for each input item.
- Add dedup guard: do not save the same source twice within a batch.

4) functions/gptr_runner.py (and/or functions/gptr_subprocess.py)
- Prompt file: write → fsync → existence assert before launch.
- If missing, regenerate once and log path.
- Ensure absolute paths passed to child process.

5) FilePromptForge (OpenAI paths)
- Map max_tokens → max_completion_tokens where required by OpenAI / responses endpoint.
- If provider rejects, retry with alternative parameter automatically.
- Enforce per-model cap (e.g., gpt‑4o: 16384) before making the request.

6) FilePromptForge (google flow)
- Inject stronger instruction preamble requiring citations and reasoning.
- On validator failure: one retry with lower temp and strict requirement phrasing.
- Optional: if project policy allows, configurable enforcement: strict | warn.

Configuration Notes
- api_cost_multiplier/config.yaml already contains:
  - one_file_only: true
- We will honor this in MA and output save flow.
- Optional future keys:
  - acm.ma.publish_formats: { markdown: true, docx: false, pdf: false }
  - fpf.validation: { require_grounding: true, require_reasoning: true, enforcement: strict|warn, retry_on_validation_failure: 1 }

Validation Plan
- Re-run a representative set:
  - One failing FPF (gemini‑2.5‑flash‑lite) to confirm retry path or stricter instruction avoids reject.
  - GPTR gpt‑4o with previous token settings to confirm 400 no longer occurs and caps are applied.
  - DR runs to verify the 'list'/'split' issue is eliminated.
  - MA runs to ensure only one .md file is produced per model/run.

Deliverables
- Code patches per file above.
- Updated docs:
  - docs/ma_response_normalization_plan.md (mark implemented).
  - docs/generate_errors_report.md (close the normalization action items).
  - New notes under docs/fpf_run_files_investigation.md regarding grounding enforcement/ retry behavior.
- Updated timeline chart will show:
  - Fewer MA artifacts (single per run).
  - Fewer GPTR failures (token cap + prompt file guard).
  - Reduced FPF false negatives due to targeted retry/instruction.

Appendix — Why FPF Run 1 failed even though grounding is on
- The validator checks the actual provider response, not just config flags.
- At 17:06:58 the response lacked the validation signals (“web_search/citations” and “reasoning” markers). With enforcement=strict, the run is marked failed and no report is written.
- Earlier the same day, the same models passed with “Run validated: web_search used and reasoning present.” Therefore the configuration is correct, but provider output is not deterministic; a targeted retry with stronger instruction is recommended.

## Progress Log (continued)
- 2025-11-04 20:53 PT — Verification after "run generate" and static analysis:
  - Pylance/static analysis:
    - generate.py: fixed except indentation, removed unused imports, removed dead local save function, aliased side‑effect import to satisfy analyzer.
    - Converted imports to package‑relative across functions (processor, gptr_runner, output_manager). No remaining runtime imports of process_markdown.* (only in comments/docs).
  - FPF:
    - Strict validation passed after enhanced‑Google preamble plus one controlled retry (wrapper only). logs/fpf_run.log shows: "Run validated: web_search used and reasoning present. Output written … ok=true".
    - No vendor edits to FilePromptForge internals; behavior implemented in functions/fpf_runner.py.
  - MA:
    - one_file_only enforced; DOCX disabled for MA. Exactly one .md artifact per MA run. Duplicate‑source dedup in output_manager prevents double saves across kinds.
    - Aggregate "saved N report(s)" lines may include other kinds (e.g., GPTR), as intended.
  - GPTR:
    - Standard runs produced outputs for some models; deep runs intermittently failed due to scraping/network issues (e.g., Tavily 4xx, "Scraper not found"). Logs indicate non‑deterministic HTTP/scraper failures rather than token parameter mapping. Token param mapping in patches/sitecustomize.py remains unchanged and was not implicated by these failures.
  - Artifacts/logs of interest:
    - logs/acm_session.log, logs/fpf_run.log, logs/acm_subprocess_*.log

### Outstanding cleanups (short‑term)
- [ ] Prune unused typing imports in functions/output_manager.py (e.g., Tuple, Optional) if unused after refactor.
- [ ] Prune unused imports in functions/fpf_runner.py (e.g., shutil, Path, fpf_events) if not referenced.

### Next actions
- [ ] Implement GPTR prompt‑file existence guard and single auto‑retry in functions/gptr_runner.py / functions/gptr_subprocess.py (pre‑create, fsync, assert exists; regenerate on miss).
- [ ] Implement OpenAI token cap enforcement and parameter‑name fallback (max_tokens → max_completion_tokens) in wrappers/patches used by FPF and GPTR (with per‑model caps, e.g., gpt‑4o=16384).
- [ ] Re‑run generate and append the verification results to this log, including any changes in GPTR deep run stability and token‑cap behavior.

- 2025-11-04 21:36 PT — Generate run results summary:
  - FPF:
    - Batch path executed for google:gemini-2.5-flash-lite and validated successfully (“web_search used and reasoning present”). Output saved to outputs directory; auto-eval invoked but evaluate.py requires at least 2 target files and exited with a notice (not an error).
  - GPTR:
    - Prompt-file guard + auto-retry worked as designed: observed “OK (retry)” for openai:gpt-4.1-mini after initial subprocess failure, indicating the missing-prompt race was mitigated by re-creating + fsync’ing and re-launching once.
    - Additional successes: openai:gpt-4.1-nano (std), openai:gpt-5-mini (std and deep). Other models intermittently failed due to scraping/network issues (“Scraper not found”, Tavily 400s). No OpenAI max_tokens parameter errors observed; sitecustomize token-param mapping remains effective.
  - MA:
    - Runs completed with numerous Tavily 4xx and “Scraper not found” messages; still produced markdown reports. Saved counts per file reflect aggregate across kinds (MA + GPTR + FPF) in runs-only mode.
  - Notes/observations:
    - The runs-only orchestrator (runner.py) uses its own save_generated_reports that preserves original extensions and does not enforce one_file_only; this explains multiple saved artifacts per file in the runs-only path despite output_manager enforcing one_file_only. Consider aligning runner’s saver with output_manager when policy one_file_only is true.
    - Auto-eval should be gated to run only when >=2 candidate files are present to avoid the “need at least 2” notice.
