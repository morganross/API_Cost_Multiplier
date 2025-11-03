# FPF Run Files Investigation — What happened to those FPF outputs?

Date: 2025-11-02  
Investigator: Cline (ACM)

Objective
- Determine why FPF runs that appear in the latest Timeline block did not show files in column 3 of the chart when scoped to the last run window.
- Identify where the FPF artifacts are, when they were written, and whether timestamp scoping explains the apparent gap.

Last Run Window (from acm_session.log)
- LOG_CFG baseline (t0): 2025-11-02 16:31:45
- Last event in that section: 2025-11-02 16:40:56
- Window used for the chart: [2025-11-02 16:31:45 .. 16:40:56]

Relevant Timeline (16:40:53 block)
- FPF deep, o4-mini-deep-research — success
- FPF rest, o4-mini — success
- FPF rest, gpt-5-nano — success
- Also present in the same block: GPTR (gpt-4.1-nano, gpt-5-mini), DR (gemini-2.5-flash-lite), MA (gpt-4.1-nano)

External Outputs Directory
- Path: C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs

Observed FPF files present in external outputs (basenames)
- 100_ EO 14er & Block.fpf.1.o4-mini-deep-research.9es.txt
- 100_ EO 14er & Block.fpf.1.o4-mini-deep-research.cjm.txt
- 100_ EO 14er & Block.fpf.1.o4-mini-deep-research.we3.txt
- 100_ EO 14er & Block.fpf.1.o4-mini.ka8.txt
- 100_ EO 14er & Block.fpf.1.o4-mini.mer.txt
- 100_ EO 14er & Block.fpf.1.o4-mini.v7g.txt
- 100_ EO 14er & Block.fpf.1.o4-mini.wjt.txt
- 100_ EO 14er & Block.fpf.2.gpt-5-nano.14v.txt
- 100_ EO 14er & Block.fpf.2.gpt-5-nano.37v.txt
- 100_ EO 14er & Block.fpf.2.gpt-5-nano.3x3.txt
- 100_ EO 14er & Block.fpf.2.gpt-5-nano.99h.txt
- 100_ EO 14er & Block.fpf.3.gpt-5-mini.00q.txt
- 100_ EO 14er & Block.fpf.3.gpt-5-mini.3ic.txt
- 100_ EO 14er & Block.fpf.3.gpt-5-mini.jtj.txt
- 100_ EO 14er & Block.fpf.3.gpt-5-mini.wj7.txt
- 100_ EO 14er & Block.gpt-5-mini.fpf-1-1.fpf.response.txt
- 100_ EO 14er & Block.gpt-5-nano.fpf-2-1.fpf.response.txt
- 100_ EO 14er & Block.o4-mini-deep-research.fpf-1-1.fpf.response.txt
- 100_ EO 14er & Block.o4-mini.fpf-3-1.fpf.response.txt

Observed GPTR / DR / MA files for context (same folder)
- GPTR: multiple .gptr.* files (e.g., gpt-4.1-nano.cgl.md, gpt-5-mini.dmq.md, etc.)
- DR:   multiple .dr.* gemini-2.5-flash-lite.*.md
- MA:   multiple .ma.* gpt-4.1-nano.* (.md/.docx)

Key Evidence From Logs
- 2025-11-02 16:31:45 .. 16:40:56: The latest run section.
- 2025-11-02 16:40:53: EVAL_BEST selected an FPF artifact: “100_ EO 14er & Block.fpf.3.gpt-5-mini.3ic.txt” and EVAL_EXPORTS wrote to gptr-eval-process/exports\eval_run_20251103_003622_009b4a10.
- In the chart scoped strictly to [16:31:45 .. 16:40:56], GPTR/DR/MA wrote new files into external outputs; FPF rows showed “—” because no new FPF files were written into external outputs within that exact window.

Initial Conclusion
- The “missing” FPF files in the timeboxed chart are explained by LastWriteTime: FPF artifacts exist in the external outputs directory, but their filesystem timestamps appear to fall outside the last run window used for the chart. In contrast, GPTR/DR/MA wrote new artifacts inside that window, so they appeared.
- Evaluator activity (EVAL_BEST/EVAL_EXPORTS) around 16:40:53 confirms FPF content was produced/selected/used during the last run, but that does not necessarily coincide with creating new external outputs files at that moment.

Open Questions
1) Exactly when (LastWriteTime) were each of the listed FPF files written?
2) Do FPF writes occur earlier (e.g., before the 16:31:45 t0) for the same last run section?
3) Is there any asynchronicity (buffered writes, delayed copy) pushing the filesystem timestamps outside the window?
4) Does the FPF runner log [FILES_WRITTEN] consistently for its outputs (we see many [FILES_WRITTEN] for GPTR/DR/MA, but not for FPF in this window)?
5) Could the EVAL_EXPORT step write only to the repo’s exports folder (not external outputs) at the end of the run, explaining the mismatch?

Verification Plan
- Step 1: Record precise LastWriteTime + size for all FPF artifacts in external outputs.
  - Expected outcome: confirm whether all current FPF files have timestamps outside [16:31:45 .. 16:40:56].
- Step 2: Inspect api_cost_multiplier/logs/fpf_run.log for write events and correlate timestamps.
  - Expected outcome: determine when the FPF artifacts were produced and whether any should have been inside the window.
- Step 3: Review fpf_runner.py and fpf_events.py regarding output write and logging behavior:
  - Ensure [FPF RUN_COMPLETE] and any file write logging are consistently emitted.
  - Confirm whether external outputs writes are synchronous and occur during the same session window.
- Step 4: If needed, enhance logging to include explicit [FILES_WRITTEN] for FPF with basenames and timestamps, mirroring GPTR/DR/MA behavior.
- Step 5: Update the chart pipeline:
  - Option A: keep strict timeboxed external outputs column (accurate per-window I/O).
  - Option B: add a separate “Eval exports (repo)” column to reflect EVAL_EXPORTS artifacts written under gptr-eval-process/exports within the same window.

Next Actions (to execute)
- Enumerate FPF files with LastWriteTime and include them in this doc.
- Cross-check fpf_run.log for correlated write events.
- Propose minimal logging changes if gaps are found.

Appendix: Lines around EVAL at 16:40:53 (from acm_session.log)
- 2025-11-02 16:40:53,441 - eval - INFO - [EVAL_BEST] path=... 100_ EO 14er & Block.fpf.3.gpt-5-mini.3ic.txt
- 2025-11-02 16:40:53,513 - eval - INFO - [EVAL_EXPORTS] dir=gptr-eval-process/exports\eval_run_20251103_003622_009b4a10
- 2025-11-02 16:40:53,995 - acm - INFO - [TIMELINE] (FPF deep/rest lines present)
