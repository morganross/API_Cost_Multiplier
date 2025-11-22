# Greenbag6 Timeline (2025-11-19 20:41)

## Timeline Chart

| Run (config) | Timeline (verbatim) | Output file(s) with size | Any file < 5 KB? | Errors/Notes |
| :--- | :--- | :--- | :--- | :--- |
| dr:google_genai:gemini-2.5-flash | 09:27 -- 12:40 (03:13) -- GPT-R deep, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.dr.1.gemini-2.5-flash.xmh.md (11.1 KB) | No | |
| dr:openai:gpt-5-mini | 00:00 -- 14:21 (14:21) -- GPT-R deep, openai:gpt-5-mini -- success | 100_ EO 14er & Block.dr.1.gpt-5-mini.3n4.md (21.46 KB) | No | |
| fpf:openai:gpt-5-nano | 00:00 -- 02:20 (02:20) -- FPF rest, gpt-5-nano -- success | 100_ EO 14er & Block.fpf.1.gpt-5-nano.x0r.txt (14.32 KB) | No | |
| fpf:openai:o4-mini | 00:00 -- 01:26 (01:26) -- FPF rest, o4-mini -- success | 100_ EO 14er & Block.fpf.1.o4-mini.cri.txt (7.21 KB) | No | |
| gptr:google_genai:gemini-2.5-flash | 00:00 -- 09:27 (09:27) -- GPT-R standard, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.9w7.md (14.9 KB) | No | |
| ma:gpt-4.1-nano | 00:00 -- 09:27 (09:27) -- MA, gpt-4.1-nano -- success<br>00:00 -- 09:27 (09:27) -- MA, gpt-4.1-nano -- success<br>09:26 -- 09:27 (00:01) -- MA, gpt-4.1-nano -- success | 100_ EO 14er & Block.ma.1.gpt-4.1-nano.lc0.md (40.07 KB) | No | Multiple timeline entries observed. |
| ma:gpt-4o | 00:00 -- 09:27 (09:27) -- MA, gpt-4o -- success<br>09:26 -- 09:27 (00:01) -- MA, gpt-4o -- success<br>09:26 -- 09:27 (00:01) -- MA, gpt-4o -- success<br>09:26 -- 09:27 (00:01) -- MA, gpt-4o -- success | 100_ EO 14er & Block.ma.1.gpt-4o.gxa.md (40.07 KB) | No | Multiple timeline entries observed. |

## Expected vs Actual Run Lists

### Generation Runs List

1. FPF openai:gpt-5-nano → ✅ SUCCESS (100_ EO 14er & Block.fpf.1.gpt-5-nano.x0r.txt, 14.32 KB, 20:43:55)
2. FPF openai:o4-mini → ✅ SUCCESS (100_ EO 14er & Block.fpf.1.o4-mini.cri.txt, 7.21 KB, 20:43:01)
3. GPTR google_genai:gemini-2.5-flash → ✅ SUCCESS (100_ EO 14er & Block.gptr.1.gemini-2.5-flash.9w7.md, 14.9 KB, 20:51:02)
4. DR openai:gpt-5-mini → ✅ SUCCESS (100_ EO 14er & Block.dr.1.gpt-5-mini.3n4.md, 21.46 KB, 20:55:56)
5. DR google_genai:gemini-2.5-flash → ✅ SUCCESS (100_ EO 14er & Block.dr.1.gemini-2.5-flash.xmh.md, 11.1 KB, 20:54:15)
6. MA gpt-4.1-nano → ✅ SUCCESS (100_ EO 14er & Block.ma.1.gpt-4.1-nano.lc0.md, 40.07 KB, 20:51:02)
7. MA gpt-4o → ✅ SUCCESS (100_ EO 14er & Block.ma.1.gpt-4o.gxa.md, 40.07 KB, 20:51:02)

### Single-Document Evaluation List

**Total Count:** 4 models × 7 files = 28 evaluations

