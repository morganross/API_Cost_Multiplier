# Timeline Implementation Plan 2.0 (Timeline-Only Fixes)

Date: November 1, 2025
Owner: Cline AI Assistant

Summary
This plan focuses exclusively on fixing the timeline generator so it reliably reports all runs it can infer from existing logs, without changing any producers (MA, GPTR, FPF, Tavily, etc.). It keeps backward compatibility with the existing “approved output format” and adds collision handling, safer baseline (t0) selection, and visibility/metrics to make omissions diagnosable. No upstream failure or configuration fixes are included.

Scope
- In scope:
  - api_cost_multiplier/tools/timeline_from_logs.py only.
  - Parser-side robustness: MA collision handling, better t0 logic, debug metrics, safer model extraction.
  - Optional, opt-in printing of partial runs (flag-gated) while keeping default behavior identical.

- Out of scope (explicitly not part of this plan):
  - Tavily or scraper configuration changes.
  - GPTR/FPF/MA producer changes, including logging formats or unique IDs.
  - Runner orchestration, waiting strategies, or session identifiers.
  - Any changes to non-timeline components.

Files to be edited
- api_cost_multiplier/tools/timeline_from_logs.py
  - Purpose: Parse acm_subprocess_*.log (and optionally acm_session.log) and print a compact, human-readable timeline. Currently requires exact start+end+result and drops anything incomplete or before the calculated baseline, with no diagnostics for exclusions.

Goals and changes (timeline_from_logs.py)
1) Robust MA run collision handling (no producer changes required)
- Problem: Multiple MA runs share the same run index (e.g., [MA run 1] for every model), causing the parser to overwrite previous MA records keyed by “ma-1”.
- Fix: Introduce multi-record storage per base ID and auto-suffix new records when we detect subsequent MA runs for the same index.

Design:
- Instead of runs: Dict[str, RunRecord], use runs_by_id: Dict[str, List[RunRecord]].
- For MA:
  - On MA_START for index N:
    - If no list exists: create runs_by_id["ma-N"] = [RunRecord(...)].
    - If list exists:
      - If the last record in the list already has both start and end (i.e., a completed run), append a new RunRecord for the new MA run (“collision -> new instance”).
      - Otherwise, if the last record is in-progress (has start but no end), keep using that active record for MA_END.
  - On MA_END for index N:
    - Complete the most recent active record in runs_by_id["ma-N"], leaving earlier records intact.

- For output:
  - Flatten runs_by_id into a final complete list (default behavior still only prints complete runs with exact format).
  - This preserves all MA runs even when the index repeats.

Code snippet (illustrative diff; exact placement near existing MA parsing):
```python
# Before: single dict keyed by run_id
# runs: Dict[str, RunRecord] = {}

# After: multimap keyed by base run_id
runs_by_id: Dict[str, List[RunRecord]] = {}

def _get_list(run_id: str) -> List[RunRecord]:
    lst = runs_by_id.get(run_id)
    if lst is None:
        lst = []
        runs_by_id[run_id] = lst
    return lst

# MA_START
m = MA_START.search(line)
if m and ts:
    run_index = m.group(1)
    run_id = f"ma-{run_index}"
    lst = _get_list(run_id)
    if lst and lst[-1].start_ts and lst[-1].end_ts:
        # last is complete -> start a new instance for this repeated index
        lst.append(RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts))
    elif not lst:
        lst.append(RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts))
    else:
        # last exists and is in-progress: set start if missing (defensive)
        if lst[-1].start_ts is None:
            lst[-1].start_ts = ts
    continue

# MA_END
m = MA_END.search(line)
if m and ts:
    run_index = m.group(1)
    run_id = f"ma-{run_index}"
    lst = _get_list(run_id)
    if lst:
        rec = lst[-1]
        rec.end_ts = ts
        model_match = re.search(r"model=([a-zA-Z0-9\-\._:]+)", line)
        if model_match:
            rec.model = model_match.group(1)
        rec.result = "success"
    continue
```

2) Preserve dict behavior for FPF/GPTR (no producer changes)
- FPF and GPTR are already uniquely identifiable (id / pid). Keep their existing handling (single record per id), but refactor aggregation code to unify on runs_by_id so the finalize step treats all components uniformly.

Illustrative adaptation:
```python
def _upsert_single(rid: str, **kwargs):
    lst = runs_by_id.get(rid)
    if not lst:
        lst = [RunRecord(run_id=rid, **kwargs)]
        runs_by_id[rid] = lst
    else:
        rec = lst[-1]
        # update fields defensively
        for k, v in kwargs.items():
            if getattr(rec, k) in (None, "unknown"):
                setattr(rec, k, v)
    return runs_by_id[rid][-1]
```

3) Safer baseline (t0) selection and filtering
- Problem: Using the last [LOG_CFG] from acm_session.log as t0 can exclude valid runs.
- Fix: When acm_session.log is provided, still parse it, but:
  - If resulting filtering would drop all complete runs, fall back to the earliest start among complete records.
  - Add an opt-in flag --no-t0-filter to disable baseline filtering entirely.
  - Print a debug line (stderr) with chosen t0 and number of runs filtered by t0.

Illustrative snippet:
```python
# After building 'complete' list
if not complete:
    return []

chosen_t0 = run_start_ts
if not chosen_t0:
    chosen_t0 = min(r.start_ts for r in complete if r.start_ts)

filtered = [r for r in complete if r.start_ts and r.start_ts >= chosen_t0]
if not filtered:
    # fallback: don't over-filter; choose earliest observed start
    chosen_t0 = min(r.start_ts for r in complete if r.start_ts)
    filtered = [r for r in complete if r.start_ts and r.start_ts >= chosen_t0]

print(f"DEBUG: t0={chosen_t0.isoformat()} filtered_out={len(complete)-len(filtered)}", file=sys.stderr)
complete = filtered
```

