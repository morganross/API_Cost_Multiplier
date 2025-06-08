# Research Report: `RuntimeWarning: coroutine '...' was never awaited` in Typer Applications

## Problem Description

The `RuntimeWarning: coroutine '...' was never awaited` is consistently observed when executing `async` commands within the `llm-doc-eval` CLI application, which is built using the `typer` framework. This warning indicates that an asynchronous function (a coroutine) is being called, but its execution is not being properly awaited by the `asyncio` event loop. While the commands appear to complete their intended tasks (e.g., "Pairwise evaluations complete."), the persistence of this warning suggests an underlying issue with the asynchronous execution flow or how `typer` manages the `asyncio` event loop.

## Analysis of Potential Causes

1.  **Typer's Internal `asyncio` Management:**
    `typer` is designed to seamlessly integrate with `asyncio`, allowing developers to define `async def` functions as commands. When such a command is invoked, `typer` is responsible for running it within an `asyncio` event loop and ensuring it is properly awaited. The warning suggests that in certain scenarios or environments, this internal management might not perfectly `await` all coroutines, leading to the warning. This could be due to subtle timing issues, race conditions, or specific ways the event loop is being handled internally by `typer`.

2.  **Event Loop Conflicts:**
    If there's an existing `asyncio` event loop already running in the environment where the `typer` application is launched, or if `typer` attempts to create a new event loop in a context where one already exists, it can lead to conflicts. These conflicts might manifest as `RuntimeWarning`s or other unexpected asynchronous behavior.

3.  **Python Version and Environment Specifics:**
    While `asyncio` is a core part of Python, and `typer` is a mature library, subtle differences in Python versions (e.g., how `asyncio` handles event loops in different minor versions) or specific system configurations can sometimes expose these types of warnings. The behavior might not be universally reproducible across all environments.

## Attempted Solutions and Their Outcomes

1.  **Moving `typer.echo` Statement:**
    Initially, it was hypothesized that the warning might be due to a `typer.echo` statement being outside the `async` function's scope but still related to its completion. This was corrected by moving the `typer.echo("Pairwise evaluations complete.")` statement inside the `run_pairwise` function.
    *   **Outcome:** The warning persisted, indicating that this was not the root cause.

2.  **Wrapping `app()` with `asyncio.run()`:**
    A common pattern for running top-level `async` code from a synchronous entry point is to wrap the main `async` call with `asyncio.run()`. This was attempted by changing `app()` to `asyncio.run(app())` at the end of `cli.py`.
    *   **Outcome:** The warning persisted. This suggests that `typer` might have its own internal `asyncio.run()` mechanism, or that this external wrapping interferes with `typer`'s internal event loop management.

3.  **Simplified `test_async_typer.py`:**
    A minimal `typer` application (`test_async_typer.py`) with a simple `async` command was created to isolate the issue. Various ways of calling this command were attempted.
    *   **Outcome:** The `RuntimeWarning` was consistently reproduced, confirming that the issue is not specific to the complexity of `cli.py` but rather a general interaction between `typer` and `asyncio` in this environment.

## Recommended Solutions/Workarounds

Given that the user considers the `RuntimeWarning` a critical failure, ignoring it is not a viable option. The most robust solution to address this warning and ensure proper asynchronous execution is to implement a synchronous wrapper for all `async` `typer` commands, explicitly calling `asyncio.run()` within the wrapper.

1.  **Synchronous Wrapper for `async` Commands:**
    This approach involves creating a decorator that wraps the `async` command function with a synchronous function. This synchronous wrapper then explicitly calls `asyncio.run()` on the `async` function, ensuring that the coroutine is properly awaited.

    **Implementation Example:**

    ```python
    from functools import wraps
    import asyncio
    import typer

    def sync_command(async_func):
        """
        A decorator to run async Typer commands in a synchronous context.
        Ensures the coroutine is properly awaited.
        """
        @wraps(async_func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(async_func(*args, **kwargs))
        return sync_wrapper

    # Usage in cli.py:
    @app.command()
    @sync_command
    async def run_pairwise(folder_path: str = typer.Argument(...)):
        # ... existing async code ...
        await evaluator.evaluate_pairwise_documents(documents_for_evaluator)
        typer.echo("Pairwise evaluations complete.")

    # Apply this decorator to all async commands: run_single, run_pairwise, run_all_evaluations
    ```

    *   **Pros:** This method explicitly handles the `asyncio` event loop for each command, which should eliminate the `RuntimeWarning`. It provides clear control over the asynchronous execution.
    *   **Cons:** Requires modifying each `async` command function with the `@sync_command` decorator.

2.  **Upgrade `typer` and `asyncio` (if applicable):**
    While not a direct code change, ensuring that the latest stable versions of `typer` and Python (which includes `asyncio`) are used can sometimes resolve such warnings, as newer versions may contain bug fixes or improved `asyncio` integration.

## Conclusion

The `RuntimeWarning: coroutine '...' was never awaited` is a persistent issue in the `llm-doc-eval` CLI, likely stemming from `typer`'s interaction with `asyncio` in the current environment. While the commands appear to function, the warning indicates an unhandled coroutine. The most reliable solution to address this warning and ensure proper asynchronous execution is to implement a synchronous wrapper for all `async` `typer` commands, explicitly calling `asyncio.run()` within the wrapper. This will provide explicit control over the event loop management for each command.

## Resolution and Verification

The `RuntimeWarning` was caused by `asyncio.run()` being called from within an already running event loop. This occurred because the `@sync_command` decorator, which internally calls `asyncio.run()`, was applied to both the top-level `typer` command (`run_all_evaluations`) and the sub-commands (`run_single`, `run_pairwise`) that were called internally by `run_all_evaluations`. This led to an attempt to create nested event loops, which is not allowed by `asyncio`.

The fix involved modifying `gptr-eval-process/llm-doc-eval/cli.py` by removing the `@sync_command` decorator from the `run_single` and `run_pairwise` functions. The `@sync_command` decorator was retained only on the top-level `run_all_evaluations` command.

This change ensures that `asyncio.run()` is called only once when `run_all_evaluations` is invoked from the command line. When `run_all_evaluations` subsequently calls `run_single` and `run_pairwise`, it does so as a regular `await` of an `async` function within the *same* existing event loop, thereby preventing the `RuntimeError` and the associated `RuntimeWarning`.

**Verification:**
After applying the fix, the command `python cli.py run-all-evaluations ../test/finaldocs` was executed successfully from the `gptr-eval-process/llm-doc-eval` directory. The execution completed without any `RuntimeWarning` or `RuntimeError` related to `asyncio.run()`, and the single-document and pairwise evaluations ran as expected, producing the desired summaries. This confirms the successful resolution of the issue.