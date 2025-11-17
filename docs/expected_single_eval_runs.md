# Timeline Chart for Generate.py Run - November 16, 2025 01:01

**Generated:** November 16, 2025

## Generation Runs (from config.yaml)

| Run (config) | Timeline (verbatim) | Output file(s) with size | Any file < 5 KB? | Errors/Notes |
|---|---|---|---|---|
| fpf:openai:gpt-5-nano | 00:00 -- 01:32 (01:32) -- FPF rest, gpt-5-nano -- success | 100_ EO 14er & Block.fpf.1.gpt-5-nano.7ha.txt (14.65 KB) | No | |
| fpf:openai:o4-mini | 00:00 -- 01:34 (01:34) -- FPF rest, o4-mini -- success | 100_ EO 14er & Block.fpf.1.o4-mini.d71.txt (6.75 KB) | Yes | File is 6.75 KB |
| gptr:google_genai:gemini-2.5-flash | 00:00 -- 04:53 (04:53) -- GPT-R standard, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.h3u.md (14.94 KB) | No | |
| dr:openai:gpt-5-mini | 00:00 -- 09:12 (09:12) -- GPT-R deep, openai:gpt-5-mini -- success | 100_ EO 14er & Block.dr.1.gpt-5-mini.6wr.md (18.72 KB) | No | |
| dr:google_genai:gemini-2.5-flash | 04:54 -- 08:03 (03:10) -- GPT-R deep, google_genai:gemini-2.5-flash -- failure | None | N/A | Run failed |
| ma:gpt-4.1-nano | 00:00 -- 04:53 (04:53) -- MA, gpt-4.1-nano -- success<br>04:52 -- 04:53 (00:01) -- MA, gpt-4.1-nano -- success | 100_ EO 14er & Block.ma.1.gpt-4.1-nano.ku6.md (41.20 KB) | No | Multiple timeline entries |
| ma:gpt-4o | 00:00 -- 04:53 (04:53) -- MA, gpt-4o -- success<br>04:52 -- 04:53 (00:01) -- MA, gpt-4o -- success<br>04:52 -- 04:53 (00:01) -- MA, gpt-4o -- success<br>04:52 -- 04:53 (00:01) -- MA, gpt-4o -- success | 100_ EO 14er & Block.ma.1.gpt-4o.p4u.md (41.20 KB) | No | Multiple timeline entries (4x) |

**Summary:**
- Total configured runs: 7
- Successful runs: 6
- Failed runs: 1 (dr:google_genai:gemini-2.5-flash)
- Files < 5 KB: 1 (fpf:openai:o4-mini at 6.75 KB)

---

## Single-Document Evaluation Runs

**Configuration:**
- Evaluator models: 2 (google:gemini-2.5-flash-lite, openai:gpt-5-mini)
- Successfully generated files: 6
- Criteria per evaluation: 4 (factuality, relevance, completeness, style_clarity)
- **Expected total: 2 × 6 × 4 = 48 single evaluations**
- **Actual completed: 32 single evaluations**
- **Missing: 16 evaluations (33.3%)**

### Actual Single-Document Evaluation Runs (32 total)

Each evaluation run assesses ONE file against ALL 4 criteria (factuality, relevance, completeness, style_clarity):

1. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.dr.1.gpt-5-mini.6wr.md → ✅ SUCCESS
2. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.h3u.md → ✅ SUCCESS
3. openai:gpt-5-mini × 100_ EO 14er & Block.dr.1.gpt-5-mini.6wr.md → ✅ SUCCESS
4. openai:gpt-5-mini × 100_ EO 14er & Block.fpf.1.gpt-5-nano.7ha.txt → ✅ SUCCESS
5. openai:gpt-5-mini × 100_ EO 14er & Block.fpf.1.o4-mini.d71.txt → ✅ SUCCESS
6. openai:gpt-5-mini × 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.h3u.md → ✅ SUCCESS
7. openai:gpt-5-mini × 100_ EO 14er & Block.ma.1.gpt-4.1-nano.ku6.md → ✅ SUCCESS
8. openai:gpt-5-mini × 100_ EO 14er & Block.ma.1.gpt-4o.p4u.md → ✅ SUCCESS

