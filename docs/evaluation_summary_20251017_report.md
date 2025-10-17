# Evaluation Run Summary - 2025-10-17

This report summarizes the results of the evaluation run performed on 2025-10-17 at approximately 08:53 AM PDT. The evaluation involved both single and pairwise execution batches across various models.

## Overall Status

- **Single Execution Batch:** 20 out of 21 runs succeeded, 1 run failed.
- **Pairwise Execution Batches:** All 3 batches completed successfully with 3/3 runs in each, showing no observed failures.
- **Total Cost:** [EVAL COST] total_cost_usd=1.144028

## Expected Runs (Based on `api_cost_multiplier/config.yaml`)

The `config.yaml` specifies the following models for evaluation with `iterations_default: 2`:
- `type: fpf`, `provider: google`, `model: gemini-2.5-flash`
- `type: fpf`, `provider: google`, `model: gemini-2.5-flash-lite`
- `type: fpf`, `provider: google`, `model: gemini-2.5-pro`
- `type: dr`, `provider: openai`, `model: gpt-5`
- `type: dr`, `provider: openai`, `model: gpt-5-mini`

Note: The evaluation processed one input file (`Census Bureau.md`), so each model from the `runs` configuration was expected to be evaluated repeatedly to fulfill any batching logic.

## Detailed Run Results

The following is a comprehensive list of every run that occurred during this evaluation batch, along with its specific outcome:

### Single Batch Runs (Total: 21)

1.  **ID:** `single-google-gemini-2.5-flash-lite-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-e8e60b9c`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **FAILED**
    -   **Error:** `"Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written."`

2.  **ID:** `single-google-gemini-2.5-flash-lite-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-08fe683f`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-flash-lite_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_08fe683f.txt`

3.  **ID:** `single-google-gemini-2.5-flash-lite-Census_Bureau.fpf.7.gpt-5.0tc.txt-658ae3d8`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-flash-lite_Census_Bureau.fpf.7.gpt-5.0tc.txt_658ae3d8.txt`

4.  **ID:** `single-google-gemini-2.5-pro-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-d4d0d7c4`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-pro_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_d4d0d7c4.txt`

5.  **ID:** `single-google-gemini-2.5-pro-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-2e60f0bf`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-pro_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_2e60f0bf.txt`

6.  **ID:** `single-google-gemini-2.5-pro-Census_Bureau.fpf.7.gpt-5.0tc.txt-424434c2`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-pro_Census_Bureau.fpf.7.gpt-5.0tc.txt_424434c2.txt`

7.  **ID:** `single-google-gemini-2.5-flash-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-a0bf32e3`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-flash_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_a0bf32e3.txt`

8.  **ID:** `single-google-gemini-2.5-flash-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-bce25d07`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-flash_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_bce25d07.txt`

9.  **ID:** `single-openai-o4-mini-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-bf86ff45`
    -   **Provider:** `openai`, **Model:** `o4-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_o4-mini_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_bf86ff45.txt`

10. **ID:** `single-google-gemini-2.5-flash-Census_Bureau.fpf.7.gpt-5.0tc.txt-ab76a0f6`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_google_gemini-2.5-flash_Census_Bureau.fpf.7.gpt-5.0tc.txt_ab76a0f6.txt`

11. **ID:** `single-openai-gpt-5-nano-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-cb563e38`
    -   **Provider:** `openai`, **Model:** `gpt-5-nano`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-nano_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_cb563e38.txt`

12. **ID:** `single-openai-o4-mini-Census_Bureau.fpf.7.gpt-5.0tc.txt-80476944`
    -   **Provider:** `openai`, **Model:** `o4-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_o4-mini_Census_Bureau.fpf.7.gpt-5.0tc.txt_80476944.txt`

13. **ID:** `single-openai-gpt-5-nano-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-d26119ad`
    -   **Provider:** `openai`, **Model:** `gpt-5-nano`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-nano_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_d26119ad.txt`

14. **ID:** `single-openai-gpt-5-nano-Census_Bureau.fpf.7.gpt-5.0tc.txt-23929a62`
    -   **Provider:** `openai`, **Model:** `gpt-5-nano`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-nano_Census_Bureau.fpf.7.gpt-5.0tc.txt_23929a62.txt`

15. **ID:** `single-openai-gpt-5-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-6b8b068b`
    -   **Provider:** `openai`, **Model:** `gpt-5`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_6b8b068b.txt`

16. **ID:** `single-openai-gpt-5-mini-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-f176b1de`
    -   **Provider:** `openai`, **Model:** `gpt-5-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-mini_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_f176b1de.txt`

