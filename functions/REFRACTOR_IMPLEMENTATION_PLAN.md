Refactor implementation plan — process_markdown/generate.py
Date: 2025-08-26
Author: Cline (assistant)

Goal
----
Break generate.py into well-scoped modules placed under process_markdown/functions/ to improve readability, testability, and maintainability. Conform to the user's requirement that the Multi-Agent runner module be named exactly "MA_runner.py" (capital "MA"). Produce a clear, incremental migration plan to avoid regressions.

High-level module layout (all new files go in process_markdown/functions/)
----
1. pm_utils.py
   - Purpose: small generic helpers and utilities used across runners and output logic.
   - To move / implement:
     - start_heartbeat(label: str = "process_markdown_noeval", interval: float = 3.0) -> threading.Event
     - ensure_temp_dir(path: str) -> str
     - sanitize_model_for_filename(model: str | None) -> str
     - normalize_report_entries(results: Iterable) -> list[tuple]
   - Additional helper (optional):
     - load_env_file(path: str) -> dict[str, str]  (if you want env parsing reused)

2. MA_runner.py  (file name required by user)
   - Purpose: All logic related to invoking the Multi-Agent CLI subprocess and streaming its output.
   - To move / implement:
     - MA_CLI_PATH constant (recompute relative to this file)
     - TEMP_BASE constant (or import from pm_utils if shared)
     - async run_multi_agent_once(query_text: str, output_folder: str, run_index: int) -> str
     - async run_multi_agent_runs(query_text: str, num_runs: int = 3) -> list[tuple]
   - Behavior to preserve:
     - Write query to temporary file
     - Build environment variables by reading .env files (gpt-researcher and MA CLI)
     - Launch subprocess using sys.executable
     - Stream stdout and stderr to the controlling process
     - Return final .md path (or raise errors as currently)
   - Rationale: subprocess and env handling are a separate domain and should be isolated for mocking in tests.

3. gptr_runner.py
   - Purpose: Adapter/wrapper around process_markdown.EXAMPLE_fucntions.gpt_researcher_client
   - To move / implement:
     - async run_gpt_researcher_runs(query_prompt: str, num_runs: int = 3, report_type: str = "research_report") -> list[tuple|str]
   - Rationale: Keeps external client integration separated from orchestration.

4. output_manager.py
   - Purpose: All functions that name and save generated reports into the mirrored output folder.
   - To move / implement:
     - save_generated_reports(input_md_path: str, input_base_dir: str, output_base_dir: str, generated_paths: dict) -> List[str]
   - Rationale: Isolate filesystem side effects and naming rules. Easier to unit test.

5. processor.py (optional but recommended)
   - Purpose: High-level orchestrator for processing a single input file: reading markdown + instructions, calling MA and GPT-R runners, invoking output_manager, and cleanup.
   - To move / implement:
     - async process_file(md_file_path: str, config: dict) -> None
   - Rationale: generate.py becomes small and only responsible for program bootstrap and dispatching to processor.process_file.

6. __init__.py
   - Add a module __init__ so the new package folder imports cleanly if needed.

Public API for each new module (concise)
----
- pm_utils.start_heartbeat(label, interval) -> threading.Event
- pm_utils.ensure_temp_dir(path) -> str
- pm_utils.sanitize_model_for_filename(model) -> str
- pm_utils.normalize_report_entries(results) -> list[(abs_path, model)]
- MA_runner.run_multi_agent_once(query_text, output_folder, run_index) -> str (async)
- MA_runner.run_multi_agent_runs(query_text, num_runs=3) -> list[(abs_path, model)] (async)
- gptr_runner.run_gpt_researcher_runs(query_prompt, num_runs=3, report_type="research_report") -> list[(abs_path, model)]
- output_manager.save_generated_reports(input_md_path, input_base_dir, output_base_dir, generated_paths) -> list[str]
- processor.process_file(md_file_path, config) -> None (async)

Migration strategy (safe, incremental)
----
1) Create new modules under process_markdown/functions/ with the functions ported exactly as they exist in generate.py. At first, leave the original implementations in generate.py untouched (duplicate functions). This lets generate.py import from the new modules but keeps a fallback until fully validated.

2) Update generate.py to import the functions from the new modules and call the imported functions instead of local versions. Example changes:
   - Before:
       from process_markdown.EXAMPLE_fucntions import config_parser, file_manager, gpt_researcher_client
       ...
       def run_multi_agent_runs(...):
           ...
   - After:
       from process_markdown.EXAMPLE_fucntions import config_parser, file_manager, gpt_researcher_client
       from process_markdown.functions import pm_utils, MA_runner, gptr_runner, output_manager, processor
       ...
       # remove or alias local names:
       run_multi_agent_runs = MA_runner.run_multi_agent_runs

