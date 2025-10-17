# Latest Evaluation Run Failure Report (2025-10-17)

This report details individual failures observed during the `evaluate.py` run executed on 2025-10-17. The evaluation aimed to assess various models' performance under enforced grounding and structured output policies.

## Summary of Failures by Model:

### 1. google/gemini-2.0-flash
**Failure Type:** Consistent "missing grounding (web_search/citations)"
**Details:** This model consistently failed to produce the required grounding signals in its responses. The system's strict enforcement policy (requiring presence of web search citations) blocked the output, leading to a failed run for this model in multiple instances (single and pairwise evaluations).
**Example Error Log:**
```
WARNING fpf_scheduler: Run failed (attempt 1/1) id=single-google-gemini-2.0-flash-Census_Bureau.fpf... provider=google model=gemini-2.0-flash err=Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written. See logs for details.
```
**Notes:** This indicates either a limitation in the model's ability to provide consistent grounding under the specified prompt/system instructions, or an issue with the prompt construction for this specific model that prevents it from utilizing web search effectively to generate verifiable citations.

### 2. openai/gpt-5-nano
**Failure Type:** Intermittent "HTTP 429: Too Many Requests - insufficient_quota"
**Details:** This model encountered "Too Many Requests" errors due to insufficient quota during several runs. While some runs involving this model were successful, the frequent 429 errors indicate a rate limit or billing issue rather than an inherent model capability failure. This makes the model unreliable for consistent evaluation in the current environment configuration.
**Example Error Log:**
```
WARNING fpf_scheduler: Run failed (attempt 1/1) id=pair-openai-gpt-5-nano-Census_Bureau.fpf... provider=openai model=gpt-5-nano err=HTTP error 429: Too Many Requests - {
  "error": {
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.",
    "type": "insufficient_quota",
    "param": null,
    "code": "insufficient_quota"
  }
}
```
**Notes:** To ensure reliable evaluation for this model, the OpenAI API quota and billing details need to be reviewed and adjusted.

### 3. openai/o4-mini
**Failure Type:** Intermittent "HTTP 429: Too Many Requests - insufficient_quota"
**Details:** Similar to `gpt-5-nano`, `o4-mini` also hit "Too Many Requests" errors due to quota limitations during the evaluation. This resulted in failed runs, suggesting that despite potential capabilities, its current operational status is hindered by API access restrictions. This prevents it from being consistently evaluated.
**Example Error Log:**
```
WARNING fpf_scheduler: Run failed (attempt 1/1) id=pair-openai-o4-mini-Census_Bureau.fpf... provider=openai model=o4-mini err=HTTP error 429: Too Many Requests - {
  "error": {
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.",
    "type": "insufficient_quota",
    "param": null,
    "code": "insufficient_quota"
  }
}
```
**Notes:** As with `gpt-5-nano`, resolving the API quota for OpenAI would be necessary to properly assess this model's performance in our evaluation framework. This model was previously flagged in reports for web search compatibility issues, and the current quota errors only add to its intermittent status.

### 4. google/gemini-2.5-flash-lite
**Failure Type:** Intermittent "missing grounding (web_search/citations)"
**Details:** Although this model showed successful runs, it also exhibited intermittent failures due to "missing grounding (web_search/citations)" in some cases (e.g., `single-google-gemini-2.5-flash-lite-Census_Bureau.fpf.7.gpt-5.0tc.txt-6bcc2856`). This indicates variability in its ability to consistently provide the required verifiable citations under the strict enforcement policy, marking it as an intermittent performer for these criteria.
**Example Error Log:**
```
WARNING fpf_scheduler: Run failed (attempt 1/1) id=single-google-gemini-2.5-flash-lite-Census_Bureau.fpf... provider=google model=gemini-2.5-flash-lite err=Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written. See logs for details.
```
**Notes:** Further investigation into prompt optimization or retry mechanisms specific to this model could potentially improve its consistency.

## Conclusion and Recommendations:
The evaluation highlights both consistent grounding issues with `google/gemini-2.0-flash` and acute quota limitations for several OpenAI models (`gpt-5-nano`, `o4-mini`), rendering them unreliable for continuous evaluation without addressing these external factors. `google/gemini-2.5-flash-lite` shows mixed performance, suggesting careful prompt engineering or relaxed policies may be needed for consistent use.

For future evaluations, it is recommended to:
1.  Investigate and resolve OpenAI API quota limitations for `gpt-5-nano` and `o4-mini`.
2.  Refine prompts for `google/gemini-2.0-flash` to explicitly enforce grounding, or consider if this model is suitable for tasks requiring strict citation enforcement.
3.  Monitor `google/gemini-2.5-flash-lite` for grounding consistency and optimize usage if necessary.

## Comparison of Specified vs. Actual Runs:

- **Specified in `llm-doc-eval/config.yaml`**: For each single input document, the configuration specifies 7 single-document evaluations and 21 pairwise evaluations, totaling 28 runs.
- **Actual runs performed during this evaluation**: The `evaluate.py` script executed 21 single-document runs and 12 pairwise runs, summing up to 33 total runs.

The difference arises because `evaluate.py` combines configurations from both `api_cost_multiplier/config.yaml` (which defines the models and iterations for generating documents) and `llm-doc-eval/config.yaml` (which defines the judge models for evaluating those generated documents).