17. **ID:** `single-openai-gpt-5-mini-Census_Bureau.fpf.7.gpt-5.0tc.txt-173ee502`
    -   **Provider:** `openai`, **Model:** `gpt-5-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-mini_Census_Bureau.fpf.7.gpt-5.0tc.txt_173ee502.txt`

18. **ID:** `single-openai-o4-mini-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-09b9e19e`
    -   **Provider:** `openai`, **Model:** `o4-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_o4-mini_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_09b9e19e.txt`

19. **ID:** `single-openai-gpt-5-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-0f71c833`
    -   **Provider:** `openai`, **Model:** `gpt-5`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_0f71c833.txt`

20. **ID:** `single-openai-gpt-5-Census_Bureau.fpf.7.gpt-5.0tc.txt-09eb5932`
    -   **Provider:** `openai`, **Model:** `gpt-5`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5_Census_Bureau.fpf.7.gpt-5.0tc.txt_09eb5932.txt`

21. **ID:** `single-openai-gpt-5-mini-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-cb789e4a`
    -   **Provider:** `openai`, **Model:** `gpt-5-mini`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_single_batch_24bwfxzb\\out_single_openai_gpt-5-mini_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_cb789e4a.txt`


### Pairwise Batch Runs (Total: 9, across 3 batches)

**Batch 1 Results:**
1.  **ID:** `pair-google-gemini-2.5-flash-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-74e1d17f`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_oo2ydav8\\out_pair_google_gemini-2.5-flash_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_74e1d17f.txt`

2.  **ID:** `pair-google-gemini-2.5-flash-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-02b1e7bd`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_oo2ydav8\\out_pair_google_gemini-2.5-flash_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_Census_Bureau.fpf.7.gpt-5.0tc.txt_02b1e7bd.txt`

3.  **ID:** `pair-google-gemini-2.5-flash-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-670dea18`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_oo2ydav8\\out_pair_google_gemini-2.5-flash_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Census_Bureau.fpf.7.gpt-5.0tc.txt_670dea18.txt`

**Batch 2 Results:**
1.  **ID:** `pair-google-gemini-2.5-flash-lite-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-14033cdd`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_ohqnnblv\\out_pair_google_gemini-2.5-flash-lite_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_Census_Bureau.fpf.7.gpt-5.0tc.txt_14033cdd.txt`

2.  **ID:** `pair-google-gemini-2.5-flash-lite-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-ee57c92d`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_ohqnnblv\\out_pair_google_gemini-2.5-flash-lite_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_ee57c92d.txt`

3.  **ID:** `pair-google-gemini-2.5-flash-lite-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-9ca5ef0a`
    -   **Provider:** `google`, **Model:** `gemini-2.5-flash-lite`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_ohqnnblv\\out_pair_google_gemini-2.5-flash-lite_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Celsius_Bureau.fpf.7.gpt-5.0tc.txt_9ca5ef0a.txt`

**Batch 3 Results:**
1.  **ID:** `pair-google-gemini-2.5-pro-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-e00dac3d`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_jdcg1is9\\out_pair_google_gemini-2.5-pro_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Census_Bureau.fpf.7.gpt-5.0tc.txt_e00dac3d.txt`

2.  **ID:** `pair-google-gemini-2.5-pro-Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-ed271c36`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_jdcg1is9\\out_pair_google_gemini-2.5-pro_Census_Bureau.fpf.4.gemini-2.5-flash-lite.0xw.txt_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_ed271c36.txt`

3.  **ID:** `pair-google-gemini-2.5-pro-Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt-Census_Bureau.fpf.7.gpt-5.0tc.txt-c5c49f54`
    -   **Provider:** `google`, **Model:** `gemini-2.5-pro`
    -   **Result:** **SUCCESS**
    -   **Path:** `C:\\Users\\kjhgf\\AppData\\Local\\Temp\\llm_doc_eval_pair_batch_jdcg1is9\\out_pair_google_gemini-2.5-pro_Census_Bureau.fpf.6.gemini-2.5-pro.rrf.txt_Census_Bureau.fpf.7.gpt-5.0tc.txt_c5c49f54.txt`

## Conclusion

The evaluation run demonstrated strong performance across most tested models for both single and pairwise evaluations. The `google/gemini-2.5-flash-lite` model exhibited an intermittent grounding failure in one single-run instance, suggesting it may not consistently meet strict grounding requirements. Further investigation or adjustments to its usage might be warranted if consistent strict grounding is a critical requirement.
