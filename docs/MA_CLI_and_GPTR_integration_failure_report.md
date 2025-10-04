# MA CLI + GPT-Researcher Integration: Failure Analysis and Remediation Report

Author: ACM Orchestration Layer (api_cost_multiplier)
Date: 2025-10-03
Scope: Multi-Agent CLI (MA_CLI) + GPT-Researcher integration as executed by ACM runner/generate.py on Windows 11 (Python 3.13)

## Executive Summary

- Symptom: With config.yaml runs targeting multiple models, early MA runs (e.g., gemini-2.5-flash, gemini-2.5-flash-lite) failed in the planning stage with:


  - AttributeError: 'str' object has no attribute 'get' at gpt-researcher/multi_agents/agents/editor.py:47
- Root cause: EditorAgent.plan_research assumes the LLM plan response is a dict, but some providers/models return a string or JSON-like string. A monkeypatch in `patches/sitecustomize.py` attempts to normalize this centrally, but it is not guaranteed to affect the bound function used by EditorAgent due to import binding semantics (“from ... import call_model” snapshots a reference).
- Status: A direct, surgical fix was implemented in EditorAgent to robustly normalize the plan to a dict even if the upstream patch is bypassed. This ensures consistent behavior across models/providers and subprocess boundaries.
- Additional observations:
  - Heavy web-scraping and live news sources introduce latency and intermittent “content too short”/blocked endpoints.
  - MA_CLI attempted to write a default `task.json` under “C:\Program Files\Python313\config” (failed), but ACM also supplies a per-run task_config.json in a temp directory; this warning is non-fatal but signals environment assumptions in MA_CLI.
  - The runner’s final save step will only deposit outputs to `test/mdoutputs` when a run completes successfully; failing planning runs do not create final outputs even though temp artifacts exist.

## Contents

1) Environment and Run Configuration
2) Observed Behavior and Timeline
3) Code Path Overview (ACM → Runner → MA Runner → MA_CLI → GPT-Researcher)
4) Primary Failure Mechanism: Plan Normalization Gap
5) Why Upstream Monkeypatch Was Insufficient in This Context
6) Remediation Implemented (EditorAgent Hardened)
7) Inventory of Prior Fix Attempts in Codebase
8) Ten Plausible Root Causes for Flakiness/Delays
9) Additional Contributing Factors on Windows
10) Recommendations (Immediate + Near-term)
11) Validation Plan

---

## 1) Environment and Run Configuration

- Entrypoint: `api_cost_multiplier/generate.py` delegates to centralized `runner.py`.
- Config: `api_cost_multiplier/config.yaml` (as of run)
  - input_folder: C:/dev/silky/api_cost_multiplier/test/mdinputs/commerce
  - output_folder: C:/dev/silky/api_cost_multiplier/test/mdoutputs
  - instructions_file: C:/dev/silky/api_cost_multiplier/test/instructions.txt
  - one_file_only: true
  - iterations_default: 1
  - max_sections: 1
  - runs (7): gemini-2.5-flash, gemini-2.5-flash-lite, gpt-4.1-nano, gpt-4o, gpt-4o-mini, gpt-5-nano, o4-mini

- Heartbeat: `pm_utils.start_heartbeat("process_markdown_runner", interval=3.0)` visible in logs.

---

## 2) Observed Behavior and Timeline

- Run #0 (gemini-2.5-flash) and #1 (gemini-2.5-flash-lite):
  - MA research and scraping proceeded.
  - During Editor planning phase: `AttributeError: 'str' object has no attribute 'get'` in `EditorAgent.plan_research`.
  - No final output saved to `test/mdoutputs` for these runs (as expected).
- Run #2 (gpt-4.1-nano):
  - Research, writing, and publishing logs observed; `.md` produced in temp ma_run directory.
  - Final output copy to `test/mdoutputs` was not yet observed at the time of snapshot, likely pending run completion.

- Additional log noise:
  - “Content too short or empty” for certain paywalled or dynamic endpoints (NYTimes, Politico, etc.).
  - MA_CLI warns: cannot write default task.json to `C:\Program Files\Python313\config` (non-fatal).

---

## 3) Code Path Overview (ACM → Runner → MA Runner → MA_CLI → GPT-Researcher)

- `generate.py` calls `runner.run(cfg)`.
- `runner.py`:
  - Loads config; starts heartbeat.
  - Resolves `runs` array; executes `process_file_run(...)` per run.
- `process_file_run(...)` (type "ma"):
  - Computes query prompt (instructions + markdown).
  - Calls `MA_runner.run_multi_agent_runs(...)` with model.
- `MA_runner.py`:
  - Spawns `MA_CLI/Multi_Agent_CLI.py` in a subprocess.
  - Injects PYTHONPATH entries including `patches/` to auto-import `sitecustomize.py` (for streaming disable + normalization shims).
  - Captures STDOUT/ERR to console prefixed per run.

- `MA_CLI/Multi_Agent_CLI.py` (in GPT-Researcher):
  - Orchestrates multi-agent pipeline.
  - EditorAgent’s `plan_research` calls `utils.llms.call_model(...)` to get plan JSON.

---

## 4) Primary Failure Mechanism: Plan Normalization Gap

- Offending site: `gpt-researcher/multi_agents/agents/editor.py`, function `plan_research`:

  ```
  plan = await call_model(prompt=..., model=task.get("model"), response_format="json")

  return {
      "title": plan.get("title"),
      "date": plan.get("date"),
      "sections": plan.get("sections"),
  }
  ```

- The code assumes `plan` supports `.get(...)` (i.e., dict). However, for some models/providers, the underlying call returns:
  - a plain string, or
  - a JSON string, or
  - a list (less common but possible with “json” coerced answers).

- Result: AttributeError when `.get` is accessed on a string.

---

## 5) Why Upstream Monkeypatch Was Insufficient in This Context

- `api_cost_multiplier/patches/sitecustomize.py` includes:

  - Non-stream enforcement for OpenAI clients.
  - GPT-Researcher patches:
    - `GenericLLMProvider.stream_response` shim to simulate streaming by chunking text from a single non-stream call.
    - Aliased module path coverage to handle multiple import patterns (`gpt_researcher.*` vs `gpt-researcher.gpt_researcher.*`).
    - Replacement of `utils.llm.create_chat_completion` to force non-streaming.
    - Critically, `_GR_llms.call_model` wrapper to always return JSON-like dicts (“planner receives a dict even if model returns plain text”), which was the explicit target of the current failure class.
  - Conclusion: There was a deliberate attempt to fix the “planner expects JSON dict” problem via global patching.

