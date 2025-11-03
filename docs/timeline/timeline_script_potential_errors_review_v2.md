# Timeline Script Potential Errors Review (v2, updated)

Scope: Parser-only review. No producer changes, no execution. Focused on `api_cost_multiplier/tools/timeline_from_logs.py` behavior, assumptions, and failure modes when used from `generate.py`.

Executive summary:
- The parser is close, but several edge cases can silently drop events or mis-attribute models.
- Two concrete bugs stand out: (1) `--file-filter` is currently a no-op; (2) several regexes are case-sensitive and may miss valid events (e.g., `ok=True` or `result=Success`).
- Additional risks: MA model extraction misses common characters, overzealous model overwriting, and fragile deep/REST classification heuristics.

High-impact issues and recommendations:

1) --file-filter is a no-op (defect)
- Symptom:
  - In `produce_timeline`, this block:
    ```
    if file_filter and file_filter not in line:
        # non-strict: do not continue here because many lines lack file hints
        pass
    ```
    does not filter anything (pass = do nothing). The CLI option is advertised but has no effect.
- Impact:
  - Users expecting to restrict parsing to specific files/runs will get full, unfiltered output.
- Recommendation (parser-only change):
  - Honor the filter by skipping non-matching lines:
    ```
    if file_filter and file_filter not in line:
        continue
    ```
  - If you want a “non-strict” mode, document it explicitly with a flag instead of silently ignoring.

2) Case-sensitive regexes drop valid events (defect)
- Details:
  - `FPF_RUN_COMPLETE` requires `ok=(true|false)` (lowercase only).
  - `GPTR_END` requires `result=(success|failure)` (lowercase only).
  - Producers may emit `True/False`, `SUCCESS/FAILURE`, etc.
- Impact:
  - RUN_COMPLETE or GPTR_END lines with varied casing won’t match; completions or results will be missing.
- Recommendation (parser-only change):
  - Compile these patterns with `re.IGNORECASE` or expand alternation:
    ```
    FPF_RUN_COMPLETE = re.compile(r"... ok=(true|false)", re.IGNORECASE)
    GPTR_END = re.compile(r"\[GPTR_END\]\s+pid=(\d+)\s+result=(success|failure)", re.IGNORECASE)
    ```
  - You already normalize with `.lower()` after matching; the match itself must succeed first.

3) MA model extraction regex is too restrictive (quality/accuracy risk)
- Details:
  - Current extraction: `model=([a-zA-Z0-9\-\._:]+)`
  - Real-world model identifiers often include `/`, `+`, and vendor prefixes (e.g., `openrouter:openai/gpt-4o-mini`, `google/gemini-1.5-pro`).
- Impact:
  - Model may be truncated or not captured at all, leading to “unknown” or incorrect attributions.
- Recommendation (parser-only change):
  - Expand the capture class:
    ```
    model_match = re.search(r"model=([a-zA-Z0-9_\-\.:\+/]+)", line)
    ```
  - Consider quoting support if producers ever emit model values with spaces (i.e., `model="openai/gpt-4o"`).

4) Model/report_type overwrite strategy can hide better data (accuracy risk)
- Details:
  - `_upsert_single` always overwrites `report_type` and `model` when provided later.
  - This fixed one FPF discrepancy class but can regress others, e.g., overwriting a specific model with “unknown”.
- Impact:
  - Later, lower-quality data can replace earlier, higher-quality data.
- Recommendation (parser-only logic change):
  - Only replace when the new value is more specific:
    - Treat `"unknown"` as lower quality.
    - Example:
      ```
      def better(a, b):
          return (a and a.lower() != "unknown") and (not b or b.lower() == "unknown")

      if report_type and (better(report_type, rec.report_type) or rec.report_type == "unknown"):
          rec.report_type = report_type
      if model and (better(model, rec.model) or rec.model == "unknown"):
          rec.model = model
      ```
  - Alternatively, preserve first non-unknown, unless an explicit “final” event supplies a different value.

5) Deep/REST classification heuristics are brittle (classification risk)
- Details:
  - `fpf_kind_to_report_type(kind, provider)` returns “FPF deep” if `kind == "deep"` or `provider == "openaidp"`.
- Impact:
  - Provider-based inference is a brittle proxy; if providers change names (e.g., `openai`, `openrouter`, `google`) or contract changes, this can misclassify.
- Recommendation:
  - Prefer `kind` as the authoritative signal (deep vs rest). Use provider only as a tie-breaker if historical data proves it is reliable.
  - Consider accepting `kind` variations (`"deep"`, `"dr"`, etc.) with a normalization map.

6) MA success is assumed; failures are invisible (observability gap)
- Details:
  - MA runs only get `rec.result = "success"` in `MA_END`. There is no MA failure path (no `MA_ERROR` or timeout).
