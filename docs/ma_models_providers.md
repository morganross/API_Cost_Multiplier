Report: Models & Providers Supported by the Multi-Agent (MA) Flow (GPT‑Researcher)
=================================================================================

Summary
-------
This report documents which LLM models and providers are supported by the GPT‑Researcher multi‑agent (MA) flow and how the MA flow selects and uses models. It is based on the repository docs (gpt-researcher docs), README content, the upstream gpt-researcher GitHub README (assafelovic/gpt-researcher), and relevant GitHub issues/PRs.

Short answer: GPT‑Researcher and the MA flow use the same underlying LLM provider infrastructure. The MA flow primarily uses the configured SMART_LLM (for reasoning/report writing) and FAST_LLM (for fast tasks / agent selection). GPT‑Researcher supports a broad set of providers via the GenericLLMProvider layer (OpenAI, Anthropic, Azure OpenAI, Cohere, Google GenAI/Vertex, Ollama, Mistral, Together, HuggingFace, Groq, Bedrock, Litellm, etc.). The multi‑agent runner leverages the SMART_LLM configuration when producing reports; other model roles (FAST/STRATEGIC) are available and configurable.

Where this information comes from
- Local docs: process_markdown/gpt-researcher/docs/docs/gpt-researcher/llms/llms.md
- Local docs: process_markdown/gpt-researcher/docs/docs/gpt-researcher/gptr/config.md
- Local docs: process_markdown/gpt-researcher/docs/docs/gpt-researcher/multi_agents/README.md
- Code references: gpt_researcher.llm_provider.generic.base and gpt_researcher/utils/llm.py
- Upstream repo README & issues: https://github.com/assafelovic/gpt-researcher (README, issues, PRs)
- Local MA_CLI and multi_agents docs in this repository

Detailed findings
-----------------

1) Are GPT‑Researcher and the MA flow different?
- Not fundamentally. The MA (multi_agents) flow is a subcomponent of GPT‑Researcher that orchestrates multiple agents (planner, execution, publisher). It uses the same LLM/provider infrastructure as the rest of GPT‑Researcher—i.e., the GenericLLMProvider layer and the configured env variables (SMART_LLM, FAST_LLM, STRATEGIC_LLM).
- The MA flow emphasizes using SMART_LLM for report writing / reasoning tasks. Some parts of the agent architecture may use FAST_LLM for agent selection or quick operations (the repo contains places that choose FAST_LLM for agent selection).

2) Which model roles exist (config names) and what are they for?
- FAST_LLM: used for fast, low-cost operations (summaries, intermediate tasks, agent selection). Example default: openai:gpt-4o-mini
- SMART_LLM: used for heavier reasoning and final report generation. Example default: openai:gpt-4.1 (docs sometimes reference gpt-5)
- STRATEGIC_LLM: used for planning/strategic steps in workflows.
- EMBEDDING provider (EMBEDDING / EMBEDDING_PROVIDER): separate for vector embeddings.

3) Providers & models explicitly listed in docs
The repo docs enumerate many supported providers and give examples showing the expected environment variable format provider:model. The list includes (non‑exhaustive, based on docs and code):
- openai (OpenAI GPT family; examples: openai:gpt-4o-mini, openai:gpt-4.1, openai:gpt-5, openai:o4-mini)
- azure_openai (Azure deployments; e.g., azure_openai:deployment_name)
- anthropic (Claude family; e.g., anthropic:claude-2.1, anthropic:claude-3-opus)
- cohere (cohere:command)
- google_vertexai (Vertex AI)
- google_genai (Google GenAI)
- ollama (local Ollama host)
- mistralai (Mistral)
- together (Together models)
- fireworks
- huggingface (HF Hub models)
- groq
- bedrock (AWS Bedrock/backends)
- litellm
- vllm_openai / vllm backends (self-hosted)
- openrouter (routing service that can proxy to various backends using an "openrouter:provider/model" syntax)
- aimlapi, dashscope, deepseek, etc. — docs include examples for many external aggregator services

4) How providers/models are specified (configuration style)
- Environment variables: FAST_LLM, SMART_LLM, STRATEGIC_LLM, EMBEDDING, EMBEDDING_PROVIDER. Format: provider:modelspec
  - Examples:
    - FAST_LLM=openai:gpt-4o-mini
    - SMART_LLM=openai:gpt-4.1
    - STRATEGIC_LLM=google_genai:gemini-1.5-pro
    - EMBEDDING=openai:text-embedding-3-small
- Additional provider‑specific env vars may be required:
  - OPENAI_API_KEY, AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT, ANTHROPIC_API_KEY, COHERE_API_KEY, OLLAMA_BASE_URL, etc.
- GenericLLMProvider.from_provider(...) is used in code to construct provider clients and will accept provider-specific kwargs.

5) Provider features & parameter gating
- The code explicitly gates certain arguments (temperature, max_tokens, reasoning_effort) depending on model/provider support:
  - SUPPORT_REASONING_EFFORT_MODELS: models that accept a reasoning_effort kwarg (e.g., O3/O4 mini family, and models routed via OpenRouter that expose reasoning controls)
  - NO_SUPPORT_TEMPERATURE_MODELS: models that don't support temperature (or only default), so the code avoids sending temperature to them. This was added in response to issues/PRs (see references).
- OpenRouter routing: docs show examples using openrouter:openai/o3-mini or openrouter:google/gemini... and the repo will forward reasoning and web-search plugin flags where supported.

6) MA behavior & model selection
- The multi‑agent flow (multi_agents) primarily uses SMART_LLM for heavy tasks (report writing), and FAST_LLM for agent selection/fast sub‑tasks. Some commits/PRs changed agent selection to use FAST_LLM in particular paths.
- MA runs can be configured via task.json or runtime overrides; the wrapper writes a runtime task.json and runs the multi_agents runner; the task JSON can include "model" or other overrides (max_sections, publish_formats, etc.).
- The MA CLI & multi_agents runner can be routed through OpenRouter or use provider SDKs (Google GenAI, OpenAI, etc.). When using provider-native grounding (e.g., Gemini with google.genai), the repo uses provider SDKs for best results.

7) Practical notes & recommendations
- Defaults & recommended stack:
  - The repository recommends OpenAI GPT models + Tavily Search for best out‑of‑the‑box performance.
  - For private/self-hosted usage, Ollama, vLLM, and Hugging Face models are supported.
- For provider‑native advanced features (native grounding, Google tools), prefer the provider SDK (e.g., google.genai) rather than proxy routing—provider SDKs expose provider-native tooling.
- Set the appropriate API keys and endpoint env variables to avoid runtime errors.

Unsupported LLM API types and features (what GPT‑Researcher / MA do NOT support)
-------------------------------------------------------------------------------

I reviewed repository docs, code, and GitHub issues/PRs to identify LLM API parameter types and behaviors the project explicitly guards against or does not support reliably. The list below reflects both code checks (NO_SUPPORT_TEMPERATURE_MODELS, SUPPORT_REASONING_EFFORT_MODELS, gating logic) and issue threads where users reported provider incompatibilities.

1) Models / endpoints that do NOT accept a "temperature" parameter
- Evidence:
  - PR: "feat(llm): stop sending temperature to non‑supporting models" (merged) — project added logic to avoid sending temperature to models that error on that param.
  - Issues: reports (eg. issue #1427) where agent selection failed for OpenAI models that don't accept temperature.
- Impact:
  - If a provider/model returns 400 for "temperature", GPT‑Researcher avoids sending the parameter for models in NO_SUPPORT_TEMPERATURE_MODELS.
- Examples:
  - Certain newer provider endpoints or specialized hosted models (some enterprise/backends or aggregated APIs) reject custom temperature parameters; the code maintains a NO_SUPPORT_TEMPERATURE_MODELS list.

2) Models that do NOT accept "max_tokens" or similar token-limiting kwargs
- Evidence:
  - The code gates max_tokens for models in NO_SUPPORT_TEMPERATURE_MODELS and handles max_tokens behavior per-provider; some backends expect different param names or disallow explicit max tokens.
