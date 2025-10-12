FPF Native Concurrency and Rate Limiting — Implementation Plan

Status
- Scope: Add native, configurable concurrency to FilePromptForge (FPF) only. ACM changes are out of scope for now.
- Concept of a “run”: A single execution that includes provider, model, file_a (instructions), file_b (input), out path, and optional overrides.
- Goal: Let FPF execute multiple runs concurrently with configurable global and per-provider limits, rate-limiting, retries, and consistent output/logging.

1) Current State (traced from api_cost_multiplier/generate.py through FPF)
- ACM drives FPF today:
  - api_cost_multiplier/generate.py delegates to functions/fpf_runner.py
  - fpf_runner.py shells out to api_cost_multiplier/FilePromptForge/fpf_main.py per run, sequentially
- Inside FPF:
  - fpf_main.py parses CLI, loads fpf_config.yaml, resolves file paths, and calls file_handler.run(...)
  - file_handler.run builds a provider payload and performs a single HTTP POST (urllib), verifies grounding+reasoning, then writes a single human-readable result
  - Providers (providers/openai, providers/google, providers/openaidp) expose:
    - validate_model, build_payload, execute_and_verify/execute_dp_background, parse_response, extract_reasoning
- Important details:
  - file_handler.run is synchronous; one network call per run
  - Output file naming uses a run_id to avoid collisions for single runs
  - Logging writes a consolidated JSON log per run under FilePromptForge/logs
  - file_handler temporarily mutates process-wide os.environ to set API keys

2) Concurrency Targets and Non-Goals
- Targets:
  - Concurrently execute many independent runs (different files, models, providers) within a single FPF invocation
  - Provide global and per-provider concurrency and rate-limit controls
  - Implement robust retries and backoff for 429/5xx
  - Guarantee unique output files and non-interleaved per-run logs
- Non-goals (for this phase):
  - Change ACM to pass batches (may come later)
  - Split a single run into multiple concurrent sub-steps (FPF’s run is one network call today)

3) Challenges and Pitfalls
- Global mutable state:
  - file_handler.run sets os.environ[PROVIDER_API_KEY] then reads it back to build headers. Under concurrency, concurrent writes to os.environ are racy and process-wide.
  - Plan: Stop mutating os.environ inside file_handler. Read API keys from the canonical .env and pass them directly to request headers for each run.
- Output path collisions:
  - Concurrency must ensure unique out paths. The existing run_id handled inside file_handler is good; ensure run_id is correlated per run and also included in logs.
- Log coherence:
  - Concurrent logs should remain readable and attributable to a specific run. The existing consolidated per-run JSON log is good. Add a run_id prefix/context to console logging paths for batch mode.
- Provider limits:
  - Enforce both concurrency (parallel requests in flight) and rate limits (QPS/burst), preferably per provider with an optional global cap.
  - Handle 429/5xx (exponential backoff + jitter) and timeouts.
- Blocking HTTP:
  - Current provider HTTP calls use urllib (blocking). Moving to aiohttp is more invasive. ThreadPool-based concurrency is a safer low-change option.
- Config evolution:
  - Concurrency and rate limiting must be expressible in fpf_config.yaml without breaking existing single-run usage.
- Backwards compatibility:
  - Single-run CLI usage must continue to work unchanged.

4) Proposed Solutions (with pros/cons)

A) ThreadPool Orchestrator (Recommended)
- Description:
  - Introduce a new batch scheduler inside FPF that:
    - Accepts an array of RunSpec items (provider, model, file_a, file_b, optional out)
    - Limits concurrency via ThreadPoolExecutor(max_workers=…)
    - Applies per-provider and global rate limits (token bucket + semaphores)
    - Retries with exponential backoff and jitter on 429/5xx
  - Keep provider adapters and file_handler.run synchronous and unchanged in their external behavior; do not switch to aiohttp now.
- Pros:
  - Minimal refactor; uses I/O-bound threading which plays well with urllib (releases GIL during I/O)
  - Fast to implement, easy to reason about, preserves existing provider logic
  - Works on Windows/macOS/Linux without new dependencies
- Cons:
  - Threads are heavier than async tasks; but acceptable for reasonable concurrency (tens to low hundreds)

