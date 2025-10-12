# Plan: Provider‑Aware JSON in FPF + Major llm-doc-eval Concurrency Refactor

Author: Cline
Date: 2025-10-12

Scope
- Re-introduce strict JSON support in FilePromptForge (FPF) in a provider‑aware way (do not blindly set JSON where it is incompatible), including a safe two‑stage flow for providers/models that cannot combine tools+JSON (e.g., Google Gemini with grounding).
- Refactor llm-doc-eval to leverage FPF’s native concurrency so evaluations (single and pairwise) run efficiently and safely under centralized concurrency limits.
- Provide a brief analysis of how ACM currently invokes FPF concurrently (generate.py) to inform the refactor.

============================================================
Part 1 — Provider‑Aware JSON in FPF
============================================================

Objective
- Accept an optional json parameter at the FPF entrypoint and propagate JSON enforcement only where compatible:
  - If provider/model supports tools+strict JSON together → single-shot JSON.
  - If incompatible (e.g., Gemini + grounding) → use a two‑stage pipeline: Stage 1 grounded content (no JSON), Stage 2 “jsonify” (tools off, JSON enforced) via configurable provider/model.

JSON mode API (top-level config/option)
- json: one of false | true | auto (default auto)
  - false: never enforce strict JSON.
  - true: always enforce strict JSON; if incompatible, fallback to two‑stage.
  - auto: decide per provider/model and grounding requirements.

Provider compatibility strategy
- Introduce a small capability helper to centralize knowledge of “tools+JSON in one call”:
  - supports_tools_plus_json(provider: str, model: str|None, grounding_required: bool) -> bool
