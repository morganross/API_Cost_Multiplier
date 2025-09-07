Max Tokens — Definitive Guide for API_Cost_Multiplier
=====================================================

Last updated: 2025-09-06

Executive summary
-----------------
"Max tokens" is a core parameter that limits how many tokens a model may generate (and in some APIs how many tokens in the response are permitted). Over time different providers and SDKs have used different parameter names (e.g., max_tokens, max_completion_tokens, maxOutputTokens, max_tokens_to_sample). This repository has repeatedly hit two classes of issues:

- Parameter name mismatches: passing `max_tokens` to a model/provider that expects `max_completion_tokens` (causes 400 Unsupported parameter).
- Token-limit overrun: sending requests whose total tokens (input+requested output or embeddings batch) exceed provider limits.

This document explains what "max tokens" means, how the project historically used it, where the code currently references it, common failure modes, exact fixes and recommended code changes, and a long-term mitigation strategy including tests and monitoring.

1) What "max tokens" actually means
----------------------------------
- For generative endpoints: "max tokens" typically limits the number of tokens the model will return for the completion. Input tokens still consume the model's context window; many providers require (input tokens + max_tokens_for_output) <= model_context_window.
- For some newer provider endpoints and SDKs the name changed:
  - OpenAI (modern Responses API / official SDKs): max_completion_tokens (preferred for some models)
  - OpenAI older chat completions: max_tokens
  - Google Gemini (genai): maxOutputTokens
  - Anthropic: max_tokens_to_sample
  - OpenRouter: provider-specific naming (often max_tokens)
- For embeddings: "max tokens per request" can apply to the input tokenized size; batching many texts together may exceed the provider embedding input limit even if each piece is small.

2) Provider parameter mapping (canonical)
-----------------------------------------
Use a small mapping when building provider calls:

- OpenAI (modern Responses / chat completions):
  - Preferred: max_completion_tokens
  - Fallback older: max_tokens
- Google (Gemini via genai): maxOutputTokens
- Anthropic: max_tokens_to_sample
- OpenRouter: max_tokens (depends on adapter)
- FilePromptForge in this repo: historically used `max_tokens` for OpenAI, which produced an error for models that require `max_completion_tokens`.

3) Project history (what we found in this repo)
------------------------------------------------
Key docs and traces discovered while investigating:

- api_cost_multiplier/docs/gptr_api_token_limit_fix.md
  - Describes an error: "Requested 378510 tokens, max 300000 tokens per request" — root cause: embeddings / batching requesting too many tokens.
  - Fix applied: set EMBEDDING_KWARGS.chunk_size so LangChain/OpenAI embeddings batch size is bounded.

- api_cost_multiplier/docs/gptr_model_fix.md
  - Fixes unrelated provider:model doubling bug but documents that token-limit and param problems persisted elsewhere.

- generate run output + api_cost_multiplier/docs/generate_errors_report.md
  - Reported:
    - AttributeError in researcher (sub_queries being a string) — fixed separately.
    - FilePromptForge produced: openai.BadRequestError: "Unsupported parameter: 'max_tokens' ... Use 'max_completion_tokens' instead."

- Code locations where `max_tokens` (or variants) appear (non-exhaustive):
  - api_cost_multiplier/FilePromptForge/gpt_processor_main.py — sends API calls using client.chat.completions.create(..., max_tokens=max_tokens) — produced unsupported-parameter error. See exact location and patch below.
  - api_cost_multiplier/FilePromptForge/grounding/adapters/* — adapters use "max_tokens" semantics; google_adapter maps to "maxOutputTokens".
  - api_cost_multiplier/model_registry/providers/*.yaml — mapping of canonical parameter names per provider (openai.yaml uses max_completion_tokens; google.yaml uses maxOutputTokens; anthropic.yaml uses max_tokens_to_sample).
  - api_cost_multiplier/gpt-researcher/gpt_researcher/utils/llm.py — llm init uses provider_kwargs['max_tokens'].
  - api_cost_multiplier/gpt-researcher/actions/query_processing.py and report_generation.py — pass max_tokens values (cfg.smart_token_limit etc).
  - api_cost_multiplier/presets.yaml and FilePromptForge/default_config.yaml — default max_tokens values.

4) Concrete recent failures and root causes
-------------------------------------------
A. Unsupported parameter (400) — OpenAI: "Unsupported parameter: 'max_tokens' ... Use 'max_completion_tokens' instead."
- Cause: client SDK or model expects new parameter name; code passed legacy name unconditionally.
- File: api_cost_multiplier/FilePromptForge/gpt_processor_main.py (client.chat.completions.create(..., max_tokens=max_tokens))
- Impact: request rejected, FPF run fails, no .md output created.

B. Requested tokens > maximum allowed (max_tokens_per_request)
- Cause: embeddings or generation requests aggregated too many tokens in a single call (either via large batches or insufficient chunking).
- Files/areas: gpt_researcher context compression & embedding pipeline; EMBEDDING_KWARGS chunk handling.
- Fix applied in repo docs: set EMBEDDING_KWARGS["chunk_size"] and ensure text splitter chunk sizes are conservative.

5) Correct ways to use max tokens (best practices)
--------------------------------------------------
- Always separate input token counting and output tokens: ensure input_tokens + desired_output_max_tokens <= model_context_window.
- Use token counting (tiktoken) to measure input tokens before making requests.
  - Use tokenizers consistent with the model. For OpenAI family use tiktoken with appropriate encoding (e.g., cl100k_base).
- For embeddings:
  - Chunk input documents by character or token length (characters are faster but token-based is more precise).
  - Enforce a per-request token cap and a per-batch item limit. Prefer explicit chunk_size and batch_size settings to ensure the embedding client doesn't send overly large requests.
- Parameter mapping:
  - Build provider adapters that translate canonical application parameter (smart_token_limit) to provider param name:
    - canonical -> provider mapping table (example in model_registry/providers/*.yaml).
  - Use a single central adapter layer for API calls rather than scattering conditional logic.
- Defensive API call:
  - Try new parameter name first (max_completion_tokens) for modern OpenAI SDKs; if that fails with BadRequest/unsupported_parameter, retry with legacy `max_tokens`.
  - Log clearly which parameter name was used and full provider/model string.
- Use config values for token limits:
  - Provide per-provider token limits and smart_token_limit in config (this repo already has cfg.smart_token_limit and cfg.strategic_token_limit), and centralize their use when building requests.

6) Exact code patches / snippets (apply these)
----------------------------------------------
Below are minimal, concrete patches to reduce repeated errors. Edit the specified files accordingly.

A) File: api_cost_multiplier/FilePromptForge/gpt_processor_main.py
Replace the call that currently does:

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )

With the robust provider-aware block:

    try:
        if provider.lower() == "openai":
            # Prefer modern parameter name for OpenAI Responses
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens
            )
        else:
            # Other providers may accept max_tokens
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
    except Exception as e:
        # If provider rejected parameter name (unsupported_parameter), try fallback
        if "unsupported_parameter" in str(e) or "max_tokens" in str(e).lower():
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages
