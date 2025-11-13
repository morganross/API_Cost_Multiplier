# Timeline Chart (from logs) - Run started 2025-11-04 21:31:16

Source:
- Config: api_cost_multiplier/config.yaml
- Timeline: 
  - api_cost_multiplier/logs/acm_subprocess_20251104_213116.log
  - api_cost_multiplier/logs/acm_session.log
- Files: C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs (window: 2025-11-04 21:31:16–21:36:25)

Legend:
- Column 1: Run from config (type / provider:model)
- Column 2: Timeline line (verbatim from timeline tool)
- Column 3: Files produced during this session window. If none, "—".
- Column 4: Potential fix (only for failures or observations)

| # | Run (from config) | Timeline | Files | Potential fix |
|---|---|---|---|---|
| 1 | fpf / google:gemini-2.5-flash-lite | 00:00 -- 00:02 (00:02) -- FPF rest, gemini-2.5-flash-lite -- success | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.fpf.1.gemini-2.5-flash-lite.b22.txt (0 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gemini-2.5-flash-lite.fpf-1-1.fpf.response.txt (0 KB) | No change needed (validation passed). |
| 2 | gptr / openai:gpt-4.1-mini | — | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gptr.1.gpt-4.1-mini.fui.md (9 KB) | Timeline event not captured; verify [GPTR_START]/[GPTR_END] logging. Output present, otherwise OK. |
| 3 | gptr / openai:gpt-4.1-nano | 02:06 -- 02:54 (00:48) -- GPT-R standard, openai:gpt-4.1-nano -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gptr.1.gpt-4.1-nano.gtl.md (10 KB) | No change needed. |
| 4 | gptr / openai:gpt-4o | 02:07 -- 02:45 (00:37) -- GPT-R standard, openai:gpt-4o -- failure | — | Enforce token cap and parameter mapping: map max_tokens → max_completion_tokens; cap gpt-4o ≤ 16384; retry with alternate param on 400. |
| 5 | gptr / openai:gpt-5-mini | 02:08 -- 04:41 (02:33) -- GPT-R standard, openai:gpt-5-mini -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gptr.1.gpt-5-mini.r7t.md (12 KB) | File size > 4KB. |
| 6 | dr / openai:gpt-4o | 02:08 -- 02:45 (00:37) -- GPT-R deep, openai:gpt-4o -- failure | — | Address scraping/network failures (e.g., Tavily 4xx, scraper not found). Add retry/backoff; normalize types to avoid split() errors. No files produced. |
| 7 | dr / openai:gpt-4o-mini | 02:09 -- 02:45 (00:36) -- GPT-R deep, openai:gpt-4o-mini -- failure | — | Same as Run 6: improve scraping reliability and input normalization. No files produced. |
| 8 | dr / openai:gpt-5-mini | 02:45 -- 05:08 (02:23) -- GPT-R deep, openai:gpt-5-mini -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.dr.1.gpt-5-mini.a6a.md (11 KB) | File size > 4KB. |
| 9 | ma / gpt-4.1-mini | 00:00 -- 00:23 (00:23) -- MA, gpt-4.1-mini -- success | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4.1-mini.xjv.md (3 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4.1-mini.y3x.md (3 KB) | Produced 2 files. Both files <= 4KB. |
| 10 | ma / gpt-4.1-nano | 00:23 -- 01:38 (01:15) -- MA, gpt-4.1-nano -- success | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4.1-nano.t5t.md (3 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4.1-nano.rpm.md (4 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.3.gpt-4.1-nano.7mf.md (4 KB) | Produced 3 files. All files <= 4KB. |
| 11 | ma / gpt-4o-mini | 01:38 -- 02:04 (00:27) -- MA, gpt-4o-mini -- success | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4o-mini.en4.md (4 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4o-mini.dt0.md (3 KB)<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.3.gpt-4o-mini.5rt.md (3 KB) | Produced 3 files. All files <= 4KB. |

## Raw TIMELINE (verbatim)
```
00:00 -- 00:23 (00:23) -- MA, gpt-4.1-mini -- success
00:00 -- 00:23 (00:23) -- MA, gpt-4.1-mini -- success
00:00 -- 00:02 (00:02) -- FPF rest, gemini-2.5-flash-lite -- success
00:22 -- 00:23 (00:01) -- MA, gpt-4.1-mini -- success
00:23 -- 01:38 (01:15) -- MA, gpt-4.1-nano -- success
00:23 -- 01:38 (01:15) -- MA, gpt-4.1-nano -- success
01:37 -- 01:38 (00:01) -- MA, gpt-4.1-nano -- success
01:37 -- 01:38 (00:01) -- MA, gpt-4.1-nano -- success
01:38 -- 02:04 (00:27) -- MA, gpt-4o-mini -- success
01:38 -- 02:04 (00:27) -- MA, gpt-4o-mini -- success
02:03 -- 02:04 (00:01) -- MA, gpt-4o-mini -- success
02:03 -- 02:04 (00:01) -- MA, gpt-4o-mini -- success
02:06 -- 02:54 (00:48) -- GPT-R standard, openai:gpt-4.1-nano -- success
02:07 -- 02:45 (00:37) -- GPT-R standard, openai:gpt-4o -- failure
02:08 -- 04:41 (02:33) -- GPT-R standard, openai:gpt-5-mini -- success
02:08 -- 02:45 (00:37) -- GPT-R deep, openai:gpt-4o -- failure
02:09 -- 02:45 (00:36) -- GPT-R deep, openai:gpt-4o-mini -- failure
02:45 -- 05:08 (02:23) -- GPT-R deep, openai:gpt-5-mini -- success
```

## Notes
- t0 was adjusted to the earliest observed start to avoid over-filtering, per tool output.
- FPF succeeded (validation signals present). Two FPF artifacts were created but are 0 KB in this window.
- GPT‑R standard gpt‑4o failed (token parameter/length issues likely). Apply token-cap mapping (max_completion_tokens) with per-model caps.
- GPT‑R deep for 4o/4o‑mini failed; logs on prior runs indicate scraping/Tavily instability. Add retry/backoff and type normalization to avoid split() errors.
- MA produced multiple artifacts per model in runs-only mode (expected with current saver). If desired, align runs-only saver with one_file_only to reduce duplicates.
