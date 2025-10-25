# ACM: Run FPF in two sequential sub-batches (openaidp first), keep overall ACM flow unchanged

Goal
- Make a single, minimal change: within the existing FPF phase, split FPF runs into two sequential sub-batches:
  1) FPF sub-batch A: provider == "openaidp" (if any)
  2) FPF sub-batch B: all remaining FPF providers
- Preserve ACM’s overall phase order and behavior:
  - FPF (now two sub-batches in sequence) → GPT‑R (standard) → GPT‑R (deep) → MA
- Do NOT change FilePromptForge (FPF) internals, do NOT add overlap across phases, and do NOT alter concurrency settings elsewhere.

fpf sub-batch A will not count aginst any limit or quota. acm will not wait for sub-batch a to finish before it starts the next report type. acm wiil start sub-batch a, and without waiting it will launch sub-batch b.


Scope
- Files touched: ../silky/api_cost_multiplier/runner.py only
- No changes to: fpf_runner.py, FPF config, GPT‑R client, MA runner, heartbeat timing, or logging controls.

Behavior before vs after
- Before: One FPF batch (all FPF entries together) that completes before moving to GPT‑R.
- After: Two FPF sub-batches, executed sequentially:
  - Run openaidp-only batch first (if present), then the “rest” batch.
  - After both FPF sub-batches finish, proceed to GPT‑R phases as before.

Implementation steps (concise)
1) Partition FPF entries by provider
- In runner.py where FPF entries are collected per input file:
  ```python
  fpf_openaidp = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() == "openaidp"]
  fpf_rest     = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() != "openaidp"]
  ```

2) Execute the two FPF sub-batches in sequence (await each)
- Replace the single FPF batch call:
  ```python
  if fpf_entries:
      print(f"\n--- Executing FPF batch ({len(fpf_entries)} run templates x {iterations_all} iteration(s)) ---")
      batch_id = f"fpf-batch-{Path(md).stem}"
      _register_run(batch_id)
      try:
          await process_file_fpf_batch(md, config, fpf_entries, iterations_all, keep_temp=keep_temp)
      finally:
          _deregister_run(batch_id)
  ```
- With:
  ```python
  # (A) openaidp-first
  if fpf_openaidp:
      print(f"\n--- Executing FPF openaidp-first batch ({len(fpf_openaidp)} x {iterations_all}) ---")
      batch_id_open = f"fpf-openAidp-{Path(md).stem}"
      _register_run(batch_id_open)
      try:
          await process_file_fpf_batch(md, config, fpf_openaidp, iterations_all, keep_temp=keep_temp)
      finally:
          _deregister_run(batch_id_open)

  # (B) rest (sequentially after openaidp)
  if fpf_rest:
      print(f"\n--- Executing FPF rest batch ({len(fpf_rest)} x {iterations_all}) ---")
      batch_id_rest = f"fpf-rest-{Path(md).stem}"
      _register_run(batch_id_rest)
      try:
          await process_file_fpf_batch(md, config, fpf_rest, iterations_all, keep_temp=keep_temp)
      finally:
          _deregister_run(batch_id_rest)
  ```
- Then continue with existing flow (unchanged):
  - GPT‑R standard group (concurrent if enabled)
  - GPT‑R deep group (concurrent if enabled)
  - MA group (sequential)

3) Heartbeat and logging
- Heartbeat will show a single FPF composite run at a time (first openaidp batch, then rest batch).
- No additional telemetry or log parsing is introduced.

Config/Knobs
- None. This plan does not add or change any configuration; it only changes the FPF phase into two sequential calls.

Testing
- Use a config that includes at least one FPF run with provider "openaidp" and at least one non-openaidp FPF run.
- Run: `python .\generate.py` from C:\dev\silky\api_cost_multiplier
- Validate:
  - The console shows:
    - “Executing FPF openaidp-first batch …”
    - “Executing FPF rest batch …”
    - Then GPT‑R standard, GPT‑R deep, and MA phases as before.
  - Outputs from openaidp sub-batch appear before the rest FPF outputs for the same file.
  - No overlap across phases is introduced.

Risks and mitigations
- Minimal risk: change is limited to splitting FPF phase into two awaited sub-batches.
- If no openaidp runs exist, behavior is effectively identical to today (only the “rest” sub-batch runs).

Rollback
- Revert runner.py to the single FPF batch call.