- Impact:
  - GPT‑Researcher adjusts/maximizes token handling: some models are called with default limits or with max_tokens omitted.

3) Models that do not support streaming or websocket-style streaming
- Evidence:
  - Multiple providers have differing streaming APIs; the GenericLLMProvider attempts to normalize streaming, but not all providers support it the same way.
  - Issues/PRs in repo show streaming-related fixes and gating.
- Impact:
  - Streaming (server-sent events / websocket incremental tokens) may not be available for every provider; code falls back to non-streaming where needed.

4) Models that do not accept provider-specific "reasoning_effort" or internal reasoning kwargs
- Evidence:
  - SUPPORT_REASONING_EFFORT_MODELS is a whitelist; only some models (o3/o4 mini family and similar) accept reasoning_effort. The code sets reasoning_effort only for models in that list.
  - PRs added Reasoning support; docs explain reasoning is forwarded only when supported.
- Impact:
  - Passing reasoning_effort to an unsupported provider/model can yield errors or be ignored. GPT‑Researcher forwards reasoning only when supported.

5) Provider-native tool integrations that are NOT available when routed via a proxy (OpenRouter)
- Evidence:
  - OpenRouter provides model-agnostic plugin/web-search features and normalizes requests, but provider-native toolkits (e.g., Google GenAI GoogleSearch tool) may only be available when using the provider SDK directly.
- Impact:
  - If you rely on provider-native grounding/tooling, prefer direct provider SDK usage (google.genai for Gemini) rather than routing through OpenRouter. Some capabilities (custom tools, advanced grounding) may not be forwarded correctly by the proxy.

6) Strict, custom provider parameter names / deployment-name-only APIs (Azure deployments)
- Evidence:
  - Azure OpenAI requires using deployment names rather than model names and requires AZURE_* env vars; repo docs call this out (running-with-azure.md). Using an incorrect format will fail.
- Impact:
  - Mis-specified deployment/model names or missing AZURE_OPENAI_API_KEY/ENDPOINT cause runtime failures.

7) Models with incompatible "extra_body" or non-LangChain parameter expectations
- Evidence:
  - Some providers validate request bodies strictly; passing unexpected fields may cause 4xx responses. The repo adds defensive logic and allows per-provider llm_kwargs, but not all providers accept arbitrary extra fields.
- Impact:
  - When adding custom llm_kwargs, verify provider docs. OpenRouter can accept extra fields but backend behavior varies.





Guidance / Recommended mitigations
- Use provider:model format for env vars and consult provider docs for accepted parameters.
- Avoid sending temperature/max_tokens to models known to reject them (repo lists NO_SUPPORT_TEMPERATURE_MODELS).
- For provider-native grounding (search tools, Google tools), use provider SDKs (google.genai) rather than proxy routing where possible.
- Test combinations (model + retriever + grounding) in a staging environment; several repo issues report edge-case failures.
- Keep the repo's code / llm-provider list up to date; some models/providers gain or lose parameter support as APIs evolve.

Appendix — where to look in repo for gating logic
- gpt_researcher/gpt_researcher/utils/llm.py
- gpt_researcher/llm_provider/generic/base.py
- gpt_researcher/docs/docs/gpt-researcher/llms/llms.md
- GitHub issues (search "temperature", "reasoning_effort", provider names) for known incompatibilities.

If you want I will:
- Commit and push this document update (including the new "Unsupported" section) to the repository now.
- Or, expand the unsupported section with more examples drawn from additional specific issues (I can fetch and cite several issue numbers in-text).

Choose "commit & push" or "expand more" (I will then run the chosen action).
