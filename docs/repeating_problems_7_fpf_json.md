# Repeating Problems: FPF OpenAI JSON Output Failures

## Problem Description
During evaluation runs utilizing File Prompt Forge (FPF) with OpenAI models, a critical failure consistently occurs when attempting to enforce JSON-formatted output (`json: True` in FPF configuration). The API calls return a `400 Bad Request` HTTP error.

The specific error messages from the OpenAI API endpoint (identified as "Responses API" based on the URL hints in `fpf_openai_main.py` and the phrasing of the error) are twofold:

1.  **Primary Error Message:** "Unsupported parameter: 'response_format'. In the Responses API, this parameter has moved to 'text.format'. Try again with the new parameter. See the API documentation for more information: https://platform.openai.com/docs/api-reference/responses/create."
2.  **Detailed Schema Validation Error (from logs):** "Invalid schema for response_format 'evaluation_result': In context=('properties', 'evaluations'), array schema missing items."

Additionally, a separate, but related, error message has been observed in the logs for OpenAI models:
"Web Search cannot be used with JSON mode."

These errors collectively prevent any OpenAI runs configured for JSON output from succeeding, leading to failed evaluations and an incomplete assessment of model performance and cost for these specific configurations.

## Root Cause Analysis
The problem arises from a combination of strict API validation, recent changes in OpenAI's Responses API, and potential incompatibilities between advanced features (such as structured output and web search) for certain models. The `fpf_openai_main.py` adapter currently constructs the payload for OpenAI API calls.

Observations:

1.  **Misleading Primary Error & API Evolution:** The message "Unsupported parameter: 'response_format'. In the Responses API, this parameter has moved to 'text.format'." is somewhat misleading. `fpf_openai_main.py` *is* already using `payload["text"]["format"]`, which is the correct, modern approach for specifying output format in the OpenAI Responses API. This part of the FPF implementation correctly adapted to the API evolution where `response_format` (a top-level parameter in older Chat Completions APIs) was deprecated in favor of nesting it under `text.format` for structured outputs in the newer Responses API.

2.  **Actual Problem: Incorrect Schema Nesting (`Invalid schema... array schema missing items`):** This is the more precise error. When `type: "json_schema"` is declared, the OpenAI API now expects a stricter nesting for the actual JSON schema definition. The `fpf_openai_main.py` adapter currently places the schema definition directly under the `format` object's `"schema"` key. However, the API's current expectation is that the entire schema definition for `type: "json_schema"` must be encapsulated within a dedicated `json_schema` key, i.e., `format.json_schema`.

    The problematic structure in `fpf_openai_main.py` is:
    ```python
    payload["text"] = {
        "format": {
            "type": "json_schema",
            "name": "evaluation_result", # This 'name' field is not part of the standard JSON schema spec under 'format' and causes validation failures.
            "schema": { # This entire object needs to be nested under a 'json_schema' key.
                "type": "object",
                "properties": {
                    "evaluations": {
                        "type": "array",
                        "items": { # This 'items' definition is fine, but its parent isn't properly nested.
                            "type": "object",
                            "properties": { /* ... */ },
                            "required": ["criterion", "score", "reason"],
                            "additionalProperties": True
                        }
                    },
                    "winner_doc_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "additionalProperties": True
            },
            "strict": False # This 'strict' flag likely belongs inside the json_schema object or is used elsewhere.
        }
    }
    ```

3.  **Incompatibility: "Web Search cannot be used with JSON mode."**: This is a critical, model-specific constraint. The `fpf_openai_main.py` adapter *enforces* web search (`"tools": [{"type": "web_search_preview"}]`) for all allowed OpenAI models (e.g., "gpt-5", "gpt-5-mini", "o4-mini", etc.) when `cfg.get("json")` is `True`. The log indicates a direct API limitation for some OpenAI models: they cannot simultaneously use web search tools and return structured JSON output. This means that even with the correct JSON schema formatting, if a model attempts both, it will fail. This limitation needs to be carefully managed, possibly by disabling JSON mode when web search is enforced, or vice versa, or by using models that explicitly support both.

## Model-Specific Considerations for OpenAI
Not all OpenAI models handle structured output and tool use identically. The `fpf_openai_main.py` has an `ALLOWED_MODELS` list, suggesting that only a subset of models are intended to enforce web search and reasoning. This implicitly acknowledges model capability differences.

For the "Responses API", models like `gpt-4o-mini` and `gpt-5` variants are generally expected to support structured output. However, the "Web Search cannot be used with JSON mode" error indicates a current restriction for the specific combination of features that FPF is enforcing. This restriction might apply dynamically based on the model chosen, the specific `tools` array content, or the `text.format` configuration.

## Impact
These issues have a significant impact on evaluation workflows:
*   **Failed Evaluations:** All runs using OpenAI models intended for JSON output fail with `400 Bad Request`, making it impossible to collect evaluation data in structured format.
*   **Inaccurate Cost Tracking:** Since runs fail, precise cost metrics for these OpenAI + JSON runs cannot be generated or aggregated due to the API errors.
*   **Workflow Blockage:** The current configuration and payload construction effectively block any FPF evaluations that rely on OpenAI JSON structured outputs.

## Proposed Solution
To fully resolve these issues, two primary changes are required in `fpf_openai_main.py`:

1.  **Correct JSON Schema Nesting:** The JSON schema definition must be correctly encapsulated under the `json_schema` key within the `format` object, and the extraneous `name` field should be removed. The `strict` flag should also be nested where expected.

2.  **Address Web Search and JSON Mode Incompatibility:** A mechanism must be implemented to handle the reported incompatibility where "Web Search cannot be used with JSON mode." This could involve:
    *   **Conditional Logic:** If `cfg.get("json")` is `True`, then the `web_search_preview` tool should potentially *not* be added to the payload for OpenAI models, or vice versa.
    *   **Configuration Guidance:** Update documentation or configuration examples to clearly state this limitation for OpenAI models in JSON mode.
    *   **Model Selection:** Only allow combinations of models and features that are known to be compatible.

### Detailed Corrected Payload Structure for `fpf_openai_main.py`
The revised structure for `payload["text"]` should be:

```python
# In fpf_openai_main.py, within the build_payload function:
if cfg.get("json") is True:
    # Use Structured Outputs (json_schema) compatible with tools/web_search.
    # Schema allows either single-doc or pairwise shapes; downstream consumers will validate precisely.
    payload["text"] = {
        "format": {
            "type": "json_schema",
            "json_schema": { # The original 'schema' dictionary contents move directly under this new 'json_schema' key.
                "type": "object",
                "properties": {
                    "evaluations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "criterion": {"type": "string"},
                                "score": {"type": "integer"},
                                "reason": {"type": "string"}
                            },
                            "required": ["criterion", "score", "reason"],
                            "additionalProperties": True
                        }
                    },
                    "winner_doc_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "additionalProperties": True # This is a JSON Schema draft 7 keyword that allows additional properties.
            },
            # The 'strict' flag should be here, directly under 'format' alongside 'type' and 'json_schema'.
            "strict": False
        }
    }
```
**Important:** The handling of including the `web_search_preview` tool needs to be revisited. If the "Web Search cannot be used with JSON mode" error is definitive across the allowed OpenAI models in this API, then the `payload["tools"] = [ws_tool]` and `payload["tool_choice"] = "auto"` lines must be conditionally excluded when `cfg.get("json") is True`.

This comprehensive approach addresses both the schema validation failure and the incompatibility between features, ensuring that FPF's integration with OpenAI's structured output capabilities is robust and functional.