B) Async Orchestrator + Wrapping Blocking Calls in Executors
- Description:
  - Make an asyncio-based orchestrator using asyncio.Semaphore + asyncio.gather for structure, and wrap file_handler.run calls via loop.run_in_executor.
  - Rate limit via async token bucket.
- Pros:
  - Aligns with modern async patterns; good future-proofing if providers later become async
- Cons:
  - Adds event-loop complexity while still using thread executors to call blocking urllib
  - Slightly higher complexity for limited net benefit now

C) Subprocess Fan-Out (Spawn fpf_main per run)
- Description:
  - fpf_main spawns multiple subprocesses for each run and monitors them with a small supervisor.
- Pros:
  - Strong isolation, simple error containment
- Cons:
  - Heavier resource usage, more moving parts (stdout/err capture), awkward rate limiting
  - Harder to share token buckets across processes without IPC

D) Full Async Refactor (aiohttp in providers)
- Description:
  - Refactor provider HTTP to aiohttp and build fully async pipeline.
- Pros:
  - Best long-term performance for very high concurrency
- Cons:
  - High effort, broad changes to providers and file_handler, larger risk

Recommendation
- Adopt Solution A (ThreadPool Orchestrator) now.
  - It meets needs with minimal risk and avoids invasive provider changes.
  - Can be evolved to B or D later if/when providers become async.

5) Config Changes (fpf_config.yaml)
Add a backward-compatible concurrency and batch schema:

concurrency:
  enabled: true
  # Global cap across all providers
  max_concurrency: 4
  # Optional per-provider caps
  per_provider:
    openai:
      max_concurrency: 2
      rate_limit:
        qps: 1        # tokens per second
        burst: 2
    google:
      max_concurrency: 4
      rate_limit:
        qps: 5
        burst: 10
    openaidp:
      max_concurrency: 1
      rate_limit:
        qps: 0.2
        burst: 1
  retry:
    max_retries: 5
    base_delay_ms: 500
    max_delay_ms: 60000
    jitter: full      # none|full
  timeout_seconds: 7200  # default per-request timeout; provider may override

# Optional batch declaration (when present, run batch mode)
runs:
  - id: run1
    provider: openai
    model: gpt-5-mini
    file_a: test/input/sample_utf8.txt
    file_b: test/prompts/standard_prompt.txt
    out: test/output/<file_b_stem>.<model_name>.<run_id>.fpf.response.md
  - id: run2
    provider: google
    model: gemini-1.5-flash
    file_a: test/input/sample_utf8.txt
    file_b: test/prompts/standard_prompt.txt

Notes:
- If runs is absent, FPF behaves in single-run mode (today’s behavior).
- If runs is present and concurrency.enabled is true, FPF orchestrates concurrent batch execution.
- Placeholders remain valid in out (e.g., <file_b_stem>, <model_name>, <run_id>).

6) Code Changes

New module: FilePromptForge/scheduler.py
- Data structures:
  - RunSpec dataclass:
    - id: Optional[str]
    - provider: str
    - model: str
    - file_a: str
    - file_b: str
    - out: Optional[str]
    - overrides: dict (e.g., reasoning_effort, max_completion_tokens)
- Rate limiting:
  - TokenBucket per provider (qps, burst):
    - Refill tokens based on time.monotonic()
    - acquire() busy-waits with sleep (e.g., 10–50ms) until a token is available
  - Concurrency:
    - Global semaphore (max_concurrency)
    - Per-provider semaphores (max_concurrency)
- Retry/Backoff:
  - Wrap execution of a single RunSpec (call file_handler.run) in:
    - for attempt in 1..max_retries:
      - try: rate_limit.acquire(); run(); break
      - except transient (HTTPError 429/5xx, timeouts):
        - sleep backoff = min(max_delay, base * 2^(attempt-1) + jitter)
      - except fatal: re-raise
- Execution:
  - ThreadPoolExecutor(max_workers = concurrency.max_concurrency or sum(per_provider.max_concurrency))
  - Submit tasks that:
    - Acquire global + provider semaphores
    - Acquire provider token bucket
    - Call file_handler.run(provider/model overrides, out path placeholders), catch/log exceptions
    - Return (ok, result_path, model, provider, run_id, error)
- Logging:
  - Ensure run_id is passed through and included in log messages and out file name
  - Print concise per-run lifecycle logs: queued → started → success/fail

