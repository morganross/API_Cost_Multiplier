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
import time
import json
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

from reporting.html_exporter import generate_html_report

# Import the new timeline aggregator
try:
    from tools.eval_timeline_aggregator import EvalTimelineAggregator
except ImportError:
    EvalTimelineAggregator = None  # Graceful fallback if not available


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
    parser.add_argument(
        "--save-winner",
        action="store_true",
        help="If set, saves the winning report to the winners directory."
    )
    parser.add_argument(
        "--winners-dir",
        help="Directory to save the winning report. Required if --save-winner is set."
    )
    parser.add_argument(
        "--timeline-json",
        help="Path to timeline JSON file for inclusion in HTML report."
    )
    parser.add_argument(
        "--eval-timeline-json",
        help="Path to eval timeline JSON file for inclusion in HTML report."
    )
    parser.add_argument(
        "--eval-phase-set",
        choices=["precombine", "postcombine"],
        default=None,
        help="Filter eval timeline chart to specific phases: 'precombine' for phases 1-2, 'postcombine' for phases 3-5."
    )
    args = parser.parse_args()

    # Setup eval logger from config (no basicConfig; named logger only)
    try:
        cfg_path = os.path.join(script_dir, 'config.yaml')
        config = config_parser.load_config(cfg_path)
    except Exception:
        cfg_path = None # Ensure cfg_path is defined even if load fails
        config = {}
    console_name, file_name, console_level, file_level = logging_levels.resolve_levels(config, component='eval')
    eval_logger = logging_levels.build_logger("eval", console_level, file_level)
    logging_levels.emit_health(eval_logger, console_name, file_name, console_level, file_level)

    # Define the specific config path for llm-doc-eval library
    # This file contains the 'models' definitions required for judging
    # BUT we use the main config (cfg_path) for run_evaluation because it has 
    # eval.pairwise_top_n and other ACM-specific settings
    llm_eval_config_path = os.path.join(llm_eval_path, 'config.yaml')
    if not os.path.exists(llm_eval_config_path):
        print(f"Warning: Evaluation config not found at {llm_eval_config_path}. Falling back to main config.")
        llm_eval_config_path = cfg_path
    
    # Use main ACM config for run_evaluation (has pairwise_top_n, mode, etc.)
    # Fall back to llm_eval_config_path only if main config is missing
    eval_config_path = cfg_path if cfg_path and os.path.exists(cfg_path) else llm_eval_config_path

    base_dir = os.path.dirname(os.path.abspath(__file__))
    eval_dir = None
    candidates = []

    if args.target_files:
        print(f"\n=== EVALUATION SCRIPT STARTUP ===")
        print(f"  Script: {__file__}")
        print(f"  Python: {sys.executable} ({sys.version})")
        print(f"  Working dir: {os.getcwd()}")
        print(f"  Time: {datetime.datetime.now()}")
        
        print(f"\n=== TARGET FILES RECEIVED ===")
        print(f"  Files passed via --target-files: {len(args.target_files)}")
        
        # Validate and log each file
        for i, f in enumerate(args.target_files, 1):
            print(f"\n  File {i}/{len(args.target_files)}: {os.path.basename(f)}")
            print(f"    Full path: {f}")
            if os.path.isfile(f):
                size = os.path.getsize(f)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f))
                print(f"    [OK] EXISTS: {size} bytes, modified {mtime}")
            else:
                print(f"    [MISSING] File not found!")
        
        # Filter for existing files and valid extensions
        candidates = [
            f for f in args.target_files
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in (".md", ".txt")
        ]
        
        print(f"\n=== FILE FILTERING RESULTS ===")
        print(f"  Input files: {len(args.target_files)}")
        print(f"  Valid candidates: {len(candidates)}")
        print(f"  Filtered out: {len(args.target_files) - len(candidates)}")
        
        if len(candidates) < 1:
            print(f"\nâŒ ERROR: No valid candidate files provided via --target-files")
            print(f"  Requirements: file must exist AND have .md or .txt extension")
            return
        
        print(f"\nValid candidates: {len(candidates)}")
        
        # Create FRESH temp directory with timestamp to prevent reuse
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        temp_eval_dir = os.path.join(tempfile.gettempdir(), f"llm_eval_{timestamp}")
        os.makedirs(temp_eval_dir, exist_ok=True)
        
        print(f"Created fresh temp directory: {temp_eval_dir}")
        logging.getLogger("eval").info("[EVAL_TEMP_DIR] Created fresh: %s", temp_eval_dir)
        
        # Clean up OLD temp directories (older than 1 hour)
        try:
            temp_root = tempfile.gettempdir()
            cutoff = time.time() - 3600  # 1 hour ago
            cleaned_count = 0
            for item in os.listdir(temp_root):
                if item.startswith("llm_eval_") or item.startswith("llm_doc_eval_single_batch_"):
                    item_path = os.path.join(temp_root, item)
                    if os.path.isdir(item_path):
                        try:
                            mtime = os.path.getmtime(item_path)
                            if mtime < cutoff:
                                shutil.rmtree(item_path)
                                cleaned_count += 1
                                print(f"  Cleaned up stale temp directory: {item}")
                        except Exception:
                            pass
            if cleaned_count > 0:
                print(f"  Cleaned up {cleaned_count} stale temp directories")
        except Exception as e:
            print(f"  Warning: Could not clean up old temp directories: {e}")
        
        # Copy files to temp directory
        temp_candidates = []
        for f in candidates:
            try:
                temp_path = os.path.join(temp_eval_dir, os.path.basename(f))
                shutil.copy2(f, temp_path)
                temp_candidates.append(temp_path)
                print(f"  Copied: {os.path.basename(f)}")
            except Exception as e:
                print(f"  ERROR: Could not copy {f} to temp eval dir: {e}")
        
        eval_dir = temp_eval_dir
        candidates = temp_candidates
        
        print(f"\nReady to evaluate {len(candidates)} files from temp directory")

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
    eval_iterations = int(eval_config.get('iterations', 1))

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
        logging.getLogger("eval").info("[EVALUATE_START] Starting evaluation")
        logging.getLogger("eval").info(f"[EVALUATE_START] Evaluation directory: {eval_dir}")
        logging.getLogger("eval").info(f"[EVALUATE_START] Database path: {db_path}")
        logging.getLogger("eval").info(f"[EVALUATE_START] Mode: config (will read from config.yaml)")
        logging.getLogger("eval").info(f"[EVALUATE_START] Config path: {eval_config_path}")
        logging.getLogger("eval").info(f"[EVALUATE_START] Iterations: {eval_iterations}")
        result = await run_evaluation(folder_path=eval_dir, db_path=db_path, mode="config", config_path=eval_config_path, iterations=eval_iterations)
        logging.getLogger("eval").info(f"[EVALUATE_COMPLETE] Evaluation returned: {result}")

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
            except Exception as log_err:
                print(f"Warning: Failed to log best report path: {log_err}")

            # Save winner to winners directory if requested
            if args.save_winner and args.winners_dir:
                try:
                    os.makedirs(args.winners_dir, exist_ok=True)
                    winner_dest_path = os.path.join(args.winners_dir, os.path.basename(best_report_path))
                    shutil.copy(best_report_path, winner_dest_path)
                    print(f"Saved winner to winners directory: {winner_dest_path}")
                    logging.getLogger("eval").info(f"[EVAL_WINNER_SAVED] path={winner_dest_path}")
                except Exception as e:
                    print(f"Error saving winner to {args.winners_dir}: {e}")
                    logging.getLogger("eval").error(f"Error saving winner: {e}")

        else:
            print("No pairwise winner available (mode may be 'single') or insufficient data to determine a winner.")

        # Auto-export CSVs
        logging.getLogger("eval").info(f"[CSV_EXPORT_START] Beginning CSV export from database: {db_path}")
        logging.getLogger("eval").info(f"[CSV_EXPORT_START] Export directory: {final_export_dir}")
        try:
            # Verify database file exists and has size
            if os.path.exists(db_path):
                db_size = os.path.getsize(db_path)
                logging.getLogger("eval").info(f"[CSV_EXPORT_DB] Database file exists: {db_size} bytes")
            else:
                logging.getLogger("eval").error(f"[CSV_EXPORT_ERROR] Database file does not exist: {db_path}")
            
            # Use final_export_dir
            conn = sqlite3.connect(db_path, timeout=30)
            try:
                cur = conn.cursor()
                # List all tables in database
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cur.fetchall()]
                logging.getLogger("eval").info(f"[CSV_EXPORT_TABLES] Database contains {len(tables)} tables: {tables}")
                
                # Export single_doc_results if data exists
                cur.execute("SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='single_doc_results'")
                if cur.fetchone()[0]:
                    cur.execute("SELECT COUNT(1) FROM single_doc_results")
                    row_count = cur.fetchone()[0]
                    logging.getLogger("eval").info(f"[CSV_EXPORT_SINGLE] Found {row_count} rows in single_doc_results")
                    if row_count:
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

                # Log which files were created
                csv_files = [f for f in os.listdir(final_export_dir) if f.endswith('.csv')]
                logging.getLogger("eval").info(f"[CSV_EXPORT_SUCCESS] Created {len(csv_files)} CSV files: {csv_files}")
                print(f"Exported CSVs to: {final_export_dir}")
                # Print export dir for runner.py to parse (required for unified HTML generation)
                print(f"[EVAL_EXPORTS] dir={final_export_dir}")
                try:
                    logging.getLogger("eval").info("[EVAL_EXPORTS] dir=%s", final_export_dir)
                except Exception as log_err:
                    print(f"Warning: Failed to log export directory: {log_err}")

                # Generate HTML report
                try:
                    # Pass timeline JSON path if provided
                    timeline_path = getattr(args, 'timeline_json', None)
                    # Pass eval timeline JSON path if provided
                    eval_timeline_path = getattr(args, 'eval_timeline_json', None)
                    
                    # Auto-generate eval timeline JSON if not provided
                    if not eval_timeline_path:
                        try:
                            # Add tools path for import
                            tools_path = os.path.join(script_dir, "tools")
                            if tools_path not in sys.path:
                                sys.path.insert(0, tools_path)
                            from eval_timeline_from_db import generate_eval_timeline
                            
                            # Find the session log file
                            log_dir = os.path.join(script_dir, "logs")
                            session_log = None
                            if os.path.isdir(log_dir):
                                logs = sorted([f for f in os.listdir(log_dir) if f.startswith("acm_session_") and f.endswith(".log")], reverse=True)
                                if logs:
                                    session_log = os.path.join(log_dir, logs[0])
                            
                            # Extract FPF log directory from result for timeline generation
                            fpf_logs_for_timeline = None
                            time_window_start_for_timeline = None
                            time_window_end_for_timeline = None
                            if isinstance(result, dict):
                                fpf_logs_dirs = result.get("fpf_logs_dirs", [])
                                if fpf_logs_dirs:
                                    # Use parent of first run_group_id folder to get all FPF logs
                                    first_dir = fpf_logs_dirs[0]
                                    if first_dir and os.path.isdir(first_dir):
                                        fpf_logs_for_timeline = os.path.dirname(first_dir)  # FilePromptForge/logs
                                eval_timestamps = result.get("eval_timestamps", [])
                                if eval_timestamps:
                                    starts = [ts["start"] for ts in eval_timestamps if ts.get("start")]
                                    ends = [ts["end"] for ts in eval_timestamps if ts.get("end")]
                                    if starts:
                                        time_window_start_for_timeline = min(starts)
                                    if ends:
                                        time_window_end_for_timeline = max(ends)
                            
                            eval_timeline_data = generate_eval_timeline(
                                db_path=db_path,
                                log_path=session_log,
                                config_path=eval_config_path,
                                export_dir=final_export_dir,
                                eval_type_label="eval",
                                fpf_logs_dir=fpf_logs_for_timeline,
                                time_window_start=time_window_start_for_timeline,
                                time_window_end=time_window_end_for_timeline
                            )
                            
                            # Write to temp file
                            eval_timeline_path = os.path.join(final_export_dir, "eval_timeline.json")
                            with open(eval_timeline_path, "w", encoding="utf-8") as fh:
                                json.dump(eval_timeline_data, fh, indent=2, ensure_ascii=False)
                            logging.getLogger("eval").info(f"[EVAL_TIMELINE] Auto-generated: {eval_timeline_path}")
                        except Exception as tl_err:
                            logging.getLogger("eval").warning(f"[EVAL_TIMELINE] Auto-generation failed: {tl_err}")
                            eval_timeline_path = None
                    
                    # Extract FPF log directories from result
                    # fpf_logs_parent_dir: Parent dir containing all run_group_id folders (for aggregator)
                    # fpf_log_dir: First run_group_id folder (for HTML report cost parsing)
                    fpf_logs_parent_dir = None
                    fpf_log_dir = None
                    if isinstance(result, dict):
                        fpf_logs_dirs = result.get("fpf_logs_dirs", [])
                        if fpf_logs_dirs and fpf_logs_dirs[0]:
                            first_dir = fpf_logs_dirs[0]
                            if first_dir and os.path.isdir(first_dir):
                                # Parent directory (logs/eval_fpf_logs) for aggregator to scan all folders
                                fpf_logs_parent_dir = os.path.dirname(first_dir)
                                # First subdirectory for HTML report
                                fpf_log_dir = first_dir
                    
                    # Generate unified timeline chart using new aggregator
                    eval_timeline_chart_data = None
                    if EvalTimelineAggregator is not None:
                        try:
                            # Determine eval_phase_set from command line arg
                            eval_phase_set = getattr(args, 'eval_phase_set', None)
                            
                            aggregator = EvalTimelineAggregator(
                                config_path=cfg_path,
                                eval_config_path=llm_eval_config_path,
                                db_path=db_path,
                                fpf_logs_dir=fpf_logs_parent_dir,
                                csv_export_dir=final_export_dir,
                                time_window_start=time_window_start_for_timeline if 'time_window_start_for_timeline' in dir() else None,
                                time_window_end=time_window_end_for_timeline if 'time_window_end_for_timeline' in dir() else None,
                                eval_phase_set=eval_phase_set,
                            )
                            eval_timeline_chart_data = aggregator.to_dict()
                            
                            # Write the chart data as JSON artifact with phase-specific naming
                            # precombine -> eval_timeline_chart_pre.json
                            # postcombine -> eval_timeline_chart_post.json
                            # None (unified) -> eval_timeline_chart.json
                            if eval_phase_set == "precombine":
                                chart_filename = "eval_timeline_chart_pre.json"
                            elif eval_phase_set == "postcombine":
                                chart_filename = "eval_timeline_chart_post.json"
                            else:
                                chart_filename = "eval_timeline_chart.json"
                            
                            chart_json_path = os.path.join(final_export_dir, chart_filename)
                            with open(chart_json_path, "w", encoding="utf-8") as f:
                                json.dump(eval_timeline_chart_data, f, indent=2, ensure_ascii=False)
                            logging.getLogger("eval").info(f"[EVAL_TIMELINE_CHART] Generated: {chart_json_path}")
                        except Exception as chart_err:
                            logging.getLogger("eval").warning(f"[EVAL_TIMELINE_CHART] Generation failed: {chart_err}")
                            eval_timeline_chart_data = None
                    
                    generate_html_report(
                        db_path, 
                        final_export_dir, 
                        timeline_json_path=timeline_path,
                        doc_paths=DOC_PATHS,
                        eval_timeline_json_path=eval_timeline_path,
                        fpf_log_dir=fpf_log_dir,
                        eval_time_window_start=time_window_start_for_timeline if 'time_window_start_for_timeline' in dir() else None,
                        eval_time_window_end=time_window_end_for_timeline if 'time_window_end_for_timeline' in dir() else None,
                        eval_timeline_chart_data=eval_timeline_chart_data
                    )
                except Exception as e:
                    print(f"Warning: HTML export skipped or failed: {e}")

            finally:
                conn.close()
                logging.getLogger("eval").info("[CSV_EXPORT_DB] Database connection closed")
        except Exception as ex:
            logging.getLogger("eval").error(f"[CSV_EXPORT_ERROR] CSV export failed: {type(ex).__name__}: {ex}", exc_info=True)
            print(f"CSV export failed: {ex}")
        # Final cost line: ensure the last console output is total batch cost
        try:
            total_cost = float((result or {}).get("total_cost_usd", 0.0))
        except (ValueError, TypeError, KeyError) as cost_err:
            print(f"Warning: Could not parse total cost: {cost_err}")
            total_cost = 0.0
        print(f"[EVAL COST] total_cost_usd={total_cost}")
        try:
            logging.getLogger("eval").info("[EVAL_COST] total_cost_usd=%s", total_cost)
        except Exception as log_err:
            print(f"Warning: Failed to log eval cost: {log_err}")

        # Emit summary for runner.py to pick up
        print(f"[EVAL_SUMMARY] Database path: {db_path}")
        logging.getLogger("eval").info(f"[EVAL_SUMMARY] Database path: {db_path}")
        
        # DATABASE VERIFICATION: Check row counts
        print(f"\n=== DATABASE VERIFICATION ===")
        print(f"  Database path: {db_path}")
        
        if os.path.isfile(db_path):
            db_size = os.path.getsize(db_path)
            print(f"  [OK] Database file exists: {db_size} bytes")
            
            conn = None
            try:
                conn = sqlite3.connect(db_path, timeout=30)
                cursor = conn.cursor()
                
                # Count single-doc evaluation rows
                try:
                    cursor.execute("SELECT COUNT(*) FROM single_doc_results")
                    single_count = cursor.fetchone()[0]
                    print(f"  Single-doc evaluations: {single_count} rows")
                except sqlite3.OperationalError:
                    print(f"  Single-doc evaluations: (table not found)")
                    single_count = 0
                
                # Count pairwise comparison rows if table exists
                try:
                    cursor.execute("SELECT COUNT(*) FROM pairwise_results")
                    pair_count = cursor.fetchone()[0]
                    print(f"  Pairwise comparisons: {pair_count} rows")
                except sqlite3.OperationalError:
                    print(f"  Pairwise comparisons: (table not created)")
                    pair_count = 0
                
                # Expected rows calculation
                expected_single = len(candidates) * 2 * 4  # files Ã— evaluators Ã— criteria
                print(f"\n  Expected single-doc rows: {expected_single} ({len(candidates)} files Ã— 2 evaluators Ã— 4 criteria)")
                print(f"  Actual single-doc rows: {single_count}")
                
                if single_count < expected_single:
                    missing = expected_single - single_count
                    print(f"  WARNING: {missing} rows missing!")
                    print(f"    Possible causes:")
                    print(f"      - Evaluator API failures (check logs for gemini/openai errors)")
                    print(f"      - Database write failures (check for exceptions)")
                    print(f"      - Duplicate content skips (check for 'skipping' messages)")
                elif single_count == expected_single:
                    print(f"  âœ… SUCCESS: All expected rows present")
                else:
                    print(f"  âš ï¸  UNEXPECTED: More rows than expected ({single_count} > {expected_single})")
                
                # Get most recent evaluation timestamps
                try:
                    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM single_doc_results WHERE timestamp IS NOT NULL")
                    min_ts, max_ts = cursor.fetchone()
                    if min_ts and max_ts:
                        print(f"\n  Evaluation time range:")
                        print(f"    First: {min_ts}")
                        print(f"    Last: {max_ts}")
                except Exception as ts_err:
                    print(f"  Warning: Could not retrieve timestamp range: {ts_err}")
                
            except Exception as db_err:
                print(f"  ERROR querying database: {db_err}")
                import traceback
                print(f"  Traceback:\n{traceback.format_exc()}")
            finally:
                if conn:
                    conn.close()
                
        else:
            print(f"  âŒ ERROR: Database file not found at {db_path}")
            print(f"    This indicates database writes completely failed!")
        
    except Exception as e:
        logging.getLogger("eval").error(f"[EVALUATE_ERROR] Evaluation failed: {type(e).__name__}: {e}", exc_info=True)
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