- Critical nuance: EditorAgent imports the function by name:
  - `from .utils.llms import call_model`
  - After this “from-import”, the symbol `call_model` is a bound reference in the local module namespace.

- If `sitecustomize` patches the `call_model` attribute on the `llms` module after EditorAgent has bound the name, the local `call_model` reference in EditorAgent does not change. This is a classic “import binding” pitfall.

- Additionally, all of this occurs inside a subprocess (MA_CLI) whose import timings can differ subtly by provider; ensuring deterministic patch application ordering across multiple modules can be brittle.

Conclusion: Relying solely on upstream monkeypatches is fragile here. The Editor must defensively normalize the result prior to using it.

---

## 6) Remediation Implemented (EditorAgent Hardened)

- File: `api_cost_multiplier/gpt-researcher/multi_agents/agents/editor.py`
- Change: After receiving `plan`, normalize to a dict:
  - If `dict`: use directly.
  - If `str`: try `json.loads`, else extract first `{...}` or `[...]` and parse; fallback to minimal dict (title/date/sections).
  - Enforce `max_sections`.
  - Guarantee `sections` is a non-empty list of strings.

- Rationale:
  - Guarantees EditorAgent works regardless of call site binding and upstream patches.
  - Addresses provider variability and string-based JSON returns.
  - Prevents blocking on this class of error for all runs.

---

## 7) Inventory of Prior Fix Attempts in Codebase

Evidence of prior fixes and engineering intent:

- `patches/sitecustomize.py`:
  - Hard-disables provider-side streaming; enforces non-stream on OpenAI SDK v1.x and v0.x, including `responses.stream` degrade to non-stream.
  - GPT-Researcher patches:
    - `GenericLLMProvider.stream_response` shim to simulate streaming by chunking text from a single non-stream call.
    - Aliased module path coverage to handle multiple import patterns (`gpt_researcher.*` vs `gpt-researcher.gpt_researcher.*`).
    - Replacement of `utils.llm.create_chat_completion` to force non-streaming.
    - Critically, `_GR_llms.call_model` wrapper to always return JSON-like dicts (“planner receives a dict even if model returns plain text”), which was the explicit target of the current failure class.
  - Conclusion: There was a deliberate attempt to fix the “planner expects JSON dict” problem via global patching.

- `functions/gpt_researcher_client.py`:
  - Disables streaming (`GPTR_DISABLE_STREAMING=true`) and adds retries on write_report when streaming-related permission errors occur.
  - Async client cleanup to avoid hanging event loops.

- `functions/MA_runner.py`:
  - Ensures PYTHONPATH includes `patches/`, `gpt-researcher`, and `multi_agents`.
  - Forces UTF-8 in subprocess to avoid encoding issues.
  - Uses explicit `--task-config` per run (file-based strict MA) to avoid global state.
  - Writes normalized JSON outputs even when MA_CLI MD exists (post-normalization path).

- Documentation:
  - `docs/ma_response_normalization_plan.md` suggests prior identification of response normalization issues for MA agent outputs.
  - `docs/gptr_model_fix.md`, `docs/gptr_api_token_limit_fix.md`, `docs/STREAMING-README.md` indicate repeated mitigation efforts for provider behavior, model configs, and streaming.

---

## 8) Ten Plausible Root Causes for Flakiness/Delays

1) Import Binding vs Monkeypatch Timing
   - EditorAgent’s `from ... import call_model` captures a reference before sitecustomize patches it, leaving the Editor using the unpatched function.

2) Provider Return-Type Variability
   - Some LLM providers/models return strings or JSON-as-string even when asked for “json” format, especially with minimal prompts (max_sections=1).

3) Subprocess Environment Divergence
   - MA_CLI runs in a separate process; environment variables & sys.path ordering may differ across runs.

4) Windows Path Semantics
   - MA_CLI attempted to write default `task.json` into Program Files, indicating reliance on sys.prefix or platform-specific paths; failure is benign but signals assumptions that could impact other file writes/reads.

5) Network Scraping Instability
   - Live news endpoints are rate-limited/paywalled; scraping returns “content too short”, requiring retries or more robust parsers → delays and occasional empty contexts.

6) Long-Running Await with No Timeout
   - Some awaits (network, scraping, LLM) may lack explicit timeouts, risking stalls that look like hangs.

7) Heavy Concurrency + Sequential Orchestration
   - Runs are executed sequentially; within runs, sub-agents execute multiple scrapes; serializing across 7 runs on news domains will appear “slow” under load.

8) Output Save Semantics
   - `runner.save_generated_reports` expects normalized outputs from MA (now JSON); failures during MA mean ACM does not copy to `test/mdoutputs`, causing perceived “no output” even when temp MD exists.

9) Streaming-SSE Removal Side Effects
   - Central SSE disabling can trigger unexpected IO paths in some SDKs; although shims degrade streams, vendor updates may still hit untested code paths.

10) UTF-8/Encoding and Windows Console Peculiarities
   - Multi-threaded stdout readers print prefixed lines char-by-char; encoding/ANSI sequences + carriage returns can mangle lines and mislead operational perception.

---

## 9) Additional Contributing Factors on Windows

- File permissions under `C:\Program Files\...` and locked-down paths caused MA_CLI warnings.
- CRLF vs LF and terminal encoding can alter readability and interact with real-time UI tools.
- Antivirus/network filters may slow scraping and HTTP connections.

---

## 10) Recommendations (Immediate + Near-term)

Immediate (already done or proposed):
- [DONE] Add robust normalization inside `EditorAgent.plan_research` (defensive coercion to dict).
- Add explicit timeouts to long operations (LLM and scraping) and handle `asyncio.TimeoutError` with retries or fallback.
- Log the exact plan payload type (dict/str/len) at DEBUG level in EditorAgent to trace provider anomalies.
- In MA_CLI, avoid defaulting to `C:\Program Files\Python313\config` for writable defaults; prefer `%TEMP%` or the run’s temp directory when no user config is provided.

Near-term:
- Replace “from ... import call_model” with “import ... as llms” then call `llms.call_model` so monkeypatches rebind successfully.
- Promote a small schema validator for plan objects (title/date/sections) across both upstream patches and EditorAgent to catch regressions.
- Consider caching/static content or API-based news providers to reduce failures from scraping paywalled pages.
- In `runner.py`, include an optional “save temp artifacts on failure” copying minimal temp outputs to `test/mdoutputs` with a suffix `.failed.json` for visibility.

---

## 11) Validation Plan