Add argparse flag:
```python
parser.add_argument("--no-t0-filter", action="store_true", help="Disable baseline filtering by t0.")
# ...
if args.no_t0_filter:
    # skip t0 filtering entirely
    pass
```

4) Diagnostics and metrics (stderr only; does not change approved timeline line format)
- Add debug/metrics to stderr so the runner can capture them if needed without polluting the appended [TIMELINE] block:
  - Parsed events count by component.
  - Total runs parsed vs. complete vs. excluded (and reasons where determinable: missing end, missing result).
  - Collision counts per run_id base (e.g., “ma-1”: 4 instances).
  - Chosen t0 and number filtered by t0.

Illustrative emit:
```python
print(f"DEBUG: counts: total_ids={sum(len(v) for v in runs_by_id.values())} "
      f"ma_collisions={sum(max(0, len(v)-1) for k,v in runs_by_id.items() if k.startswith('ma-'))}",
      file=sys.stderr)
```

5) Optional, flag-gated support for partials (default off to preserve exact output format)
- Keep default behavior: print only complete records with exact approved format.
- Add --include-partials to optionally print “in-progress” (start only) and “unknown/failure-inferred” records. These would require a clearly distinct format or a safe approximation; to avoid breaking downstream consumers, this plan only introduces the flag and internal categorization. By default, the flag is not used by runner, so behavior is unchanged.

Example categorization (internals only for now):
- start only -> state=in_progress
- end only (rare) -> state=unknown
- error-only patterns (future extension) -> state=failure_inferred

6) Minor robustness improvements
- Model extraction (MA): keep current regex but tolerate absence; do not crash.
- Printing order: continue sorting by start_ts; if equal, stable ordering by insertion.

Acceptance criteria
- MA runs with repeated “[MA run 1]” sequences produce multiple distinct timeline rows instead of a single overwritten row, without any changes to producer logs.
- With acm_session.log provided, t0 filtering no longer drops all valid rows due to a misplaced baseline; fallback logic ensures some output when complete runs exist.
- When no complete runs exist, behavior is unchanged: empty output, plus stderr metrics indicating reasons (e.g., zero complete, counts per reason).
- No changes to approved line format for complete runs:
  - start_mm:ss -- end_mm:ss (dur_mm:ss) -- ReportType, Model -- Result
- stderr contains at least:
  - total parsed run instances
  - total complete vs. excluded
  - MA collision instances
  - chosen t0 and number filtered by t0

Example end-state code excerpt (collapsed)
```python
# New container
runs_by_id: Dict[str, List[RunRecord]] = {}

# parse ...
# (FPF, GPTR use _upsert_single; MA uses multi-record logic above)

# finalize complete list (default behavior)
complete: List[RunRecord] = []
for rid, lst in runs_by_id.items():
    for rec in lst:
        if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
            complete.append(rec)

# debug metrics
total_instances = sum(len(v) for v in runs_by_id.values())
ma_collisions = sum(max(0, len(v) - 1) for k, v in runs_by_id.items() if k.startswith("ma-"))
print(f"DEBUG: instances={total_instances} complete={len(complete)} ma_collisions={ma_collisions}", file=sys.stderr)

# choose t0 safely (with fallback)
# ... (as shown above)

# print exact format for complete entries
for r in complete:
    # unchanged formatting
    print(f"{start_s} -- {end_s} ({dur_s}) -- {r.report_type}, {r.model} -- {r.result}")
```

How this fixes the observed failures (without touching producers)
- Previously only the last MA run survived overwriting; now each repeated “[MA run N]” creates a distinct record instance, so all MA runs appear.
- If acm_session.log baseline pointed too late, we previously filtered out early-valid runs; the safer t0 selection/fallback retains valid rows.
- We still exclude incomplete runs by default (to preserve format), but metrics now reveal what and why, enabling targeted remediation later without guessing.

Backward compatibility
- Default output remains identical for complete runs. No breaking changes to the approved format.
- New flags (--no-t0-filter, --include-partials) are opt-in.
- All diagnostics go to stderr, not stdout.

Implementation notes
- Keep the RunRecord dataclass as-is for compatibility; no schema changes needed.
- Internal aggregation structures change, but printed rows stay the same.

Testing plan
- Create synthetic acm_subprocess logs with:
  - Multiple “[MA run 1]” start/end pairs interleaved for various models -> expect multiple rows.
  - Early runs relative to a late [LOG_CFG] -> expect rows after fallback t0 logic.
  - Mixed complete/incomplete cases -> expect unchanged printed rows plus metrics indicating exclusions.
- Verify stderr metrics report collisions and counts.

Differences from the old plan(s)
- Old timeline-oriented docs (e.g., timeline_error_analysis.md and the broader narrative) suggested fixing producers (unique MA IDs, always log end events) alongside timeline parsing. This plan 2.0 deliberately avoids producer changes.
- Old approaches risked changing run behavior or external APIs (e.g., Tavily, scraper defaults). This plan is timeline-only: no configuration changes, no retries, no token limits, no network adjustments.
- This plan adds robust consumer-side collision handling and safe t0 fallback with explicit metrics, restoring visibility while preserving the exact line format for complete runs and keeping compatibility.

Appendix: What each edited file does
- api_cost_multiplier/tools/timeline_from_logs.py
  - Role: Offline/endpoint script that reads acm_subprocess_*.log (and optionally acm_session.log) and prints a compact human-readable timeline of runs with durations and results.
  - Why we edit here: It is the sole timeline consumer. All robustness needed to avoid overwriting MA runs and over-filtering by t0 belongs here. Diagnostics/metrics also belong here to surface exclusions without changing any producers.

End of Plan
