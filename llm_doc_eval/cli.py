import typer
import pandas as pd
import os
from typing import Optional, Tuple, Dict
from functools import wraps
import asyncio

# Import the new API functions
from .api import (
    run_single_evaluation,
    run_pairwise_evaluation,
    run_all_evaluations,
    get_single_doc_summary,
    get_pairwise_summary,
    get_best_report_by_elo,
    DB_PATH, # Import DB_PATH from api.py
    DOC_PATHS # Import DOC_PATHS from api.py
)
from sqlalchemy import create_engine, text # Keep for direct DB access in summary/export commands

app = typer.Typer()

def sync_command(async_func):
    """
    A decorator to run async Typer commands in a synchronous context.
    Ensures the coroutine is properly awaited.
    """
    @wraps(async_func)
    def sync_wrapper(*args, **kwargs):
        return asyncio.run(async_func(*args, **kwargs))
    return sync_wrapper

@app.command()
@sync_command
async def run_single(
    folder_path: str = typer.Argument(..., help="Path to the folder containing documents for single-document evaluation.")
):
    """
    Runs single-document evaluations on files in the specified folder.
    """
    await run_single_evaluation(folder_path)
    print("Single-document evaluations complete.")

@app.command()
def summary_single():
    """
    Displays a summary of single-document evaluation results.
    """
    print("Displaying single-document evaluation summary.")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-single' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("single_doc_results", db_engine)
    except ValueError:
        print(f"Error: Table 'single_doc_results' not found in {DB_PATH}. Please run 'run-single' first.")
        return
    
    summary_df, overall_avg_scores_df = get_single_doc_summary(df)

    print("\n--- Raw Single-Document Scores ---")
    print(df.to_string())
    
    print("\n--- Aggregated Single-Document Summary ---")
    print(summary_df.to_string())

    print("\n--- Overall Average Scores Per Document ---")
    print(overall_avg_scores_df.to_string())

@app.command()
@sync_command
async def run_pairwise(
    folder_path: str = typer.Argument(..., help="Path to the folder containing documents for pairwise evaluation.")
):
    """
    Runs pairwise evaluations on files in the specified folder.
    """
    await run_pairwise_evaluation(folder_path)
    print("Pairwise evaluations complete.")

