# GPT-Researcher: Streaming & Temperature Changes (Summary)

This file documents the local changes applied to ensure GPT-5 compatibility and to control streaming/temperature behavior for programmatic runs inside this repo (process_markdown). Apply carefully and review before merging to other branches.

Summary (one-line)
- added gpt5 support by removing streaming and temp; prefer repo archive; local edits to force non-streaming for programmatic runs and to gate temperature per-model.

Exhaustive list of edits and rationale
1. New wrapper to prefer local sources
   - File added: `process_markdown/run_gptr_local.py`
   - Purpose: Ensures the checked-out `process_markdown/gpt-researcher` directory is first on `sys.path` so imports `import gpt_researcher` resolve to the local files (not any installed package). Also loads `.env` and exposes small helpers:
     - run_cli_equivalent(query, report_type, tone, encoding, query_domains)
     - run_detailed_report(query, query_domains)
   - Why: Allows process_markdown scripts to run against the local copy without uninstalling the pip-installed package.

2. Make process_markdown prefer the wrapper (local import)
   - File modified: `process_markdown/generate.py`
   - Change: added `import process_markdown.run_gptr_local` near the top (side-effect) before importing helper modules that use `gpt_researcher`.
   - Why: Single-line change ensures local package precedence for generate pipeline runs.

3. Prefer repo archive (download change)
   - File modified: `process_markdown/download_and_extract.py`
   - Change: replaced hard-coded v.3.3.3 release zip with logic that tries:
     1. `https://github.com/assafelovic/gpt-researcher/archive/refs/heads/main.zip`
     2. `https://github.com/assafelovic/gpt-researcher/archive/refs/heads/master.zip`
     3. fallback `.../refs/tags/v.3.3.3.zip`
   - Why: Pull hotfixes (post-release PRs) automatically when extracting remote code snapshots.

4. Temperature gating: mark models that don't accept temperature
   - File modified: `process_markdown/gpt-researcher/gpt_researcher/llm_provider/generic/base.py`
   - Change: added GPT‑5 family identifiers (e.g. `gpt-5`, `gpt-5-mini`, `gpt-5-nano`) to `NO_SUPPORT_TEMPERATURE_MODELS`.
   - Why: Prevent sending `temperature` parameter to models/providers that reject it, avoiding 400 errors like "Unsupported value: 'temperature' does not support 0.35 with this model".

5. Conditional LLM init (avoid sending unsupported params)
   - File modified: `process_markdown/gpt-researcher/backend/chat/chat.py`
   - Change: build `llm_init_kwargs` dynamically and only set `temperature` / `max_tokens` when the canonical model supports it (canonicalization strips provider prefix).
   - Why: Avoid provider errors and make initialization robust across provider endpoints.

6. Central LLM call-site: canonicalization, retries, and forced non-streaming
   - File modified: `process_markdown/gpt-researcher/gpt_researcher/utils/llm.py`
   - Changes:
     - Canonicalize model names (strip provider prefix like `openai:` and any trailing path) to decide model capabilities.
     - Add logging for provider, model, and key kwargs to assist debugging.
     - Add retry logic to retry without `temperature` when the provider returns a temperature-related error.
     - Force non-streaming for programmatic runs by passing `effective_stream=False` to `provider.get_chat_response`.
   - Why: Avoid streaming permission rejections and temperature-related 400s during batch/programmatic runs; ensure GPT‑5 runs succeed even if streaming is gated on the account.

7. README documentation
   - File modified: `process_markdown/README.md` — appended troubleshooting note (RuntimeWarning fix for llm-doc-eval CLI).
   - New file added: `STREAMING-README.md` (this file) — contains full, exhaustive summary of streaming/temperature-related changes and rationale so reviewers can see exact edits and reasoning.

Behavioral implications & recommendations
- Non-streaming enforced:
  - Programmatic runs (generate pipeline) are now set to receive full model responses (no streaming). This avoids organization-level streaming permission errors on OpenAI for GPT‑5 in this environment.
  - Downside: No incremental output; longer wait for final result; less real-time visibility.
- Temperature gating:
  - We avoid sending `temperature` to models that do not accept it. If you prefer to re-enable `temperature` for specific runs, change `NO_SUPPORT_TEMPERATURE_MODELS` or use the wrapper to set model-specific parameters.
- How to reinstate streaming safely:
  - Option A (recommended long-term): implement streaming→non-stream fallback — attempt stream=True, and on streaming-permission error retry with stream=False.
  - Option B: verify your OpenAI organization for streaming access (https://platform.openai.com/settings/organization/general → Verify Organization). Streaming permission propagation may take ~15 minutes after verification.
  - Option C: add configurable env var (e.g., `GPTR_DISABLE_STREAMING=true/false`) and respect it in `create_chat_completion`.

Verification & testing notes
- I executed `process_markdown/generate.py` locally after modifications: it produced outputs and saved multiple GPT‑Researcher reports (model: openai:gpt-5) while avoiding streaming permission errors. Some PDF scraping still failed due to SSL verification issues on the host (system CA / certifi).
- All local edits were committed and pushed to the process_markdown remote `main` branch.

Audit checklist (what to review before merging)
- Confirm the forced non-streaming change is acceptable for your production workflow; otherwise implement an env toggle or fallback logic.
- Review additions to `NO_SUPPORT_TEMPERATURE_MODELS` and verify they match your provider-model naming conventions.
- Consider addressing SSL CA in the environment (install/upgrade `certifi`, configure OS CA) to fix PDF scraping errors.

Contact & rollback
- All changes are local to the `process_markdown` tree and were pushed to remote `main`. To revert streaming forcing, revert the `create_chat_completion` changes in `gpt_researcher/gpt_researcher/utils/llm.py` and re-run tests.
