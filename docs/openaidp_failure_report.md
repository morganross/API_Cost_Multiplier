# OpenAIDP (openaidp) Failure — Investigation & Recommended Remediation

Date: 2025-10-04
Author: ACM orchestration (generated)

## Executive summary

During the run of `api_cost_multiplier/generate.py` several FilePromptForge (FPF) runs that used the `openaidp` provider failed with the error "Background DP task failed" (background DP id printed in logs). You and your team invested considerable effort getting openaidp integrated; this report summarizes prior mitigation attempts (from repository docs and code), what the run logs show today, likely root causes, and concrete next steps to stabilize openaidp-backed runs.

Key findings
- The FPF integration moved from an "old" CLI to a new fpf_main/file_handler contract; the new provider model uses a background DP (data-processing) endpoint for some long-running tasks. The failing path is the background DP handling (openaidp provider), which returned status `failed` for at least one background response id.
- Repo documentation and patches show repeated attempts to harden provider behavior (streaming shims, response normalization, token limits). These mitigations helped other failure classes but did not address background DP lifecycle issues.
- Immediate pragmatic fixes: add better error-handling and retries around openaidp background task submission and polling; capture and surface the provider's consolidated JSON logs; ensure env and provider_url configuration and API keys are correct for the DP workflow.

## What the logs show (per last run)

From the run output captured when you ran `generate.py`:
- FPF invocation for openaidp / o3-deep-research:
  - Command executed (FPF): python .../FilePromptForge/fpf_main.py --config ... --env ... --file-a <instructions> --file-b <input.md> --out <outpath>
  - The provider printed a DP submission response id: resp_01a44e4d975614220068e13477b4fc8195a2c2dcc3b18540f6
  - The orchestrator polled the DP task and eventually received status `failed` (elapsed ~15.5s in the captured log) and raised:
    RuntimeError: Background DP task failed (id=resp_01a44e4d975614220068e13477b4fc8195a2c2dcc3b18540f6)
- Result: the FPF subprocess exited non-zero (exit code 2) and the run was marked as failed; no output file copied to `test/mdoutputs` for that run.
- Consolidated per-run JSON log files were still written to FilePromptForge/logs/ — they contain the provider request/response details and should be inspected.

Relevant log artifacts (from console output snippets)
- FilePromptForge consolidated log: FilePromptForge/logs/20251004T075135-d53c23dc.json (example - check exact run id paths written in your logs)
- FPF subprocess stderr shows the RuntimeError stack from file_handler.py -> providers/openaidp/fpf_openaidp_main.py (line ~391 in the code snapshot in the logs).

## What was tried previously (from repository docs & code)

I reviewed the repository docs and code related to FPF/MA/GPTR integration:
- `docs/FPF_integration.md` — describes the new FPF CLI contract and the strict `.env`-based key loading. Notes that new FPF enforces web_search usage & reasoning and outputs text files; it also writes consolidated logs to FilePromptForge/logs/.
- `docs/MA_CLI_and_GPTR_integration_failure_report.md` — discusses several classes of failures and the hardening already applied (plan normalization, streaming shims, timeouts, writer normalization).
- `patches/sitecustomize.py` — contains monkeypatches to make upstream modules return normalized structures and to disable streaming behavior.
- `functions/fpf_runner.py` / `FilePromptForge/file_handler.py` / `providers/openaidp/fpf_openaidp_main.py` — code paths implementing FPF invocation and provider-specific DP handling.

Prior attempts (documented in the repo)
- Enforced non-streaming and added shims to normalize provider responses (prevents other classes of errors).
- Added per-run consolidated logs and stricter validation (web_search required, reasoning required).
- Existing code already attempts to poll background DP responses and raise on failure — which is where the current run fails.

## Likely root causes for the openaidp background DP failure

1. Background DP job itself failed server-side (provider returned status `failed`).
   - This is indicated by the poll returning `failed`. Causes could be provider-side validations, missing/incorrect payload, or provider internal errors.

2. Missing or incorrect environment (FilePromptForge/.env).
   - The new FPF code loads API keys exclusively from `FilePromptForge/.env`. If the DP endpoint requires additional keys, scopes, or a provider_url override that is not present/correct, the provider may fail at job run time.

3. Invalid/unsupported payload arguments for the openaidp DP endpoint.
   - The DP payload (reasoning settings, tools, background flags) may be invalid, or the provider rejected the combination (e.g., unsupported model or parameter like `temperature`).

4. Background DP timeouts/quotas or platform-level limits
   - The provider may queue but then fail early because of account quotas, billing/permission errors, or internal DP worker timeouts.

5. Unhandled provider error surfaced as RuntimeError
   - The FPF adapter code currently treats any `status != "completed"` as a hard failure; if the DP failed with a subcode that should be retried (e.g., transient infra error), there is no automatic retry policy.

6. Missing web_search or policy check flags
   - FilePromptForge enforces that a run must use web_search and include reasoning; if the provider's DP flow did not include those tools correctly, the run might be aborted per policy enforcement.

## Concrete recommended actions (short-term, actionable)

A. Immediate debugging steps (do these first)
1. Inspect the per-run consolidated JSON log for the failing run:
   - Path pattern: api_cost_multiplier/FilePromptForge/logs/20251004T*.json
   - Open the consolidated JSON file that corresponds to the failing run id (the run logs printed the path when it was written).
   - Look for `response` for the background DP: its `status`, `error` object, and any `tool_choice`/`tools` payload in the submitted action.