@app.command()
def summary_pairwise():
    """
    Displays a summary of pairwise evaluation results, including overall win rates and Elo ratings.
    Also identifies the document with the highest win rate and highest Elo rating.
    """
    print("Displaying pairwise evaluation summary.")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("pairwise_results", db_engine)
    except ValueError:
        print(f"Error: Table 'pairwise_results' not found in {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    combined_summary_df = get_pairwise_summary(df, db_path=DB_PATH, doc_paths=DOC_PATHS)

    print("\n--- Overall Pairwise Summary (Win Rates & Elo Ratings) ---")
    print(combined_summary_df.to_string())

    if not combined_summary_df.empty:
        print("\n--- Ranking by Win Rate (Highest First) ---")
        win_rate_ranked_df = combined_summary_df.sort_values(by='overall_win_rate', ascending=False)
        for index, row in win_rate_ranked_df.iterrows():
            print(f"  {row['doc_id']} ({row['full_path']}): {row['overall_win_rate']:.2f}% Win Rate, Elo: {row['elo_rating']:.2f}")

        print("\n--- Ranking by Elo Rating (Highest First) ---")
        elo_ranked_df = combined_summary_df.sort_values(by='elo_rating', ascending=False)
        for index, row in elo_ranked_df.iterrows():
            print(f"  {row['doc_id']} ({row['full_path']}): {row['elo_rating']:.2f} Elo, Win Rate: {row['overall_win_rate']:.2f}%")

        # Best file Elo and full path
        highest_elo_doc = elo_ranked_df.iloc[0]
        print(f"\nbest file elo: {highest_elo_doc['elo_rating']:.2f}")
        print(f"full path and filename of file with highest elo: {highest_elo_doc['full_path']}")

@app.command()
def raw_pairwise():
    """
    Displays all raw pairwise evaluation results.
    """
    print("Displaying raw pairwise evaluation results.")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("pairwise_results", db_engine)
    except ValueError:
        print(f"Error: Table 'pairwise_results' not found in {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    print("\n--- Raw Pairwise Evaluation Results ---")
    df_display = df.drop(columns=['reason', 'timestamp'], errors='ignore')
    print(df_display.to_string())

@app.command()
def export_single_raw(
    output_path: str = typer.Option("single_doc_raw_results.csv", help="Path to save the raw single-document results CSV.")
):
    """
    Exports raw single-document evaluation results to a CSV file.
    """
    print(f"Exporting raw single-document results to {output_path}")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-single' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("single_doc_results", db_engine)
    except ValueError:
        print(f"Error: Table 'single_doc_results' not found in {DB_PATH}. Please run 'run-single' first.")
        return
    
    df.to_csv(output_path, index=False)
    print(f"Raw single-document results exported to {output_path}")

@app.command()
def export_single_summary(
    output_path: str = typer.Option("single_doc_summary.csv", help="Path to save the aggregated single-document summary CSV.")
):
    """
    Exports aggregated single-document evaluation summary to a CSV file.
    """
    print(f"Exporting aggregated single-document summary to {output_path}")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-single' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("single_doc_results", db_engine)
    except ValueError:
        print(f"Error: Table 'single_doc_results' not found in {DB_PATH}. Please run 'run-single' first.")
        return
    
    summary_df, overall_avg_scores_df = get_single_doc_summary(df)

    merged_summary_df = pd.merge(summary_df, overall_avg_scores_df, on='doc_id', how='left')
    
    merged_summary_df.to_csv(output_path, index=False)
    print(f"Aggregated single-document summary exported to {output_path}")

@app.command()
def export_pairwise_raw(
    output_path: str = typer.Option("pairwise_raw_results.csv", help="Path to save the raw pairwise evaluation results CSV.")
):
    """
    Exports raw pairwise evaluation results to a CSV file.
    """
    print(f"Exporting raw pairwise results to {output_path}")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("pairwise_results", db_engine)
    except ValueError:
        print(f"Error: Table 'pairwise_results' not found in {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    df_display = df.drop(columns=['reason', 'timestamp'], errors='ignore')
    df_display.to_csv(output_path, index=False)
    print(f"Raw pairwise results exported to {output_path}")

@app.command()
def export_pairwise_summary(
    output_path: str = typer.Option("pairwise_summary.csv", help="Path to save the aggregated pairwise summary CSV.")
):
    """
    Exports aggregated pairwise evaluation summary to a CSV file.
    """
    print(f"Exporting aggregated pairwise summary to {output_path}")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    db_engine = create_engine(f'sqlite:///{DB_PATH}')
    try:
        df = pd.read_sql_table("pairwise_results", db_engine)
    except ValueError:
        print(f"Error: Table 'pairwise_results' not found in {DB_PATH}. Please run 'run-pairwise' first.")
        return
    
    summary_df = get_pairwise_summary(df, db_path=DB_PATH, doc_paths=DOC_PATHS)
    
    summary_df.to_csv(output_path, index=False)
    print(f"Aggregated pairwise summary exported to {output_path}")

@app.command()
@sync_command
async def run_all_evaluations(
    folder_path: str = typer.Argument(..., help="Path to the folder containing documents for evaluation."),
    config_path: Optional[str] = typer.Option(None, help="Path to a custom configuration file.")
):
    """
    Runs both single and pairwise evaluations, then exports and displays summaries.
    """
    # config_path is not directly used by the API functions, as config is loaded internally in api.py
    # If custom config loading is needed, it should be handled within the API functions or passed as a parameter.
    
    print(f"Starting all evaluations for documents in: {folder_path}")
    
    single_doc_results_df, pairwise_results_df = await run_all_evaluations(folder_path)
    
    print("\n--- Exporting Summaries ---")
    export_single_summary(output_path="single_doc_summary.csv")
    export_pairwise_summary(output_path="pairwise_summary.csv")
    
    print("\n--- Displaying Single-Document Summary ---")
    summary_single()
    
    print("\n--- Displaying Pairwise Summary ---")
    summary_pairwise()
    
    print("\nAll evaluations, exports, and summaries complete.")

app()