1) Re-run `python -u api_cost_multiplier\generate.py` with the hardened EditorAgent:
   - Expect runs that previously failed in the planner to proceed and finish.
   - Verify final outputs appear under `test/mdoutputs` as `.json` for MA runs, with unique UID in filenames.

2) Tail `api_cost_multiplier/logs/fpf_run.log` and console:
   - Confirm no planner AttributeError.
   - Note durations per run; measure impact of scraping slow endpoints.

3) If any run still fails:
   - Collect the raw “plan” payload (logged at DEBUG).
   - Inspect for non-JSON, malformed JSON, or empty answers; tune normalization accordingly.

---

## Appendix A: Concrete Evidence from Logs

- Error stack (gemini-2.5-flash, gemini-2.5-flash-lite):
  ```
  File "...editor.py", line 47, in plan_research
    "title": plan.get("title"),
             ^^^^^^^^
  AttributeError: 'str' object has no attribute 'get'
  ```

- Successful run (gpt-4.1-nano) produced:
  ```
  Multi-agent report (Markdown) written to ...\temp_process_markdown_noeval\ma_run_...\ma_report_1_....md
  ```

- Windows warning:
  ```
  Warning: Could not create config directory at 'C:\Program Files\Python313\config'
  Error: Could not write default task.json ...
  ```

---

## Appendix B: Files of Interest

- `api_cost_multiplier/patches/sitecustomize.py` (streaming/normalization patches)
- `api_cost_multiplier/functions/MA_runner.py` (subprocess env, PYTHONPATH injection)
- `api_cost_multiplier/gpt-researcher/multi_agents/agents/editor.py` (planning)
- `api_cost_multiplier/functions/gpt_researcher_client.py` (programmatic runner)
- `api_cost_multiplier/docs/ma_response_normalization_plan.md` (design notes)
- Other docs indicating recurring issues and mitigations:
  - `docs/gptr_model_fix.md`
  - `docs/gptr_api_token_limit_fix.md`
  - `docs/STREAMING-README.md`
  - `docs/REPEATED PROBLEMS ...` series (FPF cut-off, temperature, etc.)

---

## Closing

The integration point most directly responsible for the observed planner crash is a simple type assumption in EditorAgent, now fixed locally to be robust. The upstream patch aimed to address the same class of issues but can be bypassed by import binding semantics and subprocess timing. With the defensive normalization in place, ACM can “just run it,” and downstream variability in provider responses will not derail the pipeline.

---

## Appendix C: External Findings (5 targeted web sources) — added Oct 03, 2025

The following external sources were consulted to validate and contextualize the observed failure mode (“AttributeError: 'str' object has no attribute 'get'”) and integration patterns between LLM responses and pipeline code. Each source is summarized with relevance to this project.

1) GitHub: gpt-researcher issue #859 — “Error on query: TypeError: expected string or bytes-like object, got …”
   - URL: https://github.com/assafelovic/gpt-researcher/issues/859
   - Key points:
     - Multiple users reported JSON/normalization-related errors during agent selection and LLM response handling.
     - Maintainers suggested ensuring multi_agents requirements are installed and recommended Docker as a “path of least resistance.”
     - Mentions `json_repair` failures and LLM response handling in gpt_researcher/utils/llm.py call paths.
   - Relevance:
     - Confirms recurrent community issues around non-dict responses and JSON coercion within GPT‑Researcher modules.
     - Supports our approach: harden call sites (EditorAgent) rather than rely only on upstream patches.

2) General explainer: “Handling the AttributeError: 'str' object has no attribute 'get' in Python”
   - URL: https://www.youtube.com/watch?v=RSIZa3OdFQU
   - Key points:
     - Emphasizes that `.get` is a dict method; error indicates the value is a string (or otherwise not a dict).
     - Recommends explicit JSON parsing via `json.loads` when data originates as text.
   - Relevance:
     - Aligns with our defensive normalization: detect string payloads and parse JSON (with fallbacks).

3) Q&A context on AttributeErrors (Quora)
   - URL: https://www.quora.com/What-can-I-do-if-I-have-attribute-error-str-object-has-no-attribute-re
   - Key points:
     - Root cause analysis patterns: object not being what you think (type mismatch, in-place ops returning `None`, etc.).
     - Suggests tracing provenance and verifying assumptions at each boundary.
   - Relevance:
     - Reinforces need for type checks and logging when integrating layers (MA_CLI → EditorAgent → LLM providers).

4) Microsoft Learn Q&A: “AttributeError: 'str' object has no attribute 'get'”
   - URL: https://learn.microsoft.com/en-us/answers/questions/1327627/result-failure-exception-attributeerror-str-object
   - Key points:
     - Example where double-serialized JSON produces a string body; solution is to detect and parse, then access via `.get`.
   - Relevance:
     - Mirrors our symptom: dict-expected code receiving string JSON; fix is to `json.loads` or robustly coerce.

5) bobbyhadz: “AttributeError: 'str' object has no attribute 'get' (Python)”
   - URL: https://bobbyhadz.com/blog/python-attributeerror-str-object-has-no-attribute-get
   - Key points:
     - Practical guidance on .get usage, `hasattr`, and ensuring the right type before dict operations.
   - Relevance:
     - Endorses the normalization and guard strategy we introduced in EditorAgent.

### Implications for ACM

- External consensus: this class of error is universally symptomatic of type mismatch (string vs dict). Frameworks and SDKs often return strings despite "json" directives. Robust code must handle both.
- The community evidence in GPT‑Researcher’s tracker confirms JSON repair/format issues can surface despite best efforts, especially across provider/model combinations.

### Follow-up based on research

- Add optional DEBUG logging in EditorAgent showing:
  - type(plan), length when string, and the first 200 chars (sanitized) to trace provider-specific anomalies.
- Consider adding `json_repair` as a secondary parser if plain `json.loads` fails (behind a safe try/except).
- Track provider/model pairs that most often return non-dict plans to tune prompts and response_format hints.

---

## Appendix D: Additional External Findings (Searches 2–5) — added Oct 03, 2025

This appendix captures five more sources gathered to further contextualize the “AttributeError: 'str' object has no attribute 'get'” class of failures in multi-agent LLM pipelines and surrounding ecosystems.

1) Auto‑GPT Issue (JSON handling and dict vs string failures)
- Source: AttributeError: 'str' object has no attribute 'get' · Issue #1021 — Auto‑GPT
- URL: https://github.com/Torantulino/Auto-GPT/issues/1021
- Key points:
  - Reports of agent outputs where JSON fails to parse; attempts to “fix AI output by finding outermost brackets.”
  - Repeated “failed to parse AI output” warnings and downstream errors like “string indices must be integers.”
