# Example Cleanup Plan

This document outlines the steps for cleaning up the `EXAMPLE_fucntions/` directory by migrating the used modules into the real `functions/` package, archiving unused modules into `deletepending/`, updating imports, and verifying functionality.

## 1. Identify used modules in EXAMPLE_fucntions
Based on code references, the modules that are actively imported elsewhere are:
- `config_parser.py`
- `file_manager.py`
- `gpt_researcher_client.py`

## 2. Move used modules to functions/
Move `config_parser.py`, `file_manager.py`, and `gpt_researcher_client.py` into:
```
morganross/api_cost_multiplier/functions/
```

## 3. Update import statements
Replace all occurrences of:
```python
from EXAMPLE_fucntions import …
```
with:
```python
from functions import …
```
Also handle any `process_markdown.EXAMPLE_fucntions` imports to point at `process_markdown.functions`.

## 4. Archive unused example modules
- Create a new folder `deletepending/` alongside `EXAMPLE_fucntions/`.
- Move these unused files into `deletepending/`:
  - `EXAMPLE_ma_runner_wrapper.py`
  - `llm_doc_eval_client.py`
  - `ma_runner_wrapper.py`
  - `process_markdown.py`
  - `utils.py`

## 5. Remove empty EXAMPLE_fucntions directory
If `EXAMPLE_fucntions/` is empty after step 2, delete that directory.

## 6. Verify functionality and run tests
Run existing tests or perform a smoke‑test of the CLI/UI to ensure there are no import errors or regressions.
