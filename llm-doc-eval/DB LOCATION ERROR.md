# OperationalError: no such table in llm-doc-eval

This document details the `OperationalError: no such table` encountered when using the `llm-doc-eval` CLI, particularly when executed from the project root directory (`c:/dev/monorepo`).

## 1. Specific Error Message

The error manifests as:
`OperationalError: no such table: pairwise_results`
or
`OperationalError: no such table: single_doc_results`

## 2. Context of Occurrence

This error typically occurs when running the `llm-doc-eval/cli.py` script, or commands that clear evaluation tables (e.g., `run-all-evaluations`), from a different working directory than where the `results.db` SQLite database was initially created or is expected to reside. A common scenario is executing the CLI from the project root directory (`c:/dev/monorepo`), while previous runs might have been from `c:/dev/monorepo/gptr-eval-process/llm-doc-eval/`.

## 3. Root Cause

The `llm-doc-eval` CLI uses an SQLite database named `results.db` to store evaluation results. SQLite databases are file-based, and by default, `results.db` is created in the *current working directory* from which the CLI is executed.

When the CLI is run from the project root (`c:/dev/monorepo`), if a `results.db` does not exist in that specific directory, a *new, empty* `results.db` file is created there. This new database, by definition, lacks the necessary `single_doc_results` and `pairwise_results` tables.

The problem arises because the `_clear_table` function (found in `cli.py`) attempts to delete data from these tables *before* the `Evaluator` (which is responsible for initializing and creating these tables upon its instantiation) has been fully initialized and had a chance to create them. Consequently, when `_clear_table` tries to execute a `DELETE` statement on a non-existent table in the newly created `results.db`, the `OperationalError: no such table` is raised.

## 4. Impact

This issue prevents the successful execution of commands that involve clearing tables (such as `run-all-evaluations`) when:
*   The `llm-doc-eval` CLI is run from a new working directory, leading to the creation of a new, empty `results.db`.
*   The `results.db` file is not found in the expected path, or a different `results.db` is being accessed that does not contain the required tables.

This effectively blocks the evaluation process until the database context is correctly managed or the table creation logic is adjusted to precede any table-clearing operations.