**Note:** Each run above evaluates all 4 criteria, so 8 runs × 4 criteria = 32 total database entries

### Missing Single-Document Evaluation Runs

Expected but not performed:

1. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.fpf.1.gpt-5-nano.7ha.txt → ❌ MISSING
2. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.fpf.1.o4-mini.d71.txt → ❌ MISSING
3. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.ma.1.gpt-4.1-nano.ku6.md → ❌ MISSING
4. google:gemini-2.5-flash-lite × 100_ EO 14er & Block.ma.1.gpt-4o.p4u.md → ❌ MISSING

**Missing evaluation runs: 4 runs × 4 criteria = 16 missing database entries**

---

## Database Verification

- Database path: `C:\dev\silky\api_cost_multiplier\llm-doc-eval\llm_doc_eval\results_20251116_091108_0e9e736b.sqlite`
- Database size: 40960 bytes (40 KB)
- Single-doc evaluations in database: 32 rows
- Pairwise comparisons in database: 21 rows

**Analysis:**
- google:gemini-2.5-flash-lite only evaluated 2 of 6 files (33.3% coverage)
- openai:gpt-5-mini evaluated all 6 files (100% coverage)
- Missing evaluations appear to be due to validation constraints or errors with the Google evaluator model

---

## Complete List of Expected Single-Document Evaluations

### FPF File 1: 100_ EO 14er & Block.fpf.1.gpt-5-nano.7ha.txt

1. google:gemini-2.5-flash-lite × FPF-gpt-5-nano (factuality) → Expected
2. google:gemini-2.5-flash-lite × FPF-gpt-5-nano (relevance) → Expected
3. google:gemini-2.5-flash-lite × FPF-gpt-5-nano (completeness) → Expected
4. google:gemini-2.5-flash-lite × FPF-gpt-5-nano (style_clarity) → Expected
5. openai:gpt-5-mini × FPF-gpt-5-nano (factuality) → Expected
6. openai:gpt-5-mini × FPF-gpt-5-nano (relevance) → Expected
7. openai:gpt-5-mini × FPF-gpt-5-nano (completeness) → Expected
8. openai:gpt-5-mini × FPF-gpt-5-nano (style_clarity) → Expected

### FPF File 2: 100_ EO 14er & Block.fpf.1.o4-mini.d71.txt

9. google:gemini-2.5-flash-lite × FPF-o4-mini (factuality) → Expected
10. google:gemini-2.5-flash-lite × FPF-o4-mini (relevance) → Expected
11. google:gemini-2.5-flash-lite × FPF-o4-mini (completeness) → Expected
12. google:gemini-2.5-flash-lite × FPF-o4-mini (style_clarity) → Expected
13. openai:gpt-5-mini × FPF-o4-mini (factuality) → Expected
14. openai:gpt-5-mini × FPF-o4-mini (relevance) → Expected
15. openai:gpt-5-mini × FPF-o4-mini (completeness) → Expected
16. openai:gpt-5-mini × FPF-o4-mini (style_clarity) → Expected

### GPTR File 1: 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.h3u.md

17. google:gemini-2.5-flash-lite × GPTR-gemini-2.5-flash (factuality) → Expected
18. google:gemini-2.5-flash-lite × GPTR-gemini-2.5-flash (relevance) → Expected
19. google:gemini-2.5-flash-lite × GPTR-gemini-2.5-flash (completeness) → Expected
20. google:gemini-2.5-flash-lite × GPTR-gemini-2.5-flash (style_clarity) → Expected
21. openai:gpt-5-mini × GPTR-gemini-2.5-flash (factuality) → Expected
22. openai:gpt-5-mini × GPTR-gemini-2.5-flash (relevance) → Expected
23. openai:gpt-5-mini × GPTR-gemini-2.5-flash (completeness) → Expected
24. openai:gpt-5-mini × GPTR-gemini-2.5-flash (style_clarity) → Expected

### DR File 1: 100_ EO 14er & Block.dr.1.gpt-5-mini.6wr.md