Adjustments to fpf_main.py
- New CLI flags (back-compatible):
  - --max-concurrency N (override config)
  - --batch (force batch mode even if runs is present; optional)
  - --runs-config path.yaml (optional alternative to embedding runs in fpf_config.yaml)
- Behavior:
  - Load fpf_config.yaml
  - If runs present (len > 0) and concurrency.enabled:
    - Build RunSpec list from runs[]
    - Call scheduler.run_many(specs, concurrency_config)
    - Print a summary with per-run status and exit non-zero if any failed (configurable)
  - Else:
    - Proceed with existing single-run path calling file_handler.run
- Output:
  - For batch mode, print each result_path on its own line and write a JSON summary file to logs/ with run results and timings.

Adjustments to file_handler.py (thread-safety)
- Stop mutating os.environ during runs:
  - Read API keys strictly from FilePromptForge/.env (as now) using _read_key_from_env_file
  - Use local variable api_key and construct headers directly
  - Do not set os.environ[API_KEY_NAME] under concurrency (removes racy global state)
- Keep behavior of:
  - Reasoning + web_search enforced
  - Consolidated per-run JSON logs with unique filename per run
- Ensure run_id is generated once per call and used for:
  - out file naming
  - per-run consolidated log naming
  - log context prefix (optional enhancement)

Provider adapters
- No required changes for concurrency (they already operate per-call)
- Keep using urllib.request; scheduler’s threads will release GIL during network I/O
- Maintain enforce/verify hooks as-is

7) Pseudocode Sketches

scheduler.py

class TokenBucket:
    def __init__(self, qps: float, burst: int):
        self.qps = max(qps, 0.0)
        self.capacity = max(burst, 1)
        self.tokens = self.capacity
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        if self.qps <= 0:
            # effectively no tokens; act as strict 1-per-(1/qps) if qps==0 → disallow unless overridden
            self.qps = 0.0001  # or raise
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                added = elapsed * self.qps
                if added >= 1.0:
                    self.tokens = min(self.capacity, self.tokens + int(added))
                    self.last = now
                if self.tokens > 0:
                    self.tokens -= 1
                    return
            time.sleep(0.05)

class RunExecutor:
    def __init__(self, cfg):
        self.global_sem = threading.Semaphore(cfg.global_max)
        self.provider_sems = {p: threading.Semaphore(v.max_concurrency) ...}
        self.provider_buckets = {p: TokenBucket(v.qps, v.burst) ...}
        self.retry = cfg.retry
        self.timeout = cfg.timeout

    def run_one(self, spec: RunSpec):
        # Build per-call overrides
        def attempt():
            # Apply rate limit before request
            self.provider_buckets[spec.provider].acquire()
            return file_handler.run(file_a=spec.file_a, file_b=spec.file_b, out_path=spec.out,
                                    config_path=self.config_path, env_path=self.env_path,
                                    provider=spec.provider, model=spec.model,
                                    reasoning_effort=spec.overrides.get("reasoning_effort"),
                                    max_completion_tokens=spec.overrides.get("max_completion_tokens"))
        delay = self.retry.base
        for i in range(self.retry.max):
            try:
                with self.global_sem, self.provider_sems[spec.provider]:
                    return attempt()
            except TransientError as e:
                time.sleep(jitter(delay)); delay = min(delay*2, self.retry.max_delay)
        raise

    def run_many(self, specs: list[RunSpec]):
        with ThreadPoolExecutor(max_workers=self.global_max) as pool:
            futures = [pool.submit(self.run_one, s) for s in specs]
            return [f.result() for f in as_completed(futures)]

fpf_main.py

if runs and cfg.concurrency.enabled:
    specs = parse_runs(cfg.runs)
    results = scheduler.run_many(specs, cfg.concurrency)
    # print summary, write logs, propagate failures appropriately
else:
    # existing single-run path

8) Rate Limiting, Retries, and Timeouts
- Rate limiting:
  - Per-provider token buckets avoid bursting above configured QPS/burst
  - Global max_concurrency caps simultaneous in-flight requests
- Retries:
  - On HTTP 429 and 5xx, exponential backoff with jitter
  - Respect provider-specific guidance where known; keep configurable in YAML
