# DB LOCATION ERROR

The `OperationalError: no such table` problem occurs because the `results.db` SQLite database is created in the current working directory from which the `llm-doc-eval` CLI is executed.

**Problem Description:**
When the `llm-doc-eval` CLI is run from a directory other than `gptr-eval-process/llm-doc-eval/` (e.g., from the project root `c:/dev/monorepo`), a new `results.db` file is created in that current working directory. This newly created database initially lacks the necessary `single_doc_results` and `pairwise_results` tables.

The `_clear_table` function in `cli.py` attempts to delete data from these tables *before* the `Evaluator` (which is responsible for creating these tables if they don't exist) has been initialized. This leads to the `OperationalError: no such table` because the tables do not yet exist in the newly created `results.db` in the current working directory.

**Context of Occurrence:**
This error is observed when executing `llm-doc-eval/cli.py` commands (such as `run-all-evaluations`, `run-single`, or `run-pairwise`) from a working directory different from `gptr-eval-process/llm-doc-eval/`. For example, running `python gptr-eval-process/llm-doc-eval/cli.py run-all-evaluations gptr-eval-process/test/finaldocs` from `c:/dev/monorepo`.

**Root Cause:**
1.  **Dynamic `results.db` location:** The `results.db` file is created in the current working directory of the script execution, rather than a fixed, predictable location relative to the `llm-doc-eval` module.
2.  **Premature table clearing:** The `_clear_table` function is called before the `Evaluator` class has had a chance to initialize the database and create the required tables. The `Evaluator`'s `__aenter__` method (called by `async with Evaluator(...)`) is where the table creation logic resides.

**Impact:**
This issue prevents the successful execution of `llm-doc-eval` commands that involve clearing or interacting with the database tables, especially when the database is new or located in a different path due to a change in the execution's current working directory.