- Relevance to ACM:
  - Confirms this error signature is a common emergent behavior when LLM output is not strictly JSON, even when prompts request JSON. Hardening at the call site is standard practice in agent ecosystems.

2) Microsoft Learn Q&A (double‑serialized JSON in HTTP payloads)
- Source: Failure Exception: AttributeError: 'str' object has no attribute 'get'
- URL: https://learn.microsoft.com/en-us/answers/questions/1327627/result-failure-exception-attributeerror-str-object
- Key points:
  - Example of double‑serialized JSON: server receives a string body; fix is to detect string and json.loads() before accessing dict keys with .get.
- Relevance:
  - Mirrors our planner failure: dict‑expecting code getting raw string/JSON-as-string. Validates our fix to normalize plan payloads defensively.

3) Tavily Docs: GPT‑Researcher integration guidance and environment cautions
- Source: GPT Researcher — Tavily Docs
- URL: https://docs.tavily.com/examples/open-sources/gpt-researcher
- Key points:
  - Describes GPT‑Researcher’s parallelized agent strategy; includes environment setup guidance (note on Chrome/ChromeDriver compatibility for browsing).
- Relevance:
  - Highlights that environment and dependency consistency (browser automation, drivers) can affect stability/performance of research agents, contributing to perceived slowness or failures in web steps.

4) CrewAI community thread: AttributeError in agent orchestration
- Source: Attribute Error: 'str' object has no attribute 'get' — CrewAI Community
- URL: https://community.crewai.com/t/attribute-error-str-object-has-no-attribute-get/1079
- Key points:
  - Cross‑ecosystem reports of the same error during agent runs; indicates this pattern is not GPT‑Researcher‑specific.
- Relevance:
  - Supports our architectural decision: normalize and validate at integration boundaries (agent↔LLM), not just rely on provider correctness.

5) GPT‑Researcher Troubleshooting
- Source: Troubleshooting — GPT Researcher
- URL: https://docs.gptr.dev/docs/gpt-researcher/gptr/troubleshooting
- Key points:
  - Covers environment dependencies (e.g., pango on macOS/Linux), library installation, and known platform workarounds.
- Relevance:
  - Confirms that platform dependencies and environment setup frequently cause non‑deterministic operational issues. Reinforces our recommendation to ensure subprocess environments (MA_CLI) are deterministic and instrumented.

Overall synthesis for Appendix D
- The additional sources reinforce that:
  - Type mismatch between expected dicts and actual strings (or JSON-as-string) is a pervasive source of runtime AttributeErrors in agent frameworks.
  - Fixes typically involve local normalization at the consumption site (json.loads + schema guard), exactly what we implemented in EditorAgent.
  - Ecosystem‑level issues (dependency versions, browser/driver alignment, platform packages, and web access variability) exacerbate latency and perceived “hangs,” requiring timeouts and robust error handling at orchestration points.

---

## Appendix E: Internal Codebase Findings (10 files reviewed) — added Oct 03, 2025

To further confirm (or refute) the conclusions above, ten files from this repository were examined. Key evidence and implications are summarized below.

1) docs/ma_response_normalization_plan.md
- Evidence:
  - Proposes normalizing MA planner output inside ACM’s MA_runner.py via a helper `_normalize_plan_output(...)`, coercing dict/JSON-string/narrative to a consistent dict with title/date/sections.
  - Intention is to avoid direct edits in the external gpt‑researcher library.
- Implication:
  - Confirms prior awareness of the planner type-mismatch risk and documents an ACM-side mitigation path. Our current fix in EditorAgent (library-side) achieves equivalent robustness from the opposite direction. Both approaches are compatible; combining them yields belt-and-suspenders reliability.

2) docs/gptr_model_fix.md
- Evidence:
  - Historical corruption of SMART_LLM/STRATEGIC_LLM (e.g., google:google:gemini-2.5-flash) due to provider/model concatenation loops in the GUI config path; fixed by enforcing canonical “provider:model”.
- Implication:
  - Misconfigurations at config load time can cascade into runtime selection anomalies. Although orthogonal to the planner crash, this explains intermittent “works for model X but not Y” symptoms and justifies strict provider:model hygiene across the stack.

3) docs/gptr_api_token_limit_fix.md
- Evidence:
  - Token overflow (e.g., requested 378,510 tokens vs 300,000 max) occurred during embeddings/context compression. Mitigation: set EMBEDDING_KWARGS.chunk_size to bound batch size at langchain-openai level.
- Implication:
  - Supports that perceived “hangs” or long latencies can be resource-bound or error/retry-bound. Explicit chunking lowers risk of runaway request sizes and reduces stalls in embedding phases.

4) docs/STREAMING-README.md
- Evidence:
  - Detailed rationale and changes for non-streaming enforcement, GPT‑5 temperature gating, and model capability canonicalization. Emphasizes subprocess precedence to ensure local code (and patches) are used.
- Implication:
  - Confirms systemic changes aimed at removing provider-side SSE and temperature rejections. This aligns with our diagnosis that streaming/param mismatches can cause subtle stalls. It also corroborates that process ordering/patching is a known concern.

5) functions/gptr_subprocess.py
- Evidence:
  - Preloads repo roots on sys.path and imports api_cost_multiplier.patches.sitecustomize inside the subprocess; calls run_gpt_researcher_programmatic and emits a single JSON line with path/model.
- Implication:
  - Good practice: guarantees patches load in programmatic GPT‑Researcher runs. However, it doesn’t influence MA_CLI subprocess behavior; hence our need to harden MA planner consumption code remains.

6) functions/config_parser.py
- Evidence:
  - Thin wrapper around yaml.safe_load with no merging. Runner persists resolved absolute paths back into the loaded config (see runner.py).
- Implication:
  - Confirms runner behavior relies purely on config.yaml without auto-injecting defaults, matching our earlier explanation that output_folder remains empty until a run actually completes and save logic fires.

7) functions/file_manager.py
- Evidence:
  - Utilities for finding markdowns and computing mirrored output paths; output_exists short-circuits processing if final artifact path already exists.
- Implication:
  - Explains why mdoutputs stays empty until save occurs. As soon as runner detects an existing final output path, it will skip that file—useful to avoid duplicate work, but can hide partial progress if temp artifacts exist.

8) functions/processor.py (older “process_markdown” path)
- Evidence:
  - Orchestrates MA first, then GPT‑Researcher reports, and saves outputs via output_manager.save_generated_reports; cleans temp at end.
