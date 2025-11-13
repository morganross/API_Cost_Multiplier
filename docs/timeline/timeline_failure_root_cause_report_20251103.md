# Timeline Omission Root-Cause Report (2025-11-03)

Purpose
- Document exactly why the latest [TIMELINE] block omitted expected runs, with code- and log-backed evidence.
- Enumerate all plausible reasons for omissions.
- Provide concrete remediation steps and verification procedures.

Scope and Inputs Reviewed
- Code:
  - api_cost_multiplier/tools/timeline_from_logs.py
  - api_cost_multiplier/runner.py
- Logs:
  - api_cost_multiplier/logs/acm_session.log
  - The subprocess log invoked in the session: api_cost_multiplier/logs/acm_subprocess_20251103_144021.log (referenced by acm_session.log)

Executive Summary
- The timeline generator did not “fail”; it emitted a partial, valid timeline for the latest batch (14:40–14:45) because:
  1) No FPF batch was executed in that session, so no “[FPF RUN_*]” events existed to include.
  2) MA entries were not included in the latest block because the subprocess log processed by the script did not contain the legacy MA markers the parser expects. Earlier sessions did include such markers, producing MA rows.
- The generator prints lines only for runs with complete start+end+result pairs found in the subprocess log it parses. If an event class (FPF/MA/GPTR) is absent or incomplete there, it will be omitted from the [TIMELINE] block.
- Remediation: standardize MA events in runner.py with unambiguous [MA_START]/[MA_END] pairs and extend the parser to handle them (in addition to legacy lines). No changes are required for FPF parsing.

How Timeline Generation Works Today

1) Where the timeline lines come from
- runner.py finishes a batch and calls a helper that runs the timeline script and appends the output into acm_session.log:

  - runner.py (function _append_timeline_to_acm_log):
    - Launches: python -u tools/timeline_from_logs.py --log-file <subprocLog> --acm-log-file <acm_session.log>
    - On success, prefixes “[TIMELINE]” in acm_session.log and writes each timeline line produced by the script.

2) What events the script recognizes (timeline_from_logs.py)
- Regexes used:
  - FPF:
    - FPF_RUN_START = r"\[FPF RUN_START\] id=… kind=… provider=… model=…"
    - FPF_RUN_COMPLETE = r"\[FPF RUN_COMPLETE\] id=… kind=… provider=… model=… ok=(true|false)"
  - GPT‑R:
    - GPTR_START = r"\[GPTR_START\] pid=(\d+) type=(\S+) model=(\S+)"
    - GPTR_END = r"\[GPTR_END\] pid=(\d+) result=(success|failure)"
  - MA (legacy only, currently):
    - MA_START = r"\[MA run (\d+)\] Starting research for query:"
    - MA_END = r"\[MA run (\d+)\] Multi-agent report \(Markdown\) written to"
- The script:
  - Parses ONLY the subprocess log for events.
  - Uses acm_session.log only to compute a baseline time t0 (from the last “[LOG_CFG]”), not as an event source.
  - Emits a timeline line only for records with start_ts + end_ts + result present.
  - Applies a “t0 filter” (removing events that start before t0, unless --no-t0-filter is used).
  - Prints concise DEBUG metrics to stderr (not in the timeline): totals, MA collisions, etc.

3) Where those events originate
- GPTR_*: Emitted by runner.py around each GPT‑Researcher subprocess launch and completion.
- FPF RUN_*: Emitted by runner.py when FilePromptForge runs are executed in batch. The event stream comes from the FPF batch runner via a combined event handler that writes to the subprocess logger.
- MA legacy lines: Written by runner.py around MA runs with human-readable lines per artifact (not a single canonical [END] per run).

Observed Behavior in This Repository

