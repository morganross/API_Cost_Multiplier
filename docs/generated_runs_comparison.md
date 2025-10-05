# Generated Runs Comparison
Date: 2025-10-04 19:35 (local)

Summary
This document compares the configured runs in `api_cost_multiplier/config.yaml` with the files actually written to `api_cost_multiplier/test/mdoutputs` after running `python api_cost_multiplier/generate.py`. One input file was processed (config uses `one_file_only: true`).

Notes about filename mapping
- Output filenames follow the scheme: `<base>.<type>.<run-index>.<model_label>.<uid>.<ext>`
- `model_label` is created by `pm_utils.sanitize_model_for_filename`:
  - Provider prefix (e.g. `openai:`) is removed
  - Lowercased; non-alphanumeric (except `.` `_` `-`) replaced with `-`
  - Repeated `-` collapsed; result trimmed/truncated to 60 chars
- Types produced: `fpf` (.txt), `gptr` (.md), `dr` (.md), `ma` (.md/.docx depending on run)

Per-run comparison (config order)
1) fpf — google : gemini-2.5-flash
   - Found: `commerce/Census Bureau.fpf.1.gemini-2.5-flash.h1o.txt`

2) fpf — google : gemini-2.5-flash-lite
   - Found: `commerce/Census Bureau.fpf.1.gemini-2.5-flash-lite.3gf.txt`

3) fpf — google : gemini-2.5-pro
   - Found: `commerce/Census Bureau.fpf.1.gemini-2.5-pro.9jf.txt`

4) fpf — openai : gpt-5
   - Found: `commerce/Census Bureau.fpf.1.gpt-5.ih6.txt`

5) fpf — openai : gpt-5-mini
   - Found: `commerce/Census Bureau.fpf.1.gpt-5-mini.gkk.txt`

6) fpf — openai : gpt-5-nano
   - Found: `commerce/Census Bureau.fpf.1.gpt-5-nano.7h0.txt`

7) fpf — openai : o3
   - Found: `commerce/Census Bureau.fpf.1.o3.0hh.txt`

8) fpf — openai : o4-mini
   - Found: `commerce/Census Bureau.fpf.1.o4-mini.pso.txt`

9) fpf — openaidp : o3-deep-research
   - Missing (run failed). Logs show: "Background DP task failed" — no output saved.

10) fpf — openaidp : o4-mini-deep-research
    - Found: `commerce/Census Bureau.fpf.1.o4-mini-deep-research.oti.txt`

11) gptr — google_genai : gemini-2.5-flash
    - Found: `commerce/Census Bureau.gptr.1.gemini-2.5-flash.6vq.md`

12) gptr — google_genai : gemini-2.5-flash-lite
    - Found: `commerce/Census Bureau.gptr.1.gemini-2.5-flash-lite.1rw.md`

13) gptr — google_genai : gemini-2.5-pro
    - Found: `commerce/Census Bureau.gptr.1.gemini-2.5-pro.itf.md`

14) gptr — openai : gpt-4-turbo-2024-04-09
    - Missing (no gptr file found matching `gpt-4-turbo-2024-04-09`)

15) gptr — openai : gpt-4.1
    - Found: `commerce/Census Bureau.gptr.1.gpt-4.1.6lt.md`

16) gptr — openai : gpt-4.1-mini
    - Found: `commerce/Census Bureau.gptr.1.gpt-4.1-mini.syx.md`

17) gptr — openai : gpt-4.1-nano
    - Found: `commerce/Census Bureau.gptr.1.gpt-4.1-nano.9vd.md`

18) gptr — openai : gpt-4o
    - Found: `commerce/Census Bureau.gptr.1.gpt-4o.fxa.md`

19) gptr — openai : gpt-4o-mini
    - Found: `commerce/Census Bureau.gptr.1.gpt-4o-mini.m11.md`

20) gptr — openai : gpt-5
    - Found: `commerce/Census Bureau.gptr.1.gpt-5.fb6.md`

21) gptr — openai : gpt-5-mini
    - Found: `commerce/Census Bureau.gptr.1.gpt-5-mini.wyc.md`

22) gptr — openai : o1-mini
    - Missing (no gptr file found with model label `o1-mini`)

23) gptr — openai : o3-mini
    - Found: `commerce/Census Bureau.gptr.1.o3-mini.jyw.md`

24) gptr — openai : o4-mini
    - Found: `commerce/Census Bureau.gptr.1.o4-mini.4v4.md`