- Implication:
  - Mirrors the new runner pattern (centralized in runner.py). Confirms that MA first is the intended flow and that temp cleanup can erase intermediate artifacts if not saved—another reason mdoutputs may seem empty if failures occur before save.

9) functions/output_manager.py
- Evidence:
  - Saves MA/GPTR/DR outputs as .md with unique randomized suffixes; uses SMART_LLM/FAST_LLM/STRATEGIC_LLM as fallback labels for model.
- Implication:
  - Variant from new runner.save_generated_reports which currently writes MA as .json (normalized). Confirms earlier dual behavior: legacy output_manager saves .md; centralized runner saves .json (unique UID). Discrepancy is benign but explains differing expectations on output format/location across code paths.

10) generate_gptr_only.py
- Evidence:
  - A GPTR-only pipeline that bypasses MA; uses run_gptr_local to prefer local sources; saves gptr/dr .md reports.
- Implication:
  - Confirms that gptr-only path can be used for quick validation separate from MA, useful in isolation testing if MA planner trust is in question.

Synthesis from internal review
- The repository already contains:
  - A formal plan to normalize MA planner outputs in ACM (docs/ma_response_normalization_plan.md).
  - Streaming/temperature gating docs and code hooks (docs/STREAMING-README.md).
  - Provider:model normalization fixes (docs/gptr_model_fix.md).
  - Token limit/embedding batching mitigations (docs/gptr_api_token_limit_fix.md).
- The observed failure (EditorAgent expecting dict, receiving string) is a known class of issue and is addressed by our local EditorAgent hardening. The ACM-side normalization plan could also be implemented in MA_runner to add another layer of safety.
- Legacy vs centralized saving behavior explains variations in output artifact formats and why final outputs may not appear when runs fail early. This aligns with what was seen during the gemini runs.

Actionable deltas informed by internal evidence
- Optionally implement the ACM-side `_normalize_plan_output` path in MA_runner (as per docs) to supplement the EditorAgent fix, ensuring double coverage.
- Harmonize output formats between output_manager and runner (decide on .json vs .md for MA and enforce consistently).
- Add explicit timeouts and error typing around embeddings and scraping to avoid long “alive heartbeat” with no forward progress.
- Keep provider:model hygiene strict to avoid misroutes of model selection downstream.

---

## 12) Preventative Implementation Plan (End-to-End Hardening) — added Oct 03, 2025

Goal: Eliminate the “AttributeError: 'str' object has no attribute 'get'” class of failures and adjacent stalls across all code paths (MA_CLI, GPTR, ACM). This plan layers defenses at every boundary, adds timeouts and schemas, and standardizes outputs.

A) Normalize at every boundary (belt-and-suspenders)
1. Library-side (already done): EditorAgent.plan_research
   - Status: Implemented. Coerces plan to dict, enforces max_sections, guarantees sections list.
   - Owner: Library mirror in repo (gpt-researcher/multi_agents/agents/editor.py)

2. ACM-side: MA_runner post-processing (as per docs/ma_response_normalization_plan.md)
   - Implement `_normalize_plan_output(plan_raw, max_sections, task_config)` in functions/MA_runner.py (if not present).
   - After MA_CLI returns, read produced .md, normalize to dict, write normalized .json alongside (or replace temp .md with .json).
   - On normalization failure, persist original with `.raw.txt` and continue (don’t crash).
   - Benefit: Even if EditorAgent is bypassed by future changes, ACM captures and fixes malformed plans.

3. GPTR programmatic (already resilient)
   - gpt_researcher_client.run_gpt_researcher_programmatic includes streaming disable, retries, cleanup.
   - Add optional logging of first 200 chars of plan (sanitized) for diagnostics behind DEBUG flag.

B) Import-binding and patch ordering remediation
1. Replace “from ... import call_model” patterns
   - In all local library mirrors we control, prefer `import ... as llms` and call `llms.call_model(...)`. This keeps runtime monkeypatches effective.
   - Scope: Affected gpt-researcher modules we vendor here (EditorAgent already hardened, but apply broadly where reasonable).

2. Ensure sitecustomize.py loads in all subprocesses
   - Already ensured for GPTR subprocess (functions/gptr_subprocess.py).
   - Verify MA_runner env injection: PYTHONPATH includes `api_cost_multiplier/patches` and repo `gpt-researcher`, and MA_CLI is launched with that env.
   - Add a one-line debug at MA_CLI start that prints “sitecustomize loaded” (harmless) if we control that code path; otherwise rely on our env.

C) Timeouts, cancellation, and retries
1. MA subprocess timeout
   - Wrap `subprocess.Popen(...).wait()` with an overall timeout per run (e.g., 8–12 minutes configurable).
   - On timeout: kill the process group, capture partial logs, emit `.failed.json` with reason and links to temp artifacts, then continue to next run.

2. GPTR programmatic timeout
   - Wrap `run_gpt_researcher_programmatic(...)` in `asyncio.wait_for` with configurable timeout (e.g., 8–12 minutes), cancel and cleanup clients on expiry.

3. HTTP scraping and embeddings timeouts
   - Introduce per-request timeouts via environment or provider configs (e.g., requests/httpx timeouts).
   - Backoff/retry with jitter for transient network failures; cap retries to avoid indefinite stall.

D) Plan schema validation + diagnostic logging
1. Introduce a tiny schema validator function
   - Validate dict has {title: str, date: str, sections: list[str]} and `len(sections) >= 1`.
   - Coerce where possible; otherwise fallback to minimal dict with “Initial Research Plan” section.

2. Add controlled DEBUG logging
   - Log `type(plan)`, heuristic length, and first 200 characters when plan is text.
   - Toggle via env var (e.g., ACM_DEBUG_PLAN=1) to avoid sensitive logs in production.

E) Output format harmonization and failure artifacts
1. Decide MA output as JSON
   - Standardize MA outputs to `.json` across runner and output_manager (legacy used `.md`).
   - Include a `_meta` block with model, provider, timestamps, and `_raw_output_type`.

2. Save failure artifacts
   - On any MA/GPTR failure pre-save, write a `.failed.json` next to expected output path:
     - Fields: `error`, `stage`, `model`, `provider`, `log_tail`, and pointers to temp files.
   - Users then see something in `test/mdoutputs` instead of an empty directory.

F) Config sanity checks (early errors)
1. Enforce provider:model hygiene (from docs/gptr_model_fix.md)
   - Before run, validate each run entry: rtype in {ma,gptr,dr,fpf}, model present, provider present when required.
   - Normalize “provider:model” -> provider + model parts as needed and stop if ambiguous.

2. Model capability registry (optional)
   - Maintain a small map of models that don’t support `temperature` or streaming; strip those kwargs early.
   - Prevents 400s (“Unsupported value: 'temperature'...”) that waste time.

G) CI and tests
1. Unit tests
   - Given a string plan, JSON string plan, list plan, None, weird narrative → expect normalized dict.
   - Test timeouts: simulate long-running subprocess; confirm kill and `.failed.json` written.

2. Integration tests
   - A smoke run with a fake MA_CLI that returns text plan; confirm both EditorAgent and ACM-side normalizers handle it.
   - Golden-file tests: verify standardized `.json` outputs saved with UID suffixes.

H) Operational controls and fallbacks
1. Feature flags & env toggles
   - ACM_DISABLE_STREAMING, ACM_ENABLE_TIMEOUTS, ACM_OUTPUT_JSON_ONLY, ACM_LOG_DEBUG_PLAN, etc.

2. Automatic fallback mode
   - If N consecutive MA runs fail for the same file, switch to GPTR-only mode (generate_gptr_only) for that file and mark the MA attempt as degraded instead of blocking the pipeline.

I) Token and embeddings controls
1. Enforce EMBEDDING_KWARGS.chunk_size (from docs/gptr_api_token_limit_fix.md).
2. Optional token counting using tiktoken in long contexts; split aggressively to respect provider token windows.
3. Surface token-limit errors clearly and move on (don’t stall the pipeline).

J) Platform/Windows specifics
1. Avoid `C:\Program Files\...` writes in MA_CLI defaults; prefer `%TEMP%` or run-specific dirs.
2. Ensure UTF-8 for all subprocess IO (already set); strip ANSI sequences in logs to keep console readable.

K) Timeline & ownership
- Week 1:
  - Implement MA_runner normalization and `.failed.json` artifacts
  - Add subprocess and GPTR timeouts; harmonize MA output `.json`
- Week 2:
  - Add schema validator + DEBUG plan logging
  - Replace from-imports for patched call sites where feasible
  - Add provider:model sanity checks and capability map
- Week 3:
  - CI unit + integration tests; finalize docs and flags
  - Optional GPTR-only fallback wiring and alerting hooks

Expected outcome
- Planner-related crashes eliminated due to dual normalization (library + ACM).
- Pipeline no longer “looks hung” under failures; timeouts + `.failed.json` make failure modes visible.
- Outputs standardized and always materialized (success `.json` or `.failed.json`), reducing confusion around empty directories.
- Config hygiene and capability gating prevent avoidable provider 400s.

---

## 12a) Simplified Plan (Minimal Viable Hardening)

Focus on five changes that neutralize the failure class with the least moving parts:

1) Dual normalization — single line of defense per layer
- Keep the already-implemented EditorAgent.plan_research normalization.
- Add one ACM-side normalization step in MA_runner:
  - Read MA_CLI output (.md), normalize to a dict (title/date/sections), write `.json`.
  - If normalization fails, write `.failed.json` with error and log tail. Never crash.

2) Universal timeouts + visible failures
- Apply two timeouts only:
  - Per MA run (subprocess) timeout (e.g., 10 minutes).
  - Per GPTR programmatic run timeout (e.g., 10 minutes via asyncio.wait_for).
- On timeout or error, emit `.failed.json` next to where output would go (include model/provider/stage/error/log tail).

3) Output standardization
- Standardize MA outputs to `.json` only (include `_meta` with model/provider and `_raw_output_type`).
- Always produce something (success `.json` or `.failed.json`) so `test/mdoutputs` is never empty.

4) Sanity checks at config load
- Enforce provider:model hygiene before running (split combined strings, validate presence).
- Gate obviously unsupported params (streaming/temperature) for known models upfront.

5) Minimal tests + debug knob
- Add one unit-test for plan normalization (string, JSON string, list, garbage → dict).
- Add one smoke-test that runs MA with a fake text plan.
- Introduce an env flag (ACM_DEBUG_PLAN) to log type/first 200 chars of plan for diagnostics only when needed.

Two-sprint timeline
- Sprint 1 (day 1–3): MA_runner normalization + `.failed.json`; timeouts; `.json` standardization
- Sprint 2 (day 4–5): Config hygiene checks; one unit + one smoke test; debug flag
- Outcome: Crashes removed; failures surfaced clearly; outputs consistent with minimal code churn.

---

## 13) Post-Implementation Validation Results (Oct 03, 2025)

Context
- Re-ran python -u api_cost_multiplier\generate.py after implementing the simplified plan (timeouts, MA JSON normalization, failure artifacts).
- Observation: Early MA runs for gemini-2.5-flash and gemini-2.5-flash-lite still failed, with console logs showing a different class of error:

New failure signature
- Error: TypeError: 'str' object is not a mapping at gpt-researcher/multi_agents/agents/writer.py:142
  - Code: return {**research_layout_content, "headers": headers}
  - Root cause: writer.run expects research_layout_content to be a dict, but received a string. This mirrors the original EditorAgent failure class (type assumption), but occurring later in the pipeline during the writer phase rather than the planner phase.
  - Implication: The previous normalization hardened EditorAgent.plan_research but did not harden the writer path. Provider/model variability is again returning non-dict content (or a JSON string) where a dict is expected.

Timeout and artifacts behavior
- The MA subprocess timeout (10 minutes) did not trigger during these gemini runs; the process progressed (scraping, writing) and then exited with a non-zero code due to the writer TypeError. Because our current MA_runner behavior raises on non-zero exit (without converting that failure into a .failed.json), no MA failure artifact was saved for these specific error paths.
- For a later run (gpt-4.1-nano), the writer path succeeded, the WRITER output included a large dict payload, and MA produced artifacts (docx/md and a temp ma_report_*.md). This demonstrates the variability by provider/model and confirms our timeouts do not mask legitimate progress.

Why the simplified plan did not fully eliminate failures
- Scope gap: We normalized the planner (EditorAgent) but not the writer. The simplified plan assumed planner normalization addressed the recurring type-mismatch risk; however, writer.run also dereferences a mapping shape and can receive text/JSON strings from upstream. This is the same class of problem at a different integration junction.
- Artifact policy gap: We only emitted *.failed.json on timeouts. Non-zero exit codes for MA (due to exceptions like the writer TypeError) currently raise and return without producing an MA failure artifact. This can still lead to “no outputs saved” for those runs even though they did not time out.