A) Latest session (14:40–14:45) produced GPT‑R-only [TIMELINE]
- In acm_session.log:
  - 14:45:52 [TIMELINE] block shows only GPT‑R standard/deep rows, no FPF, no MA.
  - Around that time, acm_session.log shows:
    - RUN_START type=ma … (multiple)
    - RUN_START type=gptr … (multiple)
    - Several [FILES_WRITTEN] entries for MA outputs
  - There are no signs that FPF runs were scheduled in this session.
- Conclusion:
  - FPF omission: expected, because no FPF batch ran; therefore no “[FPF RUN_*]” events existed in the subprocess log, and the timeline script had nothing to include for FPF.
  - MA omission: MA activity occurred, but the subprocess log the script processed did not contain the legacy MA markers it recognizes (or did not contain both start and end for a complete record). Earlier sessions (e.g., 10:46) contained those markers, so MA rows appeared there.

B) Earlier session (10:46) produced a complete [TIMELINE] with FPF + MA + GPTR
- acm_session.log shows a [TIMELINE] block that includes:
  - “FPF deep, o4-mini-deep-research”, “FPF rest, …” lines -> confirms FPF events were present and parsed.
  - Multiple “MA, …” lines -> confirms legacy MA markers were present in that session’s subprocess log and parsed into complete run records.
  - GPT‑R standard and deep entries as expected.

Exact Reasons a Class of Runs Can Be Omitted

Reason 1 — The class of runs did not execute in that session (FPF in latest run)
- If no FPF runs are scheduled/executed, no “[FPF RUN_START]/[FPF RUN_COMPLETE]” events will be written to the subprocess log.
- The timeline generator, by design, will not synthesize FPF rows from ACM’s [RUN_START] or [FILES_WRITTEN]; it relies on the richer FPF RUN_* pairs from the subprocess log. Therefore, the FPF section will be omitted.
- Evidence in latest session (14:40–14:45):
  - acm_session.log shows MA and GPT‑R activity but no FPF starts.
  - The [TIMELINE] shows only GPT‑R lines.

Reason 2 — MA legacy markers absent or incomplete in the parsed subprocess log (MA in latest run)
- The script expects legacy MA lines:
  - “[MA run N] Starting research for query: …” (start)
  - “[MA run N] Multi-agent report (Markdown) written to … model=…” (end)
- Omissions occur when:
  - Those lines did not land in the parsed subprocess log (e.g., emitted elsewhere or prior to the logger initialization / rotation boundary).
  - Only end-like lines appear but the script does not have a corresponding start_ts to form a complete record (it requires start+end+result to print).
  - Multiple MA runs share the same logical id (ma-N) and collide (see Reason 3).
- Evidence:
  - Latest session has MA [RUN_START] and MA [FILES_WRITTEN] in acm_session.log, proving MA work happened.
  - The corresponding legacy MA markers were not found/paired in the subprocess log used by the script, so no MA lines were printed.

Reason 3 — MA run-id collisions due to legacy “ma-N” indexing
- The script derives MA run_id as “ma-<N>”, where N comes from the legacy “[MA run N]” logs.
- If multiple MA runs share the same N (e.g., iterations_default=1), their records collide in the multimap. The script is tolerant but can still end with incomplete/overwritten joins if some sessions contain only end markers (no starts) or multiple artifacts collapse timing.
- Symptom:
  - DEBUG counters show ma_collision_instances > 0 and ma_incomplete_runs > 0.
  - Result: fewer complete MA records make it to output.
- Mitigation:
  - Use a unique per-run id and emit standardized [MA_START]/[MA_END] pairs (see Fixes).

Reason 4 — Log source/rotation boundary (events written outside the parsed subprocess log)
- The timeline script parses a single subprocess log file passed by runner.py. If a subset of events (e.g., early MA starts) were written before that log file existed, or to a different instance, the script has no visibility.
- Symptom:
  - acm_session.log shows that work happened (RUN_START or FILES_WRITTEN), but the [TIMELINE] lacks those rows.
- Mitigation:
  - Ensure all event emissions targeted for timeline are guaranteed to go to the same subprocess log used by the script.
  - Emit standardized paired events close in time to run orchestration so they’re consistently captured.