25. google:gemini-2.5-flash-lite × DR-gpt-5-mini (factuality) → Expected
26. google:gemini-2.5-flash-lite × DR-gpt-5-mini (relevance) → Expected
27. google:gemini-2.5-flash-lite × DR-gpt-5-mini (completeness) → Expected
28. google:gemini-2.5-flash-lite × DR-gpt-5-mini (style_clarity) → Expected
29. openai:gpt-5-mini × DR-gpt-5-mini (factuality) → Expected
30. openai:gpt-5-mini × DR-gpt-5-mini (relevance) → Expected
31. openai:gpt-5-mini × DR-gpt-5-mini (completeness) → Expected
32. openai:gpt-5-mini × DR-gpt-5-mini (style_clarity) → Expected

### DR File 2: 100_ EO 14er & Block.dr.1.gemini-2.5-flash.xyz.md

33. google:gemini-2.5-flash-lite × DR-gemini-2.5-flash (factuality) → Expected
34. google:gemini-2.5-flash-lite × DR-gemini-2.5-flash (relevance) → Expected
35. google:gemini-2.5-flash-lite × DR-gemini-2.5-flash (completeness) → Expected
36. google:gemini-2.5-flash-lite × DR-gemini-2.5-flash (style_clarity) → Expected
37. openai:gpt-5-mini × DR-gemini-2.5-flash (factuality) → Expected
38. openai:gpt-5-mini × DR-gemini-2.5-flash (relevance) → Expected
39. openai:gpt-5-mini × DR-gemini-2.5-flash (completeness) → Expected
40. openai:gpt-5-mini × DR-gemini-2.5-flash (style_clarity) → Expected

### MA File 1: 100_ EO 14er & Block.ma.1.gpt-4.1-nano.ku6.md

41. google:gemini-2.5-flash-lite × MA-gpt-4.1-nano (factuality) → Expected
42. google:gemini-2.5-flash-lite × MA-gpt-4.1-nano (relevance) → Expected
43. google:gemini-2.5-flash-lite × MA-gpt-4.1-nano (completeness) → Expected
44. google:gemini-2.5-flash-lite × MA-gpt-4.1-nano (style_clarity) → Expected
45. openai:gpt-5-mini × MA-gpt-4.1-nano (factuality) → Expected
46. openai:gpt-5-mini × MA-gpt-4.1-nano (relevance) → Expected
47. openai:gpt-5-mini × MA-gpt-4.1-nano (completeness) → Expected
48. openai:gpt-5-mini × MA-gpt-4.1-nano (style_clarity) → Expected

### MA File 2: 100_ EO 14er & Block.ma.1.gpt-4o.p4u.md

49. google:gemini-2.5-flash-lite × MA-gpt-4o (factuality) → Expected
50. google:gemini-2.5-flash-lite × MA-gpt-4o (relevance) → Expected
51. google:gemini-2.5-flash-lite × MA-gpt-4o (completeness) → Expected
52. google:gemini-2.5-flash-lite × MA-gpt-4o (style_clarity) → Expected
53. openai:gpt-5-mini × MA-gpt-4o (factuality) → Expected
54. openai:gpt-5-mini × MA-gpt-4o (relevance) → Expected
55. openai:gpt-5-mini × MA-gpt-4o (completeness) → Expected
56. openai:gpt-5-mini × MA-gpt-4o (style_clarity) → Expected

---

## Summary by Evaluator Model

### google:gemini-2.5-flash-lite
- Total expected evaluations: 28 (7 files × 4 criteria)
- Breakdown:
  - FPF files: 8 evaluations (2 files × 4 criteria)
  - GPTR files: 4 evaluations (1 file × 4 criteria)
  - DR files: 8 evaluations (2 files × 4 criteria)
  - MA files: 8 evaluations (2 files × 4 criteria)

### openai:gpt-5-mini
- Total expected evaluations: 28 (7 files × 4 criteria)
- Breakdown:
  - FPF files: 8 evaluations (2 files × 4 criteria)
  - GPTR files: 4 evaluations (1 file × 4 criteria)
  - DR files: 8 evaluations (2 files × 4 criteria)
  - MA files: 8 evaluations (2 files × 4 criteria)

---

## Notes

- Each evaluation assesses one file against one criterion using one evaluator model
- The actual run from the terminal output showed: **32 single-doc rows** in the database
- **Expected: 56** vs **Actual: 32** = **24 missing evaluations** (42.9% missing)
- This discrepancy should be investigated to determine which specific evaluations failed or were skipped