2. Capture the exact provider request payload that was submitted to openaidp:
   - file_handler writes request payloads into the consolidated log; inspect headers and body to confirm model, tools, and reasoning fields.
3. Confirm API keys and `FilePromptForge/.env`:
   - Ensure the `openaidp` (or expected DP service) credentials are present in FilePromptForge/.env and match the provider/provider_url expected by the adapter.

B. Quick code-level mitigations (low-risk, fast)
1. Add a retry loop around the DP background submission + poll:
   - On transient `failed` substatus (network or 5xx semantics), retry 1–2 times with exponential backoff before treating as fatal.
2. Improve logging on DP failure:
   - When raising the RuntimeError, include `raw_json` for the DP response (or at least send to the consolidated log) and echo the provider `error` subfields and `response_id`.
3. Save the DP response body to a failure artifact next to the run temp out directory so you have the provider raw trace for support/billing escalation.

C. Medium-term fixes (next 1–2 sprints)
1. Add targeted validation of DP payload prior to submission:
   - Validate model capability & DP mode (does the model support background DP tasks?).
   - Strip unsupported parameters (e.g., temperature values that provider rejects) for DP runs.
2. Modify provider adapter error handling:
   - In `FilePromptForge/providers/openaidp/fpf_openaidp_main.py` handle background DP statuses:
     - `queued` or `processing` ⇒ continue polling
     - `failed` ⇒ inspect `error.code` and map to: retryable (retry) vs terminal (fail)
     - `completed` ⇒ parse response normally
3. If DP tasks are commonly used, add a configurable `dp_poll_timeout_seconds` and `dp_retry_on_fail` flags in fpf_config.yaml and in the openaidp adapter.

D. Operational / account checks
1. Verify provider account health:
   - Check billing, DP quotas, and whether the account has permission to run DP workloads.
2. If the consolidated log shows a provider-side error that is a known service problem (quota, model deprecation, or invalid parameter), open ticket with the provider including the DP response id printed in the log.

## Suggested concrete patch (example)

In `FilePromptForge/providers/openaidp/fpf_openaidp_main.py` (where the error is raised), wrap the DP poll/response handling with:

- A 3-attempt retry on `failed` responses that contain transient markers (5xx-ish codes or "temporary" messages).
- When finally failing, write the raw DP response JSON into a `{run_id}.dp_failed.json` file in the run temp directory and copy that into `test/mdoutputs/<mirrored_path>` so the failure is visible to operators.

Also add better console output on failure:
- Print: "OPENAIDP DP failed (id=...); saving raw response to <path>; see FilePromptForge/logs/<file>.json for consolidated log."

## What to include in a report you can send to upstream provider support

When escalating to provider support include:
- DP response id (printed in run logs) — e.g., resp_01a44e4d975614220068e13477b4fc8195a2c2dcc3b18540f6
- Consolidated per-run JSON log file (attach)
- The exact request payload used (found in consolidated log)
- Timestamps and run id from the ACM run (from your runner logs)
- Your account/project id and the environment (test/dev) used

## Recommended next steps for you (priority order)

1. Inspect the consolidated JSON log that matches the failing run immediately — it will usually contain the DP `error` object that explains why the DP failed.
2. Confirm `.env` values under `api_cost_multiplier/FilePromptForge/.env`.
3. Add the quick mitigations: DP retry logic and saving raw DP response for failed runs, then re-run the failing openaidp job.
4. If DP still fails with a provider error: open a support ticket with the provider including the DP response id and consolidated JSON log.
5. Once stable, add a small automated check in CI / dev that submits a small DP job (or an SDK echo) to validate DP path before running production jobs.

## Files & places to inspect now

- Per-run consolidated logs: api_cost_multiplier/FilePromptForge/logs/*.json (open the latest file that the run printed)
- FPF adapter (openaidp): api_cost_multiplier/FilePromptForge/providers/openaidp/fpf_openaidp_main.py
- FPF orchestration and polling logic: api_cost_multiplier/FilePromptForge/file_handler.py
- FPF config & .env: api_cost_multiplier/FilePromptForge/fpf_config.yaml and api_cost_multiplier/FilePromptForge/.env
- Runner logs you already captured in the terminal when you ran generate.py — note the DP response id printed in the error stack.

## Closing

The `openaidp` failure observed in your run is consistent with a background DP job failing server-side and the adapter treating that as fatal. Repository docs show many prior fixes for other failure classes (streaming, plan normalization, token limits) — those helped other parts of the pipeline but do not remove the need for robust DP lifecycle handling and retries. The fastest wins are: inspect the consolidated run log to get the provider `error` details; add a small retry + artifact-capture patch in the openaidp adapter; and re-run. If that still fails with a provider-side error, escalate with the DP response id and the consolidated JSON log.

If you want, I can:
- Read and summarize the exact consolidated JSON log file for the failing run if you tell me which logs file you want me to inspect (e.g., the file path printed in your run output), or
- Apply a safe local patch that implements the DP retry + failure artifact capture in `FilePromptForge/providers/openaidp/fpf_openaidp_main.py` (I will prepare the patch and show it to you before writing), or
- Draft a support-ticket template you can send to the provider with the required fields.
