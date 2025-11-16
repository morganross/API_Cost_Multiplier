import os
import asyncio
import shutil
import sys # Import sys
import csv
import sqlite3
import datetime
import logging
import argparse # Import argparse
import tempfile
import uuid
from functions import logging_levels, config_parser

# Add the local llm-doc-eval package directory to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
llm_eval_path = os.path.join(script_dir, 'llm-doc-eval')
if llm_eval_path not in sys.path:
    sys.path.insert(0, llm_eval_path)

try:
    from llm_doc_eval.api import run_pairwise_evaluation, run_evaluation, get_best_report_by_elo, DOC_PATHS, DB_PATH
except ImportError as e:
    print(f"Error importing llm_doc_eval: {e}")
    print("Please ensure 'llm_doc_eval' is correctly installed or its path is in PYTHONPATH.")
    sys.exit(1) # Exit if import fails, as the script cannot proceed without it.


async def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run evaluation on generated reports.")
    parser.add_argument(
        "--target-files",
        nargs="+",
        help="List of specific files to evaluate. Overrides default directory scanning."
    )
    parser.add_argument(
        "--target-dir",
        help="Directory containing files to evaluate. Overrides default directory scanning."
    )
    args = parser.parse_args()

    # Setup eval logger from config (no basicConfig; named logger only)
    try:
        cfg_path = os.path.join(script_dir, 'config.yaml')
        config = config_parser.load_config(cfg_path)
    except Exception:
        config = {}
    console_name, file_name, console_level, file_level = logging_levels.resolve_levels(config, component='eval')
    eval_logger = logging_levels.build_logger("eval", console_level, file_level)
    logging_levels.emit_health(eval_logger, console_name, file_name, console_level, file_level)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    eval_dir = None
    candidates = []

    if args.target_files:
        print(f"Running evaluation over targeted files: {args.target_files}")
        # Filter for existing files and valid extensions
        candidates = [
            f for f in args.target_files
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in (".md", ".txt")
        ]
        if len(candidates) < 1:
            print(f"Not enough valid candidate files provided via --target-files (found {len(candidates)}; need at least 1)")
            return
        # For targeted files, create a temporary directory to hold symlinks/copies for llm-doc-eval
        # This ensures llm-doc-eval can treat it as a "folder_path"
        temp_eval_dir = os.path.join(tempfile.gettempdir(), f"llm_eval_temp_{uuid.uuid4().hex}")
        os.makedirs(temp_eval_dir, exist_ok=True)
        temp_candidates = []
        for f in candidates:
            try:
                # Create a symlink or copy the file into the temp directory
                temp_path = os.path.join(temp_eval_dir, os.path.basename(f))
                if sys.platform == "win32":
                    shutil.copy2(f, temp_path) # Windows symlinks require admin, so copy
                else:
                    os.symlink(f, temp_path)
                temp_candidates.append(temp_path)
            except Exception as e:
                print(f"Warning: Could not link/copy {f} to temp eval dir: {e}")
        eval_dir = temp_eval_dir
        candidates = temp_candidates # Update candidates to point to temp paths

    elif args.target_dir:
        print(f"Running evaluation over targeted directory: {args.target_dir}")
        eval_dir = args.target_dir
        if not os.path.isdir(eval_dir):
            print(f"Targeted directory not found: {eval_dir}")
            return
        # Ensure there are at least two candidate files (.md or .txt)
        def list_candidates_in_dir(dir_path: str):
            try:
                return [
                    os.path.join(dir_path, f) for f in os.listdir(dir_path)
                    if os.path.isfile(os.path.join(dir_path, f))
                    and os.path.splitext(f)[1].lower() in (".md", ".txt")
                ]
            except Exception as e:
                print(f"Failed to list candidates in {dir_path}: {e}")
                return []
        candidates = list_candidates_in_dir(eval_dir)
        if len(candidates) < 1:
            print(f"Not enough candidate files in {eval_dir} (found {len(candidates)}; need at least 1)")
            return

    else:
        print("Running evaluation over default folder: api_cost_multiplier/test/mdoutputs")
        eval_dir = os.path.join(base_dir, "test", "mdoutputs")

        if not os.path.isdir(eval_dir):
            print(f"Default evaluation folder not found: {eval_dir}")
            return

        # Ensure there are at least two candidate files (.md or .txt)
        def list_candidates_default(dir_path: str):
            try:
                return [
                    f for f in os.listdir(dir_path)
                    if os.path.isfile(os.path.join(dir_path, f))
                    and os.path.splitext(f)[1].lower() in (".md", ".txt")
                ]
            except Exception as e:
                print(f"Failed to list candidates in {dir_path}: {e}")
                return []

        candidates = list_candidates_default(eval_dir)

        # Fallback: if no files, default to the first subfolder under mdoutputs
        if len(candidates) < 2:
            try:
                subdirs = sorted([d for d in os.listdir(eval_dir) if os.path.isdir(os.path.join(eval_dir, d))])
            except Exception as e:
                print(f"Failed to list subfolders in {eval_dir}: {e}")
                return

            if not subdirs:
                print(f"No subfolders found under {eval_dir}; cannot evaluate.")
                return

            selected = os.path.join(eval_dir, subdirs[0])
            print(f"No/insufficient files in default mdoutputs; falling back to first subfolder under mdoutputs: {selected}")
            eval_dir = selected
            candidates = list_candidates_default(eval_dir)
            if len(candidates) < 1:
                print(f"Not enough candidate files in {eval_dir} (found {len(candidates)}; need at least 1)")
                return

    # If after all checks, eval_dir is still None or candidates are insufficient, exit
    if eval_dir is None or len(candidates) < 1:
        print("Insufficient candidate files for evaluation. Exiting.")
        return

    # Get output and export directories from config, with defaults
    eval_config = config.get('eval', {})
    output_directory = eval_config.get('output_directory', os.path.join("gptr-eval-process", "final_reports"))
    export_dir = eval_config.get('export_directory', os.path.join("gptr-eval-process", "exports"))

    # Emit start event once eval_dir is finalized
    try:
        logging.getLogger("eval").info("[EVAL_START] docs=%s", eval_dir)
    except Exception:
        pass

    # Per-run DB isolation: write results to a unique DB per run
    # If target-files was used, append a unique ID to output/export directories
    run_id_suffix = ""
    if args.target_files or args.target_dir:
        run_id_suffix = f"_{uuid.uuid4().hex[:8]}"

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_dir = os.path.dirname(DB_PATH)
    if not db_dir:
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm-doc-eval", "llm_doc_eval")
    db_path = os.path.join(db_dir, f"results_{ts}{run_id_suffix}.sqlite")
    print(f"Using per-run DB: {db_path}")
    
    # Adjust output and export directories for targeted runs
    final_output_directory = os.path.join(output_directory, f"eval_run_{ts}{run_id_suffix}")
    final_export_dir = os.path.join(export_dir, f"eval_run_{ts}{run_id_suffix}")
    os.makedirs(final_output_directory, exist_ok=True)
    os.makedirs(final_export_dir, exist_ok=True)

    try:
        # Run evaluation using mode from config.yaml (evaluation.mode: single|pairwise|both)
        result = await run_evaluation(folder_path=eval_dir, db_path=db_path, mode="config")

        # If pairwise was run (pairwise or both), compute Elo winner; otherwise this returns None
        best_report_path = get_best_report_by_elo(db_path=db_path, doc_paths=DOC_PATHS)

        if best_report_path:
            print(f"Identified best report: {best_report_path}")
            # Use final_output_directory
            final_report_path = os.path.join(final_output_directory, os.path.basename(best_report_path))
            shutil.copy(best_report_path, final_report_path)
            print(f"Copied best report to final location: {final_report_path}")
            print(f"Evaluation completed. The best report is: {best_report_path}")
            try:
                logging.getLogger("eval").info("[EVAL_BEST] path=%s", best_report_path)
            except Exception:
                pass
        else:
            print("No pairwise winner available (mode may be 'single') or insufficient data to determine a winner.")

        # Auto-export CSVs
        try:
            # Use final_export_dir
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                # Export single_doc_results if data exists
                cur.execute("SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='single_doc_results'")
                if cur.fetchone()[0]:
                    cur.execute("SELECT COUNT(1) FROM single_doc_results")
                    if cur.fetchone()[0]:
                        single_csv = os.path.join(final_export_dir, f"single_doc_results_{ts}{run_id_suffix}.csv")
                        cur2 = conn.execute("SELECT * FROM single_doc_results")
                        rows = cur2.fetchall()
                        headers = [d[0] for d in cur2.description]
                        with open(single_csv, "w", newline="", encoding="utf-8") as fh:
                            w = csv.writer(fh)
                            w.writerow(headers)
                            for r in rows:
                                w.writerow(r)

                # Export pairwise_results and Elo if data exists
                cur.execute("SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='pairwise_results'")
                if cur.fetchone()[0]:
                    cur.execute("SELECT COUNT(1) FROM pairwise_results")
                    if cur.fetchone()[0]:
                        pairwise_csv = os.path.join(final_export_dir, f"pairwise_results_{ts}{run_id_suffix}.csv")
                        cur2 = conn.execute("SELECT * FROM pairwise_results")
                        rows = cur2.fetchall()
                        headers = [d[0] for d in cur2.description]
                        with open(pairwise_csv, "w", newline="", encoding="utf-8") as fh:
                            w = csv.writer(fh)
                            w.writerow(headers)
                            for r in rows:
                                w.writerow(r)

                        # Elo summary
                        ratings = {}
                        cur3 = conn.execute("SELECT doc_id_1, doc_id_2, winner_doc_id FROM pairwise_results ORDER BY id ASC")
                        for doc1, doc2, winner in cur3.fetchall():
                            if doc1 not in ratings:
                                ratings[doc1] = 1000.0
                            if doc2 not in ratings:
                                ratings[doc2] = 1000.0
                            r1 = ratings[doc1]
                            r2 = ratings[doc2]
                            e1 = 1.0 / (1.0 + 10.0 ** ((r2 - r1) / 400.0))
                            e2 = 1.0 - e1
                            if winner == doc1:
                                s1, s2 = 1.0, 0.0
                            elif winner == doc2:
                                s1, s2 = 0.0, 1.0
                            else:
                                s1 = s2 = 0.5
                            ratings[doc1] = r1 + 32.0 * (s1 - e1)
                            ratings[doc2] = r2 + 32.0 * (s2 - e2)
                        ranking = sorted(ratings.items(), key=lambda kv: kv[1], reverse=True)
                        elo_csv = os.path.join(final_export_dir, f"elo_summary_{ts}{run_id_suffix}.csv")
                        with open(elo_csv, "w", newline="", encoding="utf-8") as fh:
                            w = csv.writer(fh)
                            w.writerow(["doc_id", "elo"])
                            for doc_id, elo in ranking:
                                w.writerow([doc_id, f"{elo:.2f}"])

                print(f"Exported CSVs to: {final_export_dir}")
                try:
                    logging.getLogger("eval").info("[EVAL_EXPORTS] dir=%s", final_export_dir)
                except Exception:
                    pass
            finally:
                conn.close()
        except Exception as ex:
            print(f"CSV export failed: {ex}")
        # Final cost line: ensure the last console output is total batch cost
        try:
            total_cost = float((result or {}).get("total_cost_usd", 0.0))
        except Exception:
            total_cost = 0.0
        print(f"[EVAL COST] total_cost_usd={total_cost}")
        try:
            logging.getLogger("eval").info("[EVAL_COST] total_cost_usd=%s", total_cost)
        except Exception:
            pass
    except Exception as e:
        print(f"Evaluation failed: {e}")
    finally:
        # Clean up temporary directory if it was created
        if args.target_files and 'temp_eval_dir' in locals() and os.path.exists(temp_eval_dir):
            try:
                shutil.rmtree(temp_eval_dir)
                print(f"Cleaned up temporary evaluation directory: {temp_eval_dir}")
            except Exception as e:
                print(f"Warning: Failed to clean up temporary evaluation directory {temp_eval_dir}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