Targeted fixes to close the newly observed gap (low risk, localized)
1) WriterAgent hardening (library-side, like EditorAgent)
   - File: gpt-researcher/multi_agents/agents/writer.py
   - Change: Before using research_layout_content as a mapping, normalize it:
     - If dict: use directly
     - If str: try json.loads; else regex-extract {...} or [...]; fallback to {"content": text}
     - Ensure a stable dict to spread into return {**normalized, "headers": headers}
   - Rationale: Mirrors the EditorAgent defensive strategy; prevents TypeError on models/providers that return narrative/JSON strings in the writer stage.

2) MA_runner failure artifacts on non-zero exit
   - File: functions/MA_runner.py
   - Change: When process.returncode != 0, create an output_filename.failed.json with stderr_tail/stdout_tail and the exit code, then return that path instead of raising.
   - Rationale: Matches the “always produce something” policy from the simplified plan. Ensures mdoutputs contains a visible artifact even when exceptions occur (not only timeouts).

Optional enhancement (if “hang” perception persists)
- Per-agent step ceilings (soft timeouts): Add smaller, agent-phase timeouts (e.g., writer step ceiling) inside MA_CLI or via env knobs. Current run showed lots of scraping and two long writer phases; while not true hangs, they read as such. Soft ceilings with retries or degraded content could reduce perceived hanging.

Net effect after these deltas
- The writer TypeError class is eliminated by local normalization (same defense-in-depth as planner).
- MA non-zero exits generate .failed.json artifacts so mdoutputs is never empty for failed runs.
- The combination meets the “never fail silently and avoid type-assumption crashes” objective across both planner and writer phases.

Next step proposal (very small patches):
- Harden writer.run as above.
- Update MA_runner to emit .failed.json on non-zero exit.

These are additive to the already-deployed plan and address the newly observed failure mode.

---

## 14) ACM-Orchestrator-Only Remediation Report: Eliminating “Hang” Perception and Ensuring Reliable File Outputs Without Touching GPT‑R/FPF

Executive Summary
- Problem statement: Users observed “hanging” behavior and missing outputs during MA runs initiated by ACM. Logs show long research/writing phases and occasional non-zero exits in GPT‑Researcher’s pipeline (e.g., a writer TypeError). The root cause is not ACM calling LLMs—it doesn’t. The issue is ACM’s orchestration behavior during tool execution and file collection, which can lead to silent failures (no final artifacts copied) when a subprocess runs long or exits with an error. 
- Guiding constraints: Do not modify GPT‑Researcher or FPF code; do not parse, transform, or “normalize” LLM content; do not perform any LLM API calls. ACM’s responsibility is process lifetime management, robust output discovery, and deterministic copying of whatever files the tools produce (docx/md/etc.), plus creating a minimal failed-artifact file when runs don’t produce outputs.
- Proposed solution, in brief: 
  1) Robust process control (timeouts, clear exit handling) that never blocks indefinitely and always yields a visible artifact. 
  2) Content-agnostic output discovery that finds, labels, and copies the files GPT‑R/FPF wrote—verbatim. 
  3) Consistent artifact policy (.failed.json on non-zero exit/timeout) so mdoutputs is never empty even when a run fails. 
  4) Minimal provider:model hygiene at run configuration time for labeling only, without altering tool behavior.
- Outcome: No perceived “hangs,” improved observability, and guaranteed presence of artifacts (success or failure) without ACM doing any LLM work or changing GPT‑R/FPF internals.

### 1) Architecture And Responsibilities
- ACM (api_cost_multiplier) is an orchestrator. It:
  - Reads config (input file(s), runs, model/provider labels).
  - Launches tools (MA_CLI for multi-agent via GPT‑Researcher, GPT‑Researcher programmatic runs, and FPF).
  - Waits for tool completion with deterministic time bounds.
  - Finds and copies the files those tools generate into mirrored output structure.
  - Emits a minimal failure artifact when runs don’t produce outputs (so users always see a result).
- GPT‑Researcher and FPF (tools) are authoritative for:
  - Deciding how to run agents, browse, draft, and publish content.
  - Actually writing reports (md, docx, pdf, etc.) to their own output directories.
- Principle of separation: ACM does not parse or normalize any LLM output, does not alter GPT‑R/FPF code, and does not change the content or the format produced by tools.

### 2) Observed Failure Modes And User Impact
- Long phases that “look like hangs”: Legitimate long phases in GPT‑R (web scraping, indexing, writing) can last several minutes. Without a global timeout and high‑level status lines, operators see repeated heartbeats and assume a hang.
- Non-zero exit without final artifacts: When the GPT‑R pipeline throws an internal exception, ACM previously surfaced nothing in mdoutputs for that run. Without a failure artifact, the user sees an empty output folder and cannot distinguish a hang from a failure.
- Inconsistent artifact collection: Tool outputs can be named dynamically (include query substrings, timestamps, UUIDs). If ACM’s discovery logic is too brittle, it may miss the files and thus copy nothing, even though GPT‑R/FPF succeeded.

### 3) Constraints And Non-Goals (Per Clarification)
- Do not modify GPT‑Researcher or FPF sources.
- Do not transform outputs from tools (no JSON normalization, no content parsing).
- Do not call LLM APIs directly from ACM.
- Only touch ACM’s orchestration code: process lifetime management, logging, output discovery and copying, error/failure artifacts.

### 4) Root Cause Synthesis Without Touching GPT‑R/FPF
- The user-facing “hang” is a perception gap: activity is happening, but without an outer timebox and visible artifact policy, runs can appear stuck.
- The “missing outputs” is an orchestration gap: ACM must reliably find and copy the tool’s outputs or, failing that, write a .failed.json to make the failure visible.

### 5) ACM-Only Remediation Plan

#### 5.1 Process Lifetime Control
- Introduce a per-run wall-clock timeout for each tool invocation:
  - Multi-agent (MA_CLI) run: e.g., 10–12 minutes (configurable).
  - GPT‑Researcher programmatic run: same envelope.
  - FPF run: appropriate timebox based on expected workload.
- Behavior on timeout: kill the subprocess; capture recent stdout/stderr tails; write a {base}.{kind}.failed.json with keys error, timeout_seconds, stdout_tail, stderr_tail. 
- Behavior on non-zero exit: do not raise; instead write {base}.{kind}.failed.json with error details and tails. 
- Rationale: This preserves orchestration continuity, ensures mdoutputs is never empty, and avoids conflating hang, error, and success states.