Reason 5 — t0 baseline filtering removed early events
- The script computes t0 (baseline) from the most recent “[LOG_CFG]” in acm_session.log unless --no-t0-filter is set.
- If some events began before t0, they are filtered out (the script warns to stderr if ACM t0 appears much later than the earliest observed start).
- Symptom:
  - DEBUG: “WARN: ACM t0 is later than earliest observed event by >60s”.
  - Output lacks early lines that are present in raw logs.
- Mitigation:
  - Provide the correct ACM log that contains the matching [LOG_CFG].
  - Use --no-t0-filter during diagnosis.
  - Adjust runner to ensure [LOG_CFG] precedes all run events.

Reason 6 — Parser expects complete records (start+end+result)
- The generator intentionally prints only completed runs.
- If an END is logged without a START (or vice versa), or result cannot be determined, no line is printed.
- For MA, the script currently “synthesizes” an approx start if an end arrives for an already-complete record, but it does not synthesize a standalone end-only record when no prior list exists (by design to avoid false positives).
- Mitigation:
  - Emit standardized pairs for MA (and continue with existing FPF/GPTR standards).
  - Optionally add fallbacks that synthesize approximate records from ACM [FILES_WRITTEN] when subprocess events are missing (with a label indicating approximation).

Reason 7 — Miswiring or suppressed event emission
- For FPF: If process_file_fpf_batch is not wired with the combined on_event handler that calls _fpf_event_handler, no “[FPF RUN_*]” entries reach the subprocess log.
- For MA: If legacy markers aren’t emitted (or are emitted only to ACM logger, not the subprocess logger), the parser will not see them.
- Current code review:
  - runner.py wires FPF correctly (combined_event_handler that includes _fpf_event_handler).
  - MA emits legacy “[MA run N] …” lines via SUBPROC_LOGGER in the MA branch, but lacks standardized [MA_START]/[MA_END] pairs.

Evidence Quotes

- Latest session (14:45 block) shows only GPT‑R lines:
  - “2025-11-03 14:45:52,845 - acm - INFO - [TIMELINE]”
  - “00:00 -- 00:54 (00:53) -- GPT-R standard, openai:gpt-4.1-nano -- success”
  - “00:01 -- 00:14 (00:13) -- GPT-R standard, openai:gpt-4o -- failure”
  - “00:02 -- 03:14 (03:12) -- GPT-R standard, openai:gpt-5-mini -- success”
  - “00:02 -- 00:43 (00:41) -- GPT-R deep, openai:gpt-4o -- failure”
  - “00:02 -- 00:34 (00:32) -- GPT-R deep, openai:gpt-4o-mini -- failure”
  - “00:03 -- 02:51 (02:48) -- GPT-R deep, openai:gpt-5-mini -- success”

- Proof MA and files existed in that session (not appearing in [TIMELINE]):
  - “2025-11-03 14:40:21,188 - acm - INFO - [RUN_START] type=ma … model=gpt-4.1-mini …”
  - “2025-11-03 14:41:02,398 - acm - INFO - [FILES_WRITTEN] count=3 paths=[… .ma.1.gpt-4.1-mini …, … .ma.2.gpt-4.1-mini …, … .ma.3.gpt-4.1-mini …]”
  - “2025-11-03 14:42:05,241 - acm - INFO - [FILES_WRITTEN] count=5 paths=[… .ma.1.gpt-4.1-nano …, … .ma.5.gpt-4.1-nano …]”
  - “2025-11-03 14:42:37,225 - acm - INFO - [RUN_START] type=gptr …”
  - No FPF RUN_* events present or implied in this time window.

- Earlier session (10:46 block) includes FPF and MA:
  - “FPF deep, o4-mini-deep-research — success”
  - “FPF rest, gemini-2.5-flash-lite — success”
  - “MA, gpt-4.1-nano — success” (multiple)
  - Confirms parser coverage when events are present in the parsed subprocess log.