3) Run smoke checks:
   - importable check: python -c "import process_markdown.generate"
   - run minimal pipeline on a single test markdown (preferably in test/ directory)
   - ensure that no NameError/ImportError occurs

4) Once everything works, remove duplicate code from generate.py and rely solely on the new modules.

5) Add small unit tests (recommended) for the pure logic modules:
   - sanitize_model_for_filename (edge cases)
   - normalize_report_entries
   - save_generated_reports (using tempfile and sample files)
   - For MA_runner and gptr_runner, create integration-style tests that stub subprocess and gpt_researcher_client respectively (use monkeypatch or unittest.mock).

6) Final manual run: point config to a test input folder and run generate.py to ensure full end-to-end behavior.

Implementation details / notes
----
- Module imports and package layout:
  - Place new modules in process_markdown/functions/.
  - Use relative imports inside the package (e.g., from .pm_utils import sanitize_model_for_filename) so modules work when run as package or imported.
  - generate.py should import new modules with from process_markdown.functions import MA_runner (absolute import) for readability and to be robust in different run contexts.

- MA_runner filename:
  - The file must be named MA_runner.py (capital "MA") per your requirement. Python modules are case-sensitive on some filesystems — be sure to commit the exact name.

- Environment and .env handling:
  - Consider extracting a small helper in pm_utils to parse .env files to keep MA_runner code cleaner.

- Heartbeat:
  - start_heartbeat is safe to keep in pm_utils. Keep its use in generate.main().

- TEMP_BASE:
  - You can either keep a single TEMP_BASE constant in MA_runner.py or place a shared TEMP_BASE in pm_utils and import it into MA_runner and processor. For minimal change, move TEMP_BASE to MA_runner.py initially.

- Error handling:
  - Preserve current error logging behavior (print). Optionally, add structured logging later.

- Formatting and linting:
  - Running a formatter (black/ruff) is recommended after the refactor but not required for correctness.

Testing and verification plan
----
- Unit tests:
  - pm_utils.sanitize_model_for_filename: many inputs (None, 'openai:gpt-4o', 'Weird Model! 123', '-----', very long strings)
  - pm_utils.normalize_report_entries: tuples, lists, bare paths
  - output_manager.save_generated_reports: create temp input file and generated md stub files, verify mirrored output path and names

- Integration / smoke:
  - Create a small test config.yaml pointing to process_markdown/test/mdinputs/commerce and a test outputs dir.
  - Run generate.py to ensure expected output files are created and no exceptions occur.

- Manual run:
  - Use a small input set and validate filenames follow the expected patterns:
    base.ma.1.<modellabel>.md
    base.gptr.1.<modellabel>.md
    base.dr.1.<modellabel>.md

Estimated effort
----
- Create modules and update imports (ACT): 25–45 minutes
- Run smoke tests / fix import issues: 10–15 minutes
- Add unit tests + run them: 20–40 minutes
- Final cleanup and linting: 15–30 minutes
Overall: ~1–2.5 hours depending on test coverage and environment hiccups.

Implementation tasks (ordered)
----
- [ ] Create process_markdown/functions/pm_utils.py and add helper functions
- [ ] Create process_markdown/functions/MA_runner.py and port MA code
- [ ] Create process_markdown/functions/gptr_runner.py and port run_gpt_researcher_runs
- [ ] Create process_markdown/functions/output_manager.py and port save_generated_reports
- [ ] Create process_markdown/functions/processor.py and port process_file (or keep process_file in generate.py if preferred)
- [ ] Add __init__.py to process_markdown/functions/
- [ ] Update process_markdown/generate.py imports to use new modules
- [ ] Run smoke tests and manual end-to-end run
- [ ] Remove old duplicate functions in generate.py once verified
- [ ] (Optional) Add unit tests and CI checks

Next step (I can implement now)
----
You told me to switch to Act mode — I can now create the new files under process_markdown/functions/ and update generate.py to import from them. Confirm you want me to:
  - create the modules and wire generate.py,
  - run a smoke test (import check),
  - leave original generate.py behavior unchanged (no deletion of code yet).

If yes, I will proceed to implement step 1 (create modules and copy code) and run a basic import check. I will mark the implementation progress in the task checklist as I go.
