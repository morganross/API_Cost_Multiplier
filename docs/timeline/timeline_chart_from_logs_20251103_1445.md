# Timeline Chart (from logs) — Latest Run

Source:
- Config: api_cost_multiplier/config.yaml
- Timeline: api_cost_multiplier/logs/acm_session.log (block at 2025-11-03 14:45:52)
- Files: [FILES_WRITTEN] entries around the latest run window in acm_session.log

Legend:
- Column 1: Run from config (type / provider:model)
- Column 2: Timeline line (verbatim from [TIMELINE] block)
- Column 3: Files produced (from [FILES_WRITTEN] during the latest run window). If none, "—".

Note: The latest [TIMELINE] block logged GPT‑R groups only. FPF did run in this session but was excluded due to a late t0 baseline (anchored to an eval [LOG_CFG] at 14:42:39), so its events (14:40:21–14:40:29) fell before t0. MA runs also did not appear for separate reasons; see Update below. Their timeline column is marked "not present in TIMELINE".

| # | Run (from config) | Timeline | Files |
|---|---|---|---|
| 1 | fpf / google:gemini-2.5-flash-lite | not present in TIMELINE | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.fpf.1.gemini-2.5-flash-lite.a3e.txt |
| 2 | gptr / openai:gpt-4.1-mini | not present in TIMELINE | — |
| 3 | gptr / openai:gpt-4.1-nano | 00:00 -- 00:54 (00:53) -- GPT-R standard, openai:gpt-4.1-nano -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gptr.1.gpt-4.1-nano.swc.md |
| 4 | gptr / openai:gpt-4o | 00:01 -- 00:14 (00:13) -- GPT-R standard, openai:gpt-4o -- failure | — |
| 5 | gptr / openai:gpt-5-mini | 00:02 -- 03:14 (03:12) -- GPT-R standard, openai:gpt-5-mini -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.gptr.1.gpt-5-mini.zvq.md |
| 6 | dr / openai:gpt-4o | 00:02 -- 00:43 (00:41) -- GPT-R deep, openai:gpt-4o -- failure | — |
| 7 | dr / openai:gpt-4o-mini | 00:02 -- 00:34 (00:32) -- GPT-R deep, openai:gpt-4o-mini -- failure | — |
| 8 | dr / openai:gpt-5-mini | 00:03 -- 02:51 (02:48) -- GPT-R deep, openai:gpt-5-mini -- success | C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.dr.1.gpt-5-mini.7l0.md |
| 9 | ma / gpt-4.1-mini | not present in TIMELINE | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4.1-mini.oyr.md<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4.1-mini.cyi.docx<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.3.gpt-4.1-mini.e5a.md |
| 10 | ma / gpt-4.1-nano | not present in TIMELINE | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4.1-nano.3au.md<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4.1-nano.3no.docx<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.3.gpt-4.1-nano.5t5.md<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.4.gpt-4.1-nano.njh.docx<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.5.gpt-4.1-nano.gwx.md |
| 11 | ma / gpt-4o-mini | not present in TIMELINE | - C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.1.gpt-4o-mini.b3b.md<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.2.gpt-4o-mini.m9w.docx<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.3.gpt-4o-mini.h0a.md<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.4.gpt-4o-mini.nm5.docx<br>- C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.ma.5.gpt-4o-mini.jz4.md |

## Raw TIMELINE (latest block)
```
00:00 -- 00:54 (00:53) -- GPT-R standard, openai:gpt-4.1-nano -- success
00:01 -- 00:14 (00:13) -- GPT-R standard, openai:gpt-4o -- failure
00:02 -- 03:14 (03:12) -- GPT-R standard, openai:gpt-5-mini -- success
00:02 -- 00:43 (00:41) -- GPT-R deep, openai:gpt-4o -- failure
00:02 -- 00:34 (00:32) -- GPT-R deep, openai:gpt-4o-mini -- failure
00:03 -- 02:51 (02:48) -- GPT-R deep, openai:gpt-5-mini -- success
```

## Notes
- Update: FPF ran and completed in this session but was omitted from the latest [TIMELINE] due to a late t0 baseline taken from an eval [LOG_CFG] at 14:42:39, which filtered out earlier events (14:40:21–14:40:29).
- Evidence (subprocess log: logs/acm_subprocess_20251103_144021.log):
  - 2025-11-03 14:40:21,443 - acm.subproc - INFO - [FPF RUN_START] id=fpf-1-1 kind=rest provider=google model=gemini-2.5-flash-lite
  - 2025-11-03 14:40:29,626 - acm.subproc - INFO - [FPF RUN_COMPLETE] id=fpf-1-1 kind=rest provider=google model=gemini-2.5-flash-lite ok=true
- The “Raw TIMELINE” block reflects only runs starting at or after t0; hence GPT‑R rows appear while FPF does not.
- Actionable: run the timeline script with --no-t0-filter or adjust t0 selection (restrict to acm [LOG_CFG] or compute from earliest event) to include FPF consistently.
- MA rows remain absent for this block due to MA event format/coverage; see timeline_failure_root_cause_report_20251103.md for details.