#### 5.2 Output Discovery Without Content Parsing
- Treat tools as black boxes that write files. ACM should:
  - Prefer explicit outputs that the tool prints (“Report written to …”) when these are stable and easily parsed as file paths; but because ACM should not parse content, prefer simple file enumeration in the tool’s known output directory.
  - Enumerate likely output folders used by tools after each run module completes:
    - For MA_CLI (GPT‑R multi-agent), list newly written files in its reported output directory (e.g., ./outputs/run_*/… or MA temp run folder) within the run window timeframe, filter by known extensions (md, docx, pdf).
    - For GPT‑Researcher programmatic runs, collect all artifacts (md, docx) reported by the subprocess script (if it prints explicit JSON path lines) or, if that printing is unstable, fall back to scanning the configured output folder for newly modified files within the time window.
    - For FPF, scan its configured output directory for newly modified artifacts (txt/md/doc).
  - Copy whatever was found—verbatim—without opening or transforming content.

#### 5.3 Copy Semantics And Naming
- Mirror the input path into output_base, create directories up-front, and copy found files using a unique suffix strategy to avoid collisions:
  - output_base/<relative_input_dir>/<baseName>.<kind>.<runIndex>.<modelLabel>.<uid>.<ext>
- Model/provider labels used only for naming context, not for tool behavior. If provider:model was combined incorrectly in config, normalize labels for file naming only (split provider:model for label text), without touching tool config files.
- Copy atomically: copy to a temp name in the destination folder, then replace to avoid partial writes.

#### 5.4 Failure Artifact Policy
- If a run yields no files (after enumeration) and the process either timed out or exited non-zero, write the single failure artifact file alongside where success files would have been placed:
  - {base}.{kind}.failed.json 
  - Include: error, stage (“timeout” or “non_zero_exit”), exit_code (when applicable), stdout_tail, stderr_tail.
- This guarantees a visible result for every run (success or failure), eliminating the “empty” output directory ambiguity.

#### 5.5 Observability And Logs
- Maintain a heartbeat at the ACM level.
- At run boundaries, print: starting run, timeouts configured, and upon completion either “Copied N artifacts” or “Wrote failed.json” with reason.
- Optionally summarize total elapsed time per run for operators.

#### 5.6 Windows-Specific Considerations
- Avoid any write attempts to protected directories (e.g., Program Files). Ensure working directory is the run’s temp folder or a user-writable path. This is relevant to tool behavior as well, but from ACM, ensure cwd and environment are set to benign, writable locations.
- Enforce UTF‑8 for subprocess I/O to avoid encoding confusion in logs.

### 6) Detailed Implementation Strategy (ACM-Only)
- MA Runner:
  - Launch MA_CLI with an explicit per-run working directory under a writable temp path.
  - Apply a global timeout; on timeout/exit error, write failed.json with recent log tails.
  - After process ends (success), enumerate the designated MA output folder(s) for newly modified md/docx/pdf since run start—copy all found artifacts; if none found, write failed.json noting “no artifacts found.”
- GPT‑Researcher (programmatic):
  - Wrap run function with asyncio.wait_for timebox.
  - If outputs are not explicitly returned by the subprocess in a machine-parsable way (e.g., clean JSON path line), prefer enumeration of the configured output folder for any new artifacts since run start; copy them.
  - On error/timeout and no files, write failed.json.
- FilePromptForge (FPF):
  - Same pattern: timebox, enumerate configured output folder after completion, copy artifacts; else failed.json.

### 7) Risk Assessment (Within Constraints)
- False negatives in enumeration: If tool moves or renames outputs after completion, enumeration windows can miss files. Mitigation: use “since run start” timestamps and include both modification-time and creation-time filters. Where the tool prints file paths reliably in its stdout, capturing just those path strings (without opening the content) is acceptable—but optional.
- Long-running yet successful runs: Timeouts must be chosen to align with real workloads. Provide a clear configuration value (e.g., gptr_timeout_seconds, ma_timeout_seconds, fpf_timeout_seconds) and document recommended defaults and when to increase.
- Disk space growth: Copying large artifacts repeatedly can grow output storage. Mitigation: configure retention policy outside ACM or allow an optional pruning step after copying (out of scope of ACM).

### 8) Validation Without Modifying Tools Or Parsing Content
- Manual validation steps:
  - Run a set of MA, GPT‑R (standard/deep), and FPF runs on known inputs; confirm:
    - When the tool produces md/docx, ACM copies them to mdoutputs with the expected mirrored path and unique suffix.
    - When the tool times out or exits non-zero, ACM writes a failed.json artifact in the mirrored output directory.
  - Induce a non-zero exit in a safe way (e.g., misconfigured dependency) and confirm failed.json presence with stderr_tail explaining the error.
  - Increase timeouts and confirm long runs now complete with copied files.
- Operational metrics:
  - Count of success artifacts vs failed.json per run set.
  - Mean duration per run type and model label.
  - Zero content parsing checks: grep ACM code to ensure no content inspection or JSON normalization of tool outputs occurs.

### 9) Rollback Plan
- Because we do not modify tool code or content, rollback is trivial: disable timeouts (if undesirable) and revert to baseline process execution and blind file copying (not recommended). No changes to GPT‑R/FPF are involved.

### 10) Acceptance Criteria
- For every run entry in config.yaml:
  - Either at least one success artifact is copied (md/docx/pdf/etc.) to mdoutputs, or a single {base}.{kind}.failed.json is present.
  - No ACM code reads or parses LLM content or tool report bodies.
  - GPT‑R/FPF code remains untouched.
  - No observed indefinite “hangs”; runs either complete within the timebox or fail with a visible artifact.
- Operators can distinguish success/timeout/error instantly by looking at mdoutputs.

### Appendix A: Concrete ACM Behaviors To Keep/Remove
- Keep:
  - Process spawning with environment setup and writable cwd.
  - Global run heartbeats and console prefixes for readability.
  - Per-run timeouts and failed.json generation for timeout/non-zero exit.
  - Mirrored output directory structure and deterministic copy naming.
- Remove/Avoid:
  - Any JSON normalization of tool-generated content.
  - Any code path that opens GPTR/FPF outputs and rewrites them.
  - Any edits under api_cost_multiplier/gpt-researcher or FPF vendor trees.

### Appendix B: Operator Playbook
- When you see a failed.json:
  - Open it to read exit_code and the tail of stderr/stdout to understand the tool error. Then adjust timeouts or tool configuration outside ACM as needed.
- When outputs exist but seem incomplete or slow:
  - Increase the timeouts; check network conditions; verify the tool’s own logs and environment, since ACM does not intervene in content generation.

Closing
This ACM-only remediation ensures that, without touching GPT‑R/FPF internals or parsing any LLM output, operators reliably get either the tool’s outputs or a clear failed.json artifact for each run. It eliminates “hang” perception, preserves strict separation of concerns, and maintains consistent, predictable orchestration behavior.