1. google:gemini-2.5-flash-lite × DR-Gemini (dr.1.gemini-2.5-flash.xmh.md) → ✅ SUCCESS
2. google:gemini-2.5-flash-lite × DR-GPT5 (dr.1.gpt-5-mini.3n4.md) → ❌ MISSING (missing from results)
3. google:gemini-2.5-flash-lite × FPF-GPT5 (fpf.1.gpt-5-nano.x0r.txt) → ❌ MISSING (missing from results)
4. google:gemini-2.5-flash-lite × FPF-O4 (fpf.1.o4-mini.cri.txt) → ❌ MISSING (missing from results)
5. google:gemini-2.5-flash-lite × GPTR-Gemini (gptr.1.gemini-2.5-flash.9w7.md) → ❌ MISSING (missing from results)
6. google:gemini-2.5-flash-lite × MA-Nano (ma.1.gpt-4.1-nano.lc0.md) → ❌ MISSING (missing from results)
7. google:gemini-2.5-flash-lite × MA-4o (ma.1.gpt-4o.gxa.md) → ✅ SUCCESS
8. google:gemini-2.5-flash × DR-Gemini (dr.1.gemini-2.5-flash.xmh.md) → ✅ SUCCESS
9. google:gemini-2.5-flash × DR-GPT5 (dr.1.gpt-5-mini.3n4.md) → ✅ SUCCESS
10. google:gemini-2.5-flash × FPF-GPT5 (fpf.1.gpt-5-nano.x0r.txt) → ✅ SUCCESS
11. google:gemini-2.5-flash × FPF-O4 (fpf.1.o4-mini.cri.txt) → ✅ SUCCESS
12. google:gemini-2.5-flash × GPTR-Gemini (gptr.1.gemini-2.5-flash.9w7.md) → ✅ SUCCESS
13. google:gemini-2.5-flash × MA-Nano (ma.1.gpt-4.1-nano.lc0.md) → ✅ SUCCESS
14. google:gemini-2.5-flash × MA-4o (ma.1.gpt-4o.gxa.md) → ✅ SUCCESS
15. openai:gpt-5-mini × DR-Gemini (dr.1.gemini-2.5-flash.xmh.md) → ✅ SUCCESS
16. openai:gpt-5-mini × DR-GPT5 (dr.1.gpt-5-mini.3n4.md) → ✅ SUCCESS
17. openai:gpt-5-mini × FPF-GPT5 (fpf.1.gpt-5-nano.x0r.txt) → ✅ SUCCESS
18. openai:gpt-5-mini × FPF-O4 (fpf.1.o4-mini.cri.txt) → ✅ SUCCESS
19. openai:gpt-5-mini × GPTR-Gemini (gptr.1.gemini-2.5-flash.9w7.md) → ✅ SUCCESS
20. openai:gpt-5-mini × MA-Nano (ma.1.gpt-4.1-nano.lc0.md) → ✅ SUCCESS
21. openai:gpt-5-mini × MA-4o (ma.1.gpt-4o.gxa.md) → ✅ SUCCESS
22. openai:o4-mini × DR-Gemini (dr.1.gemini-2.5-flash.xmh.md) → ✅ SUCCESS
23. openai:o4-mini × DR-GPT5 (dr.1.gpt-5-mini.3n4.md) → ✅ SUCCESS
24. openai:o4-mini × FPF-GPT5 (fpf.1.gpt-5-nano.x0r.txt) → ✅ SUCCESS
25. openai:o4-mini × FPF-O4 (fpf.1.o4-mini.cri.txt) → ✅ SUCCESS
26. openai:o4-mini × GPTR-Gemini (gptr.1.gemini-2.5-flash.9w7.md) → ✅ SUCCESS
27. openai:o4-mini × MA-Nano (ma.1.gpt-4.1-nano.lc0.md) → ✅ SUCCESS
28. openai:o4-mini × MA-4o (ma.1.gpt-4o.gxa.md) → ✅ SUCCESS

### Pairwise Evaluation List (Summary)

**Total Count:** 4 models × 21 pairs = 84 evaluations

*   **google:gemini-2.5-flash-lite:** ❌ FAILED for most pairs (similar to single-doc results).
*   **google:gemini-2.5-flash:** ✅ SUCCESS for all pairs.
*   **openai:gpt-5-mini:** ✅ SUCCESS for all pairs.
*   **openai:o4-mini:** ✅ SUCCESS for all pairs.

**Note:** `gemini-2.5-flash-lite` continues to show instability/failures in evaluation tasks, likely due to grounding/citation validation checks or API timeouts.