- Impact:
  - Failed MA runs are completely omitted (never complete), which might be desirable for the final timeline but hides useful diagnostics.
- Recommendation:
  - Keep the final output as-is, but emit stderr diagnostics when an `MA_START` appears without a subsequent `MA_END` before EOF:
    - Example metric: “DEBUG: ma_incomplete_runs=N (possible failures or interruptions)”.

7) Timestamp prefix is strict; minor variations break parsing (robustness risk)
- Details:
  - `TS_PREFIX` expects `YYYY-MM-DD HH:MM:SS,mmm` exactly.
  - Some loggers use `.` instead of `,` for milliseconds; some include timezone offsets.
- Impact:
  - Lines with valid events may be skipped if TS doesn’t match exactly, which kills ordering and t0 calculations.
- Recommendation:
  - Expand `TS_PREFIX` to tolerate `,` or `.` and optional timezone (keep simple if needed):
    ```
    TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.](\d{3})\b")
    ```
  - If timezone appears, either strip it or support a separate optional group.

8) t0 baseline drift risk when --acm-log-file mismatches session (filtering risk)
- Details:
  - If `--acm-log-file` points to an unrelated session, the derived `run_start_ts` may be too late and filter out legitimate early events.
  - You do have a fallback if filtering removes everything, but partial over-filtering won’t be detected.
- Impact:
  - Early valid runs can be silently dropped.
- Recommendation:
  - Emit a warning if `acm_log_path` is provided and the earliest `complete.start_ts` is significantly earlier than `run_start_ts` (e.g., >60s). Example:
    ```
    if run_start_ts and earliest and (run_start_ts - earliest > timedelta(seconds=60)):
        print("WARN: acm t0 is later than earliest event; consider --no-t0-filter or correct --acm-log-file", file=sys.stderr)
    ```

9) PID reuse across long logs (identity collision risk)
- Details:
  - GPTR run_id = `gptr-{pid}`. If the log spans multiple sessions (no `t0` filtering) or processes reuse PIDs over time, collisions can happen.
- Impact:
  - Unrelated runs may be merged into a single logical record.
- Recommendation:
  - Encourage use of `--acm-log-file` to compute session t0 or provide a parser option to require `LOG_CFG` presence.
  - Alternatively, incorporate an iso-date prefix into GPTR run_id (parser-side only) when `no_t0_filter=True`.

10) Concurrency and out-of-order lines (parsing fidelity risk)
- Details:
  - Concurrent producers can interleave lines; if logger flush order diverges slightly from the event order, near-simultaneous records may sort oddly.
- Impact:
  - Off-by-one second ordering differences can cause cosmetic timeline ordering changes or wrong pairing if timestamps are identical.
- Recommendation:
  - Keep sort by `start_ts`, but consider stabilizing with a secondary key (e.g., end_ts, then run_id) to make ordering deterministic:
    ```
    filtered.sort(key=lambda r: (r.start_ts, r.end_ts, r.run_id))
    ```

11) Diagnostics could be more actionable (operability)
- Details:
  - Current stderr metrics are helpful but could include counts per category:
    - totals per type (FPF/GPT-R/MA), incomplete by type, unmatched pattern counters.
- Benefit:
  - Faster root cause detection when timelines look sparse.

12) Minor: unused imports and cleanup
- `Tuple` is imported but unused. Not harmful but can be cleaned.

Concrete parser-only changes (safe, incremental):

- Implement filter behavior:
  - Replace `pass` with `continue` for `--file-filter`.
- Add `re.IGNORECASE` to `FPF_RUN_COMPLETE` and `GPTR_END` patterns.
- Expand MA model regex to allow `/` and `+`.
- Add guarded overwrite in `_upsert_single` so “unknown” doesn’t stomp real values.
- Add stderr warning when `--acm-log-file` t0 is later than earliest event.
- Optional robustness: widen `TS_PREFIX` to allow `.` and optional timezone hints.
- Optional determinism: stable multi-key sort.

Why these matter for the original failure modes:
- Run-id collisions (MA) are already mitigated by multimap. These updates reduce silent event loss (case sensitivity, timestamp strictness), prevent model mis-attribution (regex and guarded overwrite), and align CLI behavior with user expectation (`--file-filter`).

Non-goals:
- No execution. No producer changes. No behavior change to the approved output format beyond improving parsing fidelity and diagnostics.

Suggested validation (manual, no execution here):
- Prepare a small set of anonymized sample lines covering:
  - True/False casing variants for FPF/GPTR.
  - MA_END lines with models containing `/` and `+`.
  - Timestamps using `.` separator.
  - Interleaved FPF/GPT-R/MA sequences to confirm stable ordering.
- Verify that events are now recognized and models are attributed without being overwritten by “unknown”.