- Initial matrix:
  - openai/* and openrouter-openai/*: True
  - google/gemini-*:
    - If grounding required (tools ON): False → must use two‑stage
    - If no grounding: True (allow responseMimeType=application/json)
  - openaidp/* (deep research): False for single-shot tools+JSON; JSON should be handled as a separate formatting step if needed.

Files to change

1) api_cost_multiplier/functions/fpf_runner.py
- Re-introduce optional json override in options:
  - options["json"] may be "auto" | True | False.
  - Before spawning FPF, patch a temp config with the requested json mode (preserving base config) so downstream FPF can read it from YAML. (Alternative: add a new CLI arg to fpf_main.py; patching keeps current CLI stable.)
- Do not directly alter tools/JSON payloads here; leave provider-specific decisions to FPF core (file_handler + adapters).

2) api_cost_multiplier/FilePromptForge/compatibility.py (new)
- Provide supports_tools_plus_json() using a simple table/regex model matcher.
- Make it easy to extend as providers evolve.

3) api_cost_multiplier/FilePromptForge/file_handler.py
- Read json mode from cfg (default "auto").
- Determine grounding requirement using grounding_enforcer + config (grounding/enforce_web_search flags).
- Routing logic:
  - If json == false: call provider as today (execute_and_verify, assert grounding/reasoning).
  - If json in {true, auto}:
    - If supports_tools_plus_json(provider, model, grounding_required) OR grounding not required:
      - Set cfg["json"] = True and perform a single call via provider.execute_and_verify (or standard HTTP + enforcer when execute_and_verify unavailable). Grounding+reasoning asserted as today.
    - Else (e.g., Google with grounding):
      - Two‑stage:
        - Stage 1 (grounded): cfg_stage1 = dict(cfg); cfg_stage1["json"] = False; call provider.execute_and_verify; assert grounding+reasoning; obtain grounded_text using provider.parse_response or JSON summary.
        - Stage 2 (jsonify): use cfg["jsonify"] with provider/model (default: OpenAI); cfg_stage2["json"] = True; build a compact strict-JSON formatting prompt from grounded_text; DO NOT enforce grounding in stage 2; perform one normal call; parse and return stage 2 response as the final “human_text”.
      - Logging: consolidated run log should include stage 1 evidence (grounding) and stage 2 JSON output; record both providers/models used.

4) api_cost_multiplier/FilePromptForge/providers/google/fpf_google_main.py
- Keep build_payload minimal:
  - When cfg["json"] is True and grounding not required: set generationConfig.responseMimeType="application/json".
  - When grounding required and cfg["json"] is True: the two‑stage logic in file_handler ensures stage 1 arrives with json=False (so provider adapter does not set responseMimeType).
- Ensure extract_reasoning/parse_response remain stable.

5) Configuration (api_cost_multiplier/FilePromptForge/fpf_config.yaml)
- Add/ensure:
  - json: "auto" (default)
  - jsonify:
    - provider: openai
    - model: gpt-4.1-mini (or gpt-5-mini)
    - temperature: optional
    - max_output_tokens: optional
- Document new keys in FilePromptForge/readme.md.

6) Tests & acceptance
- Unit tests (mock HTTP):
  - Google + grounding + json=true/auto: assert two‑stage is used; stage 1 shows grounding evidence; final output strict JSON; no 400 from Google.
  - OpenAI + grounding + json=true/auto: single-shot; strict JSON; grounding verified.
  - json=false: never enforce JSON; behavior same as today.
  - Google + no grounding + json=true: single-shot JSON allowed.
- Acceptance:
  - No regression in grounding_enforcer guarantees.
  - Consolidated logs include both stage traces for two-stage.

Risks & mitigations
- Multi-provider API drift: keep compatibility helper easy to evolve.
- Cost/time overhead of two-stage: acceptable for providers that cannot do tools+JSON in one request; document trade-offs and optional overrides.

============================================================
Part 2 — Major Refactor of llm-doc-eval to Use FPF Concurrency
============================================================

Objective
- Shift evaluator orchestration to use FPF’s native concurrency, enabling controlled parallelism across pairwise (and single) judgments while centralizing provider-aware routing and retries inside FPF.

Current llm-doc-eval behavior (summary)
- judge_backend.py generates instruction/payload temp files per pair (or single) and calls fpf_runner.run_filepromptforge_runs(..., num_runs=1) sequentially within loops.
- options={"json": True} is passed today, but fpf_runner no longer honors it; Part 1 will restore provider-aware JSON handling.

Target architecture (concurrency-aware)
- Build all needed evaluation runs (for pairwise: all N choose 2 per configured model/provider; for single: all docs per model/provider).
- Use FPF batch mode where possible to submit a JSON array of runs to a single FPF process that internally manages concurrency (via scheduler / max concurrency).
  - API: fpf_runner.run_filepromptforge_batch(runs, options) → returns list of results [(path, model_name)] for successful runs, plus batched progress logs.
- Concurrency source of truth:
  - config.llm_api.max_concurrent_llm_calls (existing in llm-doc-eval/config.yaml).
  - Pass this into options["max_concurrency"] for batch; set per-provider timeouts using config.llm_api.timeout_seconds at the FPF layer.
- JSON mode propagation:
  - options["json"] set to "auto" (or true) at the batch submission; FPF core decides provider-specific logic per run.

Detailed refactor steps

1) judge_backend.py
- New batch builder:
  - For pairwise:
    - For each configured provider:model, generate one run object per (docA, docB):
      {
        "id": "<uuid> or tuple key",
        "provider": "<provider>",
        "model": "<model>",
        "file_a": "<temp path to generated pairwise instructions>",
        "file_b": "<path to doc or minimal payload>",
        "out": "<desired output path or let FPF decide>",
        "overrides": {"max_completion_tokens": X, "reasoning_effort": Y} (optional)
      }
    - Generate all instruction files into a temp workspace directory; clean up after run.
  - For single: similar pattern with single_template.md instructions per doc.
- Submit batch:
  - options = {
      "json": "auto",                  # let FPF route provider-aware JSON
      "max_concurrency": cfg.llm_api.max_concurrent_llm_calls
    }
  - results = await fpf_runner.run_filepromptforge_batch(runs, options)
- Parse results and validate:
  - For pairwise: parse JSON from text; validate winner_doc_id ∈ {idA, idB}; reason is non-empty.
  - For single: validate evaluations array items.
- Persist to SQLite (as today).
- Error handling:
  - If some batch run fails, detect missing result IDs and record minimal diagnostics to logs; consider selective retry for failed runs (future enhancement).

2) cli.py
- No significant change to the UX; ensure help text reflects concurrency usage and that max concurrency is surfaced via config rather than CLI flags (optional override could be added later).

3) config.yaml (llm-doc-eval)
- llm_api:
  - max_concurrent_llm_calls
  - timeout_seconds
- retries:
  - attempts / base_delay_seconds / jitter (optional for future repair loop in judge_backend)
- No immediate changes required for concurrency adoption.

4) Optional enhancements (future)
- Add a local repair/retry loop on JSON parse failures in judge_backend (append repair instruction turn; exponential backoff) to increase robustness independently of FPF retries.
- Stream progress/logging back to CLI during batch execution (tail FPF logs to report in-progress status).

Acceptance criteria for eval refactor
- Pairwise run over K documents and M models runs under centralized max_concurrency with stable throughput; DB rows persisted match expectations.
- Time-to-completion reduced compared to sequential calls.
- JSON validation guarantees held constant or improved.

============================================================
Part 3 — How ACM (generate.py) Interacts with FPF Concurrency (Findings)
============================================================

File reviewed: api_cost_multiplier/generate.py

Observed usage patterns
- Async per-file orchestration:
  - For each markdown file, it concurrently kicks off:
    - GPT‑Researcher (standard) via asyncio.create_task
    - GPT‑Researcher (deep) via asyncio.create_task
    - FPF single run via asyncio.create_task(fpf_runner.run_filepromptforge_runs(..., num_runs=1))
  - Then awaits asyncio.gather on those three tasks.
- Per-file concurrency is bounded to those three tasks; files are processed sequentially across the folder (comment suggests it “can be parallelized later”).
- fpf_runner support for batch:
  - fpf_runner exposes run_filepromptforge_batch(runs, options) which supports “--runs-stdin” and an options["max_concurrency"] that maps to FPF’s internal scheduler via CLI arguments.
  - generate.py currently uses run_filepromptforge_runs with num_runs=1 (single-shot), not the batch API.

Implications for llm-doc-eval refactor
- Prefer the batch API for llm-doc-eval to centralize concurrency limits:
  - Construct all runs (for all pairs and models) and let FPF schedule them with options["max_concurrency"] sourced from llm-doc-eval/config.yaml.
- For json behavior:
  - Pass options["json"] = "auto" (or true) at batch submission; provider-aware JSON enforcement occurs inside FPF (Part 1), avoiding per-call complexity in llm-doc-eval.

============================================================
Part 4 — Timeline & Rollout
============================================================

Phase A (Provider-aware JSON in FPF)
- A1: Add compatibility.py and tests.
- A2: Re-introduce fpf_runner json override (option patch → temp config).
- A3: Update file_handler routing (single-shot vs two‑stage); logging for two‑stage.
- A4: Align google adapter and document config keys; update FilePromptForge/readme.md.
- A5: Unit tests + smoke tests (OpenAI/Google).

Phase B (llm-doc-eval concurrency refactor)
- B1: Implement batch builder in judge_backend.py for pairwise/single.
- B2: Integrate fpf_runner.run_filepromptforge_batch with options["json"] and ["max_concurrency"].
- B3: Parse results, validate, persist; clean temp generation; add informative logs.
- B4: Optional local repair/retry loop; optional progress streaming.
- B5: Smoke: run ‘run-pairwise’ over sample folder, verify DB rows and timing improvements.

============================================================
Part 5 — Risks & Mitigations
============================================================
- Provider behavior drift: encapsulate in compatibility.py with clear defaults and tests.
- Two‑stage cost latency: document tradeoffs; allow json=false to disable; allow jsonify provider override.
- Batch memory footprint with many pairs: generate instructions lazily or chunk batches if needed; use temp directories and cleanup.

============================================================
Part 6 — Deliverables
============================================================
- Provider-aware JSON routing implemented and documented in FPF (compatibility table, two‑stage for Gemini).
- Updated fpf_runner to honor optional json option; docs updated.
- llm-doc-eval batch concurrency implemented; CLI unchanged; measurable speedup; correctness maintained.
- Brief “generate.py concurrency” report integrated (this document).
