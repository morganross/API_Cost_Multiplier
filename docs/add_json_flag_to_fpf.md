# add json flag to fpf

Status: proposed
Owner: FPF maintainers
Scope: internal FPF design (no upstream callers referenced)

Goal
- Introduce a simple configuration switch to require strict JSON responses from underlying LLM providers.
- Centralize provider-specific JSON enforcement inside FPF (one place to maintain).
- Keep behavior backward compatible when the flag is off.

1) Config schema changes (fpf_config.yaml)
- Add an output block that controls JSON behavior and runtime hints.

Example:
```yaml
output:
  require_json: true           # new: turn on JSON-only responses
  use_response_schema: true    # optional: when provider supports structured schema
  response_mime_type: application/json  # optional: provider hint (e.g., Gemini)
runtime:
  streaming: false             # recommended for structured outputs
  timeout_seconds: 120         # per-call timeout
retries:
  attempts: 1                  # optional: repair attempt on invalid JSON
  backoff_seconds: 2
```

Notes:
- require_json (boolean): master switch. When true, adapters must force JSON-only output.
- use_response_schema (boolean): if provider supports schema-enforced responses (e.g., Gemini), enable it.
- response_mime_type (string): provider-specific hint, default application/json.
- runtime.streaming: false recommended to reduce schema violations (no token interleaving).
- retries: enabled only for non-compliant responses, to run a minimal “repair” attempt.

2) Runner surface (no caller details)
- Extend the existing options map to allow an override, while config remains the source of truth.

Options handling (concept):
- options.require_json: optional boolean; if omitted, use config.output.require_json.
- options.response_schema_id: optional string; indicates which schema to enforce when supported (see §3). If omitted and require_json is true, adapters apply the strongest JSON-only mode available without a schema.

Return contract:
- Keep the existing return of [(out_path, model_name_or_id)], where model_name_or_id reflects the actual provider/model resolved by FPF.

3) Schema management (optional, internal-only)
- Maintain a small internal registry of JSON shapes keyed by response_schema_id.
  - Example entries:
    - minimal_object: {"type":"object","additionalProperties":false}
    - generic_list: {"type":"array","items":{"type":"object"}}
- When use_response_schema is true and response_schema_id is provided, adapters inject the appropriate schema using the provider’s vocabulary:
  - Gemini: response_schema + response_mime_type
  - OpenAI-like (if supported by chosen API): function/tool parameters schema or response_format=json
- If no schema is provided, adapters still enforce JSON-only with the provider’s best available mechanism.

4) Provider adapter behavior

OpenAI / OpenRouter-compatible:
- Preferred mechanisms:
  - Tool/function calling with a parameters schema when feasible.
  - Or use response_format={"type":"json_object"} (Responses API), depending on SDK.
- Set non-streaming for structured outputs.
- Respect timeout from runtime.timeout_seconds.
- If the first response is not valid JSON and retries.attempts > 0:
  - Send a single repair prompt requesting ONLY compact JSON.

Google Gemini:
- Set generationConfig.response_mime_type="application/json".
- If use_response_schema is true and a schema is provided:
  - Set generationConfig.response_schema to the mapped schema vocabulary (convert from JSON Schema style to Gemini’s).
- Disable streaming for structured outputs.
- Apply a single repair attempt if provider returns non-JSON (rare when response_schema is active).

Anthropic Claude (if applicable):
- Use whatever JSON-enforcement the SDK supports (e.g., tool_use/output_format where available).
- Keep non-streaming.
- Optional single repair attempt.

5) JSON filtering and repair
- ensure_json_only(text, schema?):
  - If provider claims JSON but extra prose sneaks in, extract the first well-formed JSON object/array.
  - Validate against schema when provided (optional).
  - If invalid and retries are configured, run one repair attempt with a short instruction: “Return ONLY valid compact JSON. No markdown, no prose.”
- Keep repair attempts minimal (default 1) to cap cost/latency.

6) Logging & telemetry
- Log per-call metadata:
  - provider, model (resolved internally), require_json (on/off), use_response_schema (on/off), streaming (on/off), timeout
  - latency, optional token counts if adapters expose them
  - repair attempted: yes/no
- Redact prompts and large payloads; do not log secrets.

7) Error handling
- If require_json is true and the final response is not valid JSON after configured retries:
  - Fail the call with a clear error type (e.g., JsonEnforcementError) and include a concise diagnostic.
- Respect timeouts; surface timeout errors with actionable info.

8) Backward compatibility
- With require_json unset or false, behavior remains unchanged.
- options.require_json can override the config for targeted runs without changing the main config.
- response_schema_id is optional; the system still enforces JSON-only without a schema when provider supports a generic JSON mode.

9) Testing plan
- Unit tests (adapters):
  - OpenAI/OpenRouter: verify response_format/tool-calling returns JSON-only; validate repair path runs once when initial response is non-JSON.
  - Gemini: verify response_schema + application/json returns JSON-only; validate behavior with and without schema.
- Integration tests:
  - Configure require_json: true globally; run against multiple adapters with short prompts; assert outputs are valid JSON.
  - Toggle retries off/on and verify behavior.
- Regression tests:
  - require_json: false → current behavior preserved.

10) Migration
- Add output.require_json to config with a default (false), and a note recommending true for structured workflows.
- Document optional fields (use_response_schema, response_mime_type).
- Release note: “FPF now supports a JSON-only mode via a single config flag; providers are handled internally with best practices.”

11) Acceptance criteria
- When output.require_json=true:
  - Adapters consistently return valid JSON-only payloads (object or array) across supported providers.
  - Non-JSON outputs are auto-repaired once (if configured) or fail clearly with JsonEnforcementError.
  - Non-streaming is respected for structured outputs.
- With the flag off, legacy behavior is unchanged.

Appendix — conceptual pseudocode
```python
def build_call_options(global_cfg, options):
  require_json = options.get("require_json", global_cfg.output.require_json)
  use_schema = global_cfg.output.use_response_schema if require_json else False
  response_mime = global_cfg.output.response_mime_type or "application/json"
  streaming = False if require_json else global_cfg.runtime.streaming
  timeout = global_cfg.runtime.timeout_seconds
  schema_id = options.get("response_schema_id")
  schema = registry.get(schema_id) if (use_schema and schema_id) else None
  return {
    "require_json": require_json,
    "use_schema": use_schema,
    "response_mime_type": response_mime,
    "streaming": streaming,
    "timeout_seconds": timeout,
    "schema": schema,
  }

async def call_provider(adapter, instructions, payload, call_opts):
  raw = await adapter.invoke(
    instructions=instructions,
    payload=payload,
    streaming=call_opts["streaming"],
    timeout=call_opts["timeout_seconds"],
    response_mime_type=call_opts["response_mime_type"],
    schema=call_opts["schema"] if call_opts["use_schema"] else None,
    json_mode=call_opts["require_json"],
  )
  if call_opts["require_json"]:
    text = ensure_json_only(raw, schema=call_opts["schema"])
    if not is_valid_json(text, schema=call_opts["schema"]):
      # optional single repair
      text = attempt_repair_once(adapter, instructions, payload, call_opts)
  else:
    text = raw
  return text
