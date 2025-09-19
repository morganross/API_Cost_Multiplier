# FilePromptForge Integration — Old vs New (Impact on API_Cost_Multiplier)

Summary
- ACM (API_Cost_Multiplier) currently assumes the “old” FPF runner contract (`gpt_processor_main.py` with input/output-dir semantics).
- The “new” FPF exposes a different CLI and behavior (`fpf_main.py` + `file_handler.py`, strict env handling, two-file inputs, text outputs).
- This report enumerates the differences and the concrete integration impact on ACM’s current adapter (`functions/fpf_runner.py`) and orchestrator (`generate.py`).

1) Entrypoint and Invocation
- Old (ACM’s expectation)
  - Entrypoint: `FilePromptForge/gpt_processor_main.py`
  - CLI flags:
    - `--config <yaml>`
    - `--input_dir <dir with input.md>`
    - `--output_dir <dir for response_input.md>`
    - `--log_file <path>`
    - `--prompt <prompt_filename>` (repeatable)
    - `[--model <override>]`
  - Output detection: ACM expects `response_input.md` in `output_dir`; else fallback to newest `*.md`.

- New (current FPF)
  - Entrypoint: `FilePromptForge/fpf_main.py`
  - Delegates to: `FilePromptForge/file_handler.py`; helpers in `FilePromptForge/fpf/fpf_main.py`
  - CLI flags:
    - `--file-a <path>`   (left input)
    - `--file-b <path>`   (right input)
    - `--out <path>`      (explicit output file)
    - `--config <path>`   (fpf_config.yaml)
    - `--env <path>`      (defaults to `FilePromptForge/.env`)
    - `--provider`, `--model`, `--reasoning-effort`, `--max-completion-tokens`, `-v`
  - Output: a text file (e.g., `<file_b_stem>.<model>.fpf.response.txt`) and a printed path to stdout (no `response_input.md`; no `output_dir` concept).

Impact
- The run contract changed; ACM’s `fpf_runner` command construction and output file discovery are incompatible as-is.

2) Inputs and Prompting
- Old
  - ACM writes a single string prompt to `in/input.md` and passes prompt filenames via `--prompt`.

- New
  - FPF composes the prompt from two files:
    - `--file-a` and `--file-b`, using `compose_input(file_a, file_b, prompt_template)`
    - `prompt_template` is specified in `fpf_config.yaml` (file path or literal string with `{{file_a}}` / `{{file_b}}` placeholders).
  - No `--prompt` flags on the CLI.

Impact
- Natural mapping for ACM:
  - `file_a` = `instructions_file` (from ACM config)
  - `file_b` = input markdown currently being processed
  - `prompt_template` configured in `fpf_config.yaml`

3) Environment and Secrets
- Old
  - Keys could be taken from environment/config with fewer constraints.

- New (strict)
  - `file_handler.py` loads provider API keys exclusively from `FilePromptForge/.env` (canonical source), using `_read_key_from_env_file`.
  - It sets the provider-specific env var (e.g., `OPENAI_API_KEY`, `GOOGLE_API_KEY`), then builds headers (`x-goog-api-key` for Google; `Authorization: Bearer` for OpenAI).
  - Missing key in `FilePromptForge/.env` => hard failure. No override from outer env.

Impact
- We propagated root `.env` into `FilePromptForge/.env` (and other targets).
- Ensure key name matches `provider` in `fpf_config.yaml` (e.g., `OPENAI_API_KEY` vs `GOOGLE_API_KEY`).

4) Output Artifacts and Logging
- Old
  - `response_input.md` in `output_dir`; logs via `--log_file`.

- New
  - Human-readable text written to `--out` (or default `"<file_b_stem>.<model>.fpf.response.txt"`).
  - Per-run consolidated JSON logs saved under `FilePromptForge/logs/*.json` (contains request/response, reasoning, usage, web_search segments).
  - Rotating log at `FilePromptForge/logs/fpf_run.log`.