Fixes and Enhancements

A) Standardize MA events (runner.py) [Recommended]
- Emit:
  - “[MA_START] id=<unique> model=<provider:model or model>”
  - “[MA_END] id=<unique> model=<…> result=success|failure”
- Use a unique id per MA run (e.g., pm_utils.uid3 or a UUID) to eliminate collisions.
- Keep legacy “[MA run N] …” lines for compatibility.

B) Extend timeline_from_logs.py [Recommended]
- Add regexes for:
  - MA_START2 = r"\[MA_START\]\s+id=(\S+)\s+model=(\S+)"
  - MA_END2 = r"\[MA_END\]\s+id=(\S+)\s+model=(\S+)\s+result=(success|failure)"
- Parse these alongside legacy MA markers.

C) Optional fallbacks
- Option 1: If subprocess log MA/FPF events are missing, synthesize “approximate” timeline rows from ACM’s [RUN_START]/[FILES_WRITTEN] (explicitly labeled “approx”). This trades purity for completeness.
- Option 2: Emit minimal ACM-level “[RUN_START] type=fpf …” for FPF batches to aid a cross-check (the timeline would still rely on RUN_* pairs from the subproc log).

D) Operational safeguards
- Ensure the subprocess logger is initialized before any MA/FPF/GPTR starts to avoid rotation-boundary losses.
- Consider enabling --no-t0-filter during troubleshooting to rule out baseline filtering effects.

Verification Steps

1) Regenerate timeline for latest session (manual)
- Run the timeline script explicitly on the known files:

  - Example (Windows PowerShell, one command per line):
    python -u api_cost_multiplier/tools/timeline_from_logs.py --log-file api_cost_multiplier/logs/acm_subprocess_20251103_144021.log --acm-log-file api_cost_multiplier/logs/acm_session.log

- Observe stderr for DEBUG metrics (instances_total, complete, ma_collision_instances, ma_incomplete_runs, t0 info).
- Confirm that output contains only GPT‑R lines, matching the [TIMELINE] already appended.

2) After implementing MA standardization
- Run a short batch including MA and verify:
  - acm_subprocess_*.log contains [MA_START]/[MA_END] pairs with unique ids.
  - The generated [TIMELINE] now consistently includes MA rows in the latest block.

3) Optional: Add FPF to the run
- Ensure runs[] includes type: fpf entries.
- Verify “[FPF RUN_START]/[FPF RUN_COMPLETE]” appear in the subprocess log.
- Confirm timeline shows “FPF rest”/“FPF deep” lines, as in the 10:46 block.

Appendix: Reference Code Paths

- runner.py
  - _append_timeline_to_acm_log invokes the timeline script and appends a [TIMELINE] block on success.
  - FPF batch wiring:
    - process_file_fpf_batch uses run_filepromptforge_batch with on_event and calls _fpf_event_handler, which writes “[FPF RUN_*]” to SUBPROC_LOGGER.
  - MA legacy logging:
    - In process_file_run (rtype == "ma"), MA artifacts are logged with legacy “[MA run N] … written to … model=…”. There is no current standardized [MA_START]/[MA_END] emission.

- tools/timeline_from_logs.py
  - Recognizes FPF_RUN_START/FPF_RUN_COMPLETE, GPTR_START/GPTR_END, and legacy MA markers.
  - Outputs only complete records (start+end+result) in the exact approved format:
    - start_mm:ss -- end_mm:ss (dur_mm:ss) -- ReportType, Model -- Result
  - Uses acm_session.log solely to compute t0 (via “[LOG_CFG]”), not for events.

Bottom Line
- FPF was omitted because no FPF runs were executed in the latest session.
- MA was omitted because the parser did not find complete MA event pairs in the subprocess log it processed (legacy marker fragility and/or log boundary).
- Implementing standardized MA event pairs and parsing them removes this fragility and makes the timeline consistently complete across sessions.
