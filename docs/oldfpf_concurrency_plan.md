FPF Native Concurrency and Rate Limiting Plan (Revised)
==========================================================

Author: Cline
Date: 2025-10-11

Executive Summary
- Goal: Move concurrency and rate limiting into FilePromptForge (FPF) itself. FPF should natively schedule and throttle its own runs, independent of ACM (api_cost_multiplier).
- Scope: Implement concurrency inside the FilePromptForge package (not in ACM). ACM will continue to request individual runs for now; in a later phase ACM will hand FPF an entire batch of runs at once to schedule internally.
- Concurrency concept: FPF operates on “runs,” where a run = {provider, model, file_a, file_b, optional out}. FPF config and CLI should express concurrency in terms of runs, not “files in flight.”

Prior Flow and Gap
- Current invocation path observed earlier: ACM (generate.py/runner.py) → fpf_runner (spawns subprocess) → FilePromptForge/fpf_main.py → file_handler.run (single request).
- Earlier proposal added concurrency at the ACM layer. That is not the desired ownership model. Concurrency should live inside FPF so:
  - FPF works standalone with native parallelism.
  - ACM remains a thin orchestrator that can later pass a batch of runs to FPF and let FPF schedule them internally.

Design Overview (FPF-Owned)
1) Single-run remains unchanged
   - fpf_main.py continues to support today’s single-run mode:
     python fpf_main.py --file-a A --file-b B [--out OUT] [--provider P] [--model M]
   - file_handler.run keeps all existing guarantees (provider-side web_search used and reasoning present; sidecar logging preserved).

2) Native batch mode in FPF
   - Add a batch runner that accepts an array of runs, each run being {provider, model, file_a, file_b, optional out}.
   - FPF schedules these runs concurrently according to its own config (runs_in_flight) and per-provider limits (rpm, concurrent).
   - Deep-research models (o3-deep-research*, o4-mini-deep-research*, similar) DO NOT count against FPF’s RPM limiter but DO respect provider concurrency caps and longer timeouts.

3) Rate limiting and concurrency primitives (internal to FPF)
   - Global “runs_in_flight” semaphore limits how many runs can execute simultaneously.
   - Per-provider gates:
     - rpm limiter (sliding window over 60s) to cap starts/minute for non-deep-research models.
     - concurrency semaphore to cap simultaneous calls per provider (applies to all models including deep-research).
   - These live inside FilePromptForge so FPF can run natively concurrent when called directly.

4) ACM usage model
   - Near term: ACM keeps calling FPF one run at a time (unchanged behavior). FPF’s single-run mode works as-is; no requirement to pass batches yet.
   - Later: ACM will hand off a batch of runs to FPF in a single call. FPF will perform all scheduling, rate limiting, and execution internally.

FPF Configuration (No “files in flight”)
- Remove any notion of “files_in_flight” from FPF configuration. Concurrency is expressed in runs, not files.
- Backward compatible config extension (optional keys):
  concurrency:
    runs_in_flight: 3           # maximum concurrent FPF runs
  rate_limits:
    openai:   { rpm: 120, concurrent: 5 }
    google:   { rpm: 60,  concurrent: 2 }
    openaidp: { rpm: 30,  concurrent: 1 }
  timeouts:
    default_seconds: 600
    openaidp_seconds: 7200
- If these keys are absent, FPF behaves serially (current default). Provider/model continue to be taken from this config unless overridden by CLI.

CLI Changes (FPF)
- Keep existing single-run flags unchanged.
- Add batch mode:
  - --batch-json path/to/jobs.json
  - jobs.json format:
    [
      {"provider":"openai","model":"gpt-5-mini","file_a":"instructions.txt","file_b":"doc1.md","out":"out1.txt"},
      {"provider":"google","model":"gemini-2.5-flash","file_a":"instructions.txt","file_b":"doc2.md","out":"out2.txt"}
    ]
- Optional CLI overrides for concurrency and rate limits can be added, but config should remain the primary source. CLI values would override config for convenience.

Implementation Plan (FPF-only)
Phase A (this revision)
- Create FPF-internal limiters module (e.g., FilePromptForge/fpf/limiters.py):
  - AsyncRPMWindowLimiter (sliding window 60s)
  - ProviderLimiter (rpm gate + concurrency semaphore)
  - Limits (global runs_in_flight + per-provider limiters)
  - Deep-research RPM bypass via model-name check
- Create FPF batch runner (FilePromptForge/fpf/batch_runner.py):
  - Input: array of run specs (provider, model, file_a, file_b, out?).
  - For each run: apply provider gate, then call file_handler.run in background (e.g., asyncio.to_thread).
  - Collect outputs and print one output path per line (or structured JSON if desired).
- Extend fpf_main.py:
  - If --batch-json is not provided, run single-run path (no change).
  - If --batch-json is provided, load jobs, build Limits from fpf_config.yaml (and optional CLI overrides), and dispatch to batch_runner.
- Update fpf_config.yaml documentation (no breaking changes):
  - Add optional concurrency.runs_in_flight, rate_limits, timeouts.
  - Note deep-research RPM bypass.
- Maintain existing validation and per-run logging invariants.

Phase B (later)
- Update ACM to pass a batch of runs to FPF instead of iterating runs itself.
- ACM becomes a simple client; FPF schedules runs internally using its own config and limiters.

Backward Compatibility
- Single-run behavior unchanged.
- If concurrency/rate_limits are absent in FPF config, FPF remains serial.
- Provider/model selection in FPF config continues to work; CLI flags still override.
- ACM can continue asking for runs one-by-one without any change.

Testing Strategy
- Unit tests for limiters: rpm windowing, concurrency caps, deep-research RPM bypass.
- Integration tests:
  - Batch of runs with mixed providers/models including deep-research models; verify no RPM counting for deep-research while concurrency caps still apply.
  - Confirm unique output paths and stable logging.
  - Verify that omission of concurrency/rate_limits yields serial execution identical to today.

Open Questions
- Default values for runs_in_flight and per-provider caps (suggest runs_in_flight=3; openai concurrent=5, google=2, openaidp=1, adjust based on env).
- Output format of batch mode: one path per line (simple) vs JSON array (richer). We can support both with a flag (e.g., --batch-output json|lines).
- Whether to add per-model overrides in rate_limits if needed in the future.

Summary
- FPF owns concurrency and rate limiting using “runs” as the unit of parallelism.
- No “files in flight” in FPF config; runs_in_flight controls parallelism.
- Deep-research models bypass RPM accounting but still respect concurrency caps and longer timeouts.
- ACM continues to request runs now; later it will pass the full batch to FPF to schedule natively.
