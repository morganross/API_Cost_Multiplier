# Timeline Chart: November 14, 2025 22:27 Run

**Run Start:** 22:27:47  
**Run End:** 22:40:24  
**Total Duration:** ~12 minutes 37 seconds  
**Config:** one_file_only: true (single input file)

---

| Run (config) | Timeline (verbatim) | Output file(s) with size | Any file < 5 KB? | Errors/Notes |
|---|---|---|---|---|
| fpf:google:gemini-2.5-flash | 00:00 -- 00:24 (00:23) -- FPF rest, gemini-2.5-flash -- success | 100_ EO 14er & Block.fpf.1.gemini-2.5-flash.3l2.txt (10.1 KB) | No | File written at 22:35:17 |
| fpf:google:gemini-2.5-flash-lite | 00:00 -- 00:03 (00:02) -- FPF rest, gemini-2.5-flash-lite -- failure | None | No | Timeline shows failure; no output expected |
| fpf:openai:gpt-5-mini | 00:00 -- 04:45 (04:45) -- FPF rest, gpt-5-mini -- success | 100_ EO 14er & Block.fpf.4.gpt-5-mini.c9l.txt (19.2 KB) | No | File written at 22:35:17 |
| fpf:openai:gpt-5-nano | 00:00 -- 01:44 (01:43) -- FPF rest, gpt-5-nano -- success | 100_ EO 14er & Block.fpf.3.gpt-5-nano.3xy.txt (15.5 KB) | No | File written at 22:35:17 |
| fpf:openai:o4-mini | 00:00 -- 01:00 (01:00) -- FPF rest, o4-mini -- success | 100_ EO 14er & Block.fpf.2.o4-mini.k3a.txt (7.1 KB) | No | File written at 22:35:17 |
| gptr:google_genai:gemini-2.5-flash | 00:00 -- 07:30 (07:30) -- GPT-R standard, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.3ov.md (11.3 KB) | No | File written at 22:35:17 |
| gptr:google_genai:gemini-2.5-flash-lite | 12:29 -- 12:37 (00:08) -- GPT-R standard, google_genai:gpt-4.1-nano -- failure | None | No | Timeline shows "gpt-4.1-nano" model but config says "gemini-2.5-flash-lite". Log shows [FILES_WRITTEN] count=0 at 22:40:24. Run started at 22:40:16 |
| ma:gpt-4o | 00:00 -- 07:30 (07:30) -- MA, gpt-4o -- success<br>00:00 -- 07:30 (07:30) -- MA, gpt-4o -- success<br>07:29 -- 07:30 (00:01) -- MA, gpt-4o -- success | 100_ EO 14er & Block.ma.1.gpt-4o.e1r.md (38.9 KB) | No | Multiple duplicate timeline entries (3 total). File written at 22:35:17 |
| ma:gpt-4o-mini | 00:00 -- 07:30 (07:30) -- MA, gpt-4o-mini -- success<br>07:29 -- 07:30 (00:01) -- MA, gpt-4o-mini -- success<br>07:29 -- 07:30 (00:01) -- MA, gpt-4o-mini -- success<br>07:29 -- 07:30 (00:01) -- MA, gpt-4o-mini -- success | 100_ EO 14er & Block.ma.1.gpt-4o-mini.o84.md (38.9 KB) | No | Multiple duplicate timeline entries (4 total). File written at 22:35:17 |
| ma:o4-mini | 00:00 -- 12:29 (12:29) -- MA, o4-mini -- success<br>12:28 -- 12:29 (00:01) -- MA, o4-mini -- success<br>12:28 -- 12:29 (00:01) -- MA, o4-mini -- success<br>12:28 -- 12:29 (00:01) -- MA, o4-mini -- success | 100_ EO 14er & Block.ma.1.o4-mini.8cb.md (36.5 KB) | No | Multiple duplicate timeline entries (4 total). File written at 22:40:16 (last file of run) |

---

## Summary

**Total Configured Runs:** 10 (5 FPF + 2 GPTR + 3 MA)  
**Successful Timeline Entries:** 9 success + 2 failure = 11 timeline entries (duplicates counted separately)  
**Files Generated:** 8 files  
- 4 FPF files (10.1 KB, 19.2 KB, 15.5 KB, 7.1 KB) - written at 22:35:17
- 1 GPTR file (11.3 KB) - written at 22:35:17
- 3 MA files (38.9 KB, 38.9 KB, 36.5 KB) - written at 22:35:17 (2) and 22:40:16 (1)

**Files Under 5 KB:** 0

**Success Rate:** 8/10 runs generated output (80%)

---

## Anomalies Detected

1. **~~FPF Batch Complete Failure~~** ✅ RESOLVED:
   - Initial error: Looked for .md files but FPF outputs .txt files
   - Reality: 4/5 FPF runs succeeded (80% success rate)
   - All 4 successful FPF runs wrote .txt files at 22:35:17
   - 1 expected validation failure (gemini-2.5-flash-lite)

2. **Duplicate Timeline Entries:**
   - MA runs have 3-4 duplicate timeline entries each
   - Suggests timeline logging bug or multiple concurrent processes logging same event
   - All duplicates show identical timestamps and durations

3. **GPTR Model Mismatch:**
   - Config: `gptr:google_genai:gemini-2.5-flash-lite`
   - Timeline: Shows as "gpt-4.1-nano"
   - Likely timeline logging error or model resolution issue

4. **Evaluation Auto-Triggered:**
   - Log shows evaluation started at 22:35:18
   - Evaluated 4 FPF .txt files generated at 22:35:17 (THIS run)
   - Confirms threshold gate fix working (≥1 file triggers eval)
   - Cost: $0.222348
   - All newly generated FPF files successfully evaluated

---

**Chart Generated:** 2025-11-14 23:25  
**Source Logs:** acm_session.log (22:27:47 session)  
**Config:** config.yaml (10 runs configured)