25) dr — google_genai : gemini-2.5-flash
    - Found: `commerce/Census Bureau.dr.1.gemini-2.5-flash.34t.md`

26) dr — google_genai : gemini-2.5-flash-lite
    - Found: `commerce/Census Bureau.dr.1.gemini-2.5-flash-lite.wsn.md`

27) dr — google_genai : gemini-2.5-pro
    - Found: `commerce/Census Bureau.dr.1.gemini-2.5-pro.acp.md`

28) dr — openai : gpt-4-turbo-2024-04-09
    - Missing (no dr file found matching `gpt-4-turbo-2024-04-09`)

29) dr — openai : gpt-4.1
    - Found: `commerce/Census Bureau.dr.1.gpt-4.1.0n9.md`

30) dr — openai : gpt-4.1-mini
    - Found: `commerce/Census Bureau.dr.1.gpt-4.1-mini.ptc.md`

31) dr — openai : gpt-4.1-nano
    - Found: `commerce/Census Bureau.dr.1.gpt-4.1-nano.dbw.md`

32) dr — openai : gpt-4o
    - Found: `commerce/Census Bureau.dr.1.gpt-4o.xqh.md`

33) dr — openai : gpt-4o-mini
    - Found: `commerce/Census Bureau.dr.1.gpt-4o-mini.61r.md`

34) dr — openai : gpt-5
    - Found: `commerce/Census Bureau.dr.1.gpt-5.dqp.md`

35) dr — openai : gpt-5-mini
    - Found: `commerce/Census Bureau.dr.1.gpt-5-mini.yxn.md`

36) dr — openai : o3
    - Found: `commerce/Census Bureau.dr.1.o3.oks.md`

37) dr — openai : o3-mini
    - Found: `commerce/Census Bureau.dr.1.o3-mini.yu5.md`

38) dr — openai : o4-mini
    - Found: `commerce/Census Bureau.dr.1.o4-mini.vug.md`

39) ma — gpt-4.1
    - Found: multiple `ma` outputs containing `gpt-4.1` (examples: `commerce/Census Bureau.ma.1.gpt-4.1.1kh.md`, plus ma.*)

40) ma — gpt-4.1-mini
    - Found: `commerce/Census Bureau.ma.1.gpt-4.1-mini.igv.md` and others

41) ma — gpt-4.1-nano
    - Found: `commerce/Census Bureau.ma.1.gpt-4.1-nano.h0s.docx` and others

42) ma — gpt-4o
    - Found: `commerce/Census Bureau.ma.1.gpt-4o.ffd.md` and others

43) ma — gpt-4o-mini
    - Found: `commerce/Census Bureau.ma.1.gpt-4o-mini.u89.docx` and others

44) ma — o4-mini
    - Found: `commerce/Census Bureau.ma.1.o4-mini.q2o.md` and others

Missing / Failed runs (summary)
- FPF (openaidp) — o3-deep-research: Failed; logs indicate "Background DP task failed". No output saved.
- GPTR (openai) — gpt-4-turbo-2024-04-09: No corresponding output file found for this model in `gptr` or `dr` outputs.
- GPTR (openai) — o1-mini: No corresponding gptr output found.
- DR (openai) — gpt-4-turbo-2024-04-09: No corresponding dr output found.

Recommended follow-ups
- Inspect the per-run logs for:
  - The openaidp FPF failure: inspect the FilePromptForge per-run JSON log (console printed paths under `FilePromptForge/logs/*.json`) to see the DP response failure details.
  - The gptr/dr runs for `gpt-4-turbo-2024-04-09` and `o1-mini` to confirm whether the runner mapped those model identifiers to other canonical names or skipped them.
- Optionally re-run only the missing runs (safer) to reproduce and capture detailed logs.

If you want, I can:
- Generate a CSV mapping config runs to found filenames and save it under `api_cost_multiplier/docs/` (or elsewhere).
- Open the specific per-run log JSON for the failed openaidp run and paste the error section here.
- Attempt to re-run only the missing runs and capture their output.

Task progress
- [x] Analyze requirements
- [x] Inspect generate.py
- [x] Run generate.py
- [x] Read config.yaml runs
- [x] Inspect pm_utils for filename sanitization
- [x] List files produced under api_cost_multiplier/test/mdoutputs
- [x] Compare outputs to config runs (documented above)
- [ ] Follow-up actions (log inspection / targeted re-runs) — waiting on direction