- Timeouts:
  - Per-request timeout remains enforced by provider implementations (e.g., 7200 for openaidp deep research)
  - Optionally allow overriding via concurrency.timeout_seconds routed into provider calls

9) Backwards Compatibility and Migration
- Single-run usage unchanged:
  - fpf_main.py --file-a A --file-b B [--model ... --provider ...]
- Enabling concurrency:
  - Add runs: [] to fpf_config.yaml and turn on concurrency.enabled
  - Optionally override with CLI --max-concurrency N
- ACM remains unchanged:
  - ACM can still call FPF per run; later we can add an ACM “batch” entrypoint to pass multiple runs in one call

10) Testing Strategy
- Unit tests:
  - TokenBucket behavior (refill, burst, steady-state QPS)
  - Retry/backoff decision logic (429/5xx transient detection)
  - Out path placeholder resolution with run_id uniqueness
  - Thread-safety: ensure no shared mutable global (os.environ) is written during run
- Integration tests:
  - Batch with mixed providers
  - Intentionally trigger rate limiting (mock provider) to validate pacing
  - Simulate 429/5xx with exponential backoff
  - Ensure per-run JSON logs and out files are produced and valid
- Load tests (optional):
  - Use mock endpoints to validate concurrency throughput at different max_concurrency settings

11) Open Questions for Confirmation
- Default limits:
  - What defaults should we set for global max_concurrency? (Proposal: 4)
  - Any known provider QPS guidance you want encoded as defaults? (e.g., OpenAI: 1 QPS with burst 2)
- Batch schema:
  - Do you prefer “runs” embedded in fpf_config.yaml as shown, or a separate runs.yaml referenced by --runs-config?
- Failure policy:
  - In batch mode, should FPF exit non-zero if any run fails, or only if all runs fail?
- Output collation:
  - Should we write a batch summary JSON manifest listing per-run results/paths in logs/?

12) Step-by-Step Implementation Plan
1. Config schema and parsing
   - Extend fpf_config.yaml to include concurrency and runs (back-compatible)
   - Add schema validation in fpf_main.py with clear error messages
2. New scheduler module
   - Implement RunSpec, TokenBucket, and RunExecutor as described
   - Include transient error classification (HTTP 429, 5xx, timeouts)
3. file_handler thread-safety
   - Stop writing to os.environ during runs
   - Use local headers with API keys read from canonical .env
4. fpf_main integration
   - Detect runs[] + concurrency.enabled paths
   - Wire CLI override for --max-concurrency
   - Print per-run result paths and write batch manifest JSON
5. Logging improvements
   - Ensure each run has a run_id included in console logs (prefix) and consolidated JSON name
6. Tests
   - Unit tests for token bucket and retry logic
   - Integration batch tests over providers with mocks
7. Documentation
   - Update readme.md with examples:
     - Single-run (legacy)
     - Batch-run via config
     - Concurrency and rate-limiting settings
8. (Optional) ACM follow-up (later)
   - Add ACM runner support to pass a batch of runs to FPF in one call

Appendix: Minimal YAML Examples

Single-run (legacy; no concurrency)
model: gemini-1.5-flash
provider: google
test:
  file_a: test/input/sample_utf8.txt
  file_b: test/prompts/standard_prompt.txt
  out: test/output/<file_b_stem>.<model_name>.fpf.response.md

Batch with concurrency
concurrency:
  enabled: true
  max_concurrency: 4
  per_provider:
    openai: { max_concurrency: 2, rate_limit: { qps: 1, burst: 2 } }
    google: { max_concurrency: 4, rate_limit: { qps: 5, burst: 10 } }
  retry:
    max_retries: 5
    base_delay_ms: 500
    max_delay_ms: 60000
    jitter: full
runs:
  - id: g5m-doc1
    provider: openai
    model: gpt-5-mini
    file_a: test/input/sample_utf8.txt
    file_b: test/prompts/standard_prompt.txt
  - id: g15-doc1
    provider: google
    model: gemini-1.5-flash
    file_a: test/input/sample_utf8.txt
    file_b: test/prompts/standard_prompt.txt

Conclusion
This plan adds native, configurable concurrency to FPF with a low-risk thread-based scheduler, robust rate limiting, and retries. It preserves current single-run behavior, avoids broad provider refactors, and positions FPF to accept batch requests from ACM later with no breaking changes.