Impact
- ACM currently copies `*.md` reports. New FPF produces `.txt`. Either accept `.txt` outputs or convert/rename to `.md` in ACM’s save step.

5) Provider Abstraction and Constraints
- Old
  - `gpt_processor_main.py` embedded provider logic.

- New
  - Modular providers at `filepromptforge.providers.<provider>.fpf_<provider>_main` with:
    - `validate_model(model) -> bool`
    - `build_payload(prompt, cfg) -> (body, headers)`
    - `parse_response(raw_json) -> str`
    - `extract_reasoning(raw_json) -> Optional[str]`
  - Strong policy enforcement in `file_handler`:
    - Web search must be used (tool/grounding evidence) else fail (`_response_used_websearch`).
    - Reasoning must be present else fail.

Impact
- Failures surface earlier and more explicitly (no silent empty saves). ACM should surface these errors.

6) Config schema changes
- Old
  - `default_config.yaml` (provider-nested sections with model under `openai/openrouter/google`). Prompt files and `prompts_dir` existed.

- New
  - `fpf_config.yaml` includes:
    - `provider`, `model`
    - `provider_urls` `{ provider_name: url }` or fallback `provider_url`
    - `prompt_template` (file path or literal string)
    - `reasoning.effort`, `max_completion_tokens`, `title`, `referer`
  - No `prompts_dir` or prompt filenames; no `input_dir/output_dir` semantics.

Impact
- ACM’s model detection should read `cfg["model"]` and `cfg["provider"]` from `fpf_config.yaml` instead of parsing nested provider sections.
- Any references to prompt filenames in ACM are obsolete for FPF.

7) What breaks in ACM today (without changes)
- `functions/fpf_runner.py` points to `gpt_processor_main.py` and passes unsupported flags (`--input_dir/--output_dir/--prompt`).
- ACM expects `response_input.md`; new FPF writes `*.fpf.response.txt` and prints a path.
- Old config parsing in ACM won’t find `model` the same way (moved to top-level `fpf_config.yaml`).
- ACM supplies a single prompt string; new FPF expects two files (`instructions` + `content`).

8) Remediation paths (for future implementation; no code change now)
- Compatibility shim (no ACM changes)
  - `FilePromptForge/apicostmultiplier_shim.py` to accept old flags and internally call `fpf_main.py` with two inputs and an `--out` path, finally writing a `.md` file compatible with ACM’s save flow and exit 0.

- Update ACM adapter (`functions/fpf_runner.py`)
  - Write two temp files from ACM’s `instructions_file` and current `input_md`.
  - Call `fpf_main.py` with `--config fpf_config.yaml`, `--env FilePromptForge/.env`, and optional `--provider/--model`.
  - Capture the printed output path or pass `--out` explicitly.
  - Copy/convert the `.txt` output into ACM’s output mirror, optionally renaming to `.md`.
  - Update model detection to read `fpf_config.yaml` (`cfg["provider"]`, `cfg["model"]`).

9) Concrete mapping proposal (reference)
- Inputs:
  - `file_a` = `instructions_file` (ACM)
  - `file_b` = current markdown file
- CLI example (concept):
  - `python fpf_main.py --config fpf_config.yaml --file-a "<instructions_file>" --file-b "<input_md>" --out "<temp_out.txt>" [--provider ...] [--model ...]`
- Output handling:
  - Copy `temp_out.txt` to ACM’s output structure, using existing naming scheme (possibly with `.md` extension).

Appendix: Old vs New flag mapping (conceptual)
- `--config` (old/new) => same concept (different schema file name/content)
- `--input_dir/--output_dir` (old) => replaced by `--file-a/--file-b` + `--out` (new)
- `--prompt` (old) => replaced by `prompt_template` in `fpf_config.yaml` (new)
- `--model` (old/new) => still supported as override (new)
- `--log_file` (old) => logging handled internally; consolidated logs in `FilePromptForge/logs` (new)

End of report.
