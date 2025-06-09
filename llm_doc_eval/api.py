import os
import pandas as pd
from sqlalchemy import create_engine, text
import yaml
from typing import Optional, Tuple, Dict
import asyncio

from .loaders.text_loader import load_documents_from_folder
from .engine.evaluator import Evaluator
from .engine.metrics import Metrics
from .engine.elo_calculator import calculate_elo_ratings

# Global dictionary to store document paths (moved from cli.py)
DOC_PATHS = {}

def load_config(cli_file_path):
    """
    Loads and parses the configuration from config.yaml.
    """
    config_dir = os.path.dirname(os.path.abspath(cli_file_path))
    config_file_path = os.path.join(config_dir, 'config.yaml')

    try:
        with open(config_file_path, 'r') as file:
            config_data = yaml.safe_load(file)
        return config_data
    except FileNotFoundError:
        print(f"Error: Config file not found at {config_file_path}")
        raise
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file: {e}")
        raise

# Load configuration at the very beginning
config = load_config(cli_file_path=__file__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results.db')
MAX_CONCURRENT_LLM_CALLS = config['llm_api']['max_concurrent_llm_calls']

def _create_tables(db_path: str):
    """Creates the necessary tables if they don't exist."""
    db_engine = create_engine(f'sqlite:///{db_path}')
    with db_engine.connect() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS single_doc_results (
                doc_id TEXT,
                model TEXT,
                trial INTEGER,
                criterion TEXT,
                score REAL,
                reason TEXT,
                timestamp TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS pairwise_results (
                doc_id_1 TEXT,
                doc_id_2 TEXT,
                model TEXT,
                trial INTEGER,
                winner_doc_id TEXT,
                reason TEXT,
                timestamp TEXT
            )
        """))
        connection.commit()
    print("Ensured database tables exist.")

def _clear_table(db_path: str, table_name: str):
    """Clears all data from the specified table."""
    db_engine = create_engine(f'sqlite:///{db_path}')
    with db_engine.connect() as connection:
        table_exists = connection.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")).fetchone()
        if table_exists:
            connection.execute(text(f"DELETE FROM {table_name}"))
            connection.commit()
            print(f"Cleared table: {table_name}")
        else:
            print(f"Table '{table_name}' does not exist, skipping clear.")

async def run_single_evaluation(folder_path: str, db_path: str = DB_PATH, max_concurrent_llm_calls: int = MAX_CONCURRENT_LLM_CALLS) -> pd.DataFrame:
    """
    Executes single-document evaluations on files in the specified folder.
    """
    print(f"Running single-document evaluations on: {folder_path}")
    _create_tables(db_path)
    async with Evaluator(db_path=db_path, max_concurrent_llm_calls=max_concurrent_llm_calls) as evaluator:
        _clear_table(db_path, "single_doc_results")
        documents = list(load_documents_from_folder(folder_path))
        if not documents:
            print("No .txt or .md documents found in the specified folder.")
            return pd.DataFrame()

        for doc_id, content, file_path in documents:
            DOC_PATHS[doc_id] = file_path
            print(f"  Evaluating single document: {doc_id}")
            # evaluator.evaluate_single_document now returns the DataFrame
            single_doc_results_df = await evaluator.evaluate_single_document(doc_id, content)
        
        print("Single-document evaluations complete.")
        return single_doc_results_df # Return the accumulated results

async def run_pairwise_evaluation(folder_path: str, db_path: str = DB_PATH, max_concurrent_llm_calls: int = MAX_CONCURRENT_LLM_CALLS) -> pd.DataFrame:
    """
    Executes pairwise evaluations on files in the specified folder.
    """
    print(f"Running pairwise evaluations on: {folder_path}")
    _create_tables(db_path)
    async with Evaluator(db_path=db_path, max_concurrent_llm_calls=max_concurrent_llm_calls) as evaluator:
        _clear_table(db_path, "pairwise_results")
        documents = list(load_documents_from_folder(folder_path))
        if not documents:
            print("No .txt or .md documents found in the specified folder.")
            return pd.DataFrame()
        
        print(f"  Evaluating {len(documents)} documents in pairwise combinations.")
        for doc_id, content, file_path in documents:
            DOC_PATHS[doc_id] = file_path
        documents_for_evaluator = [(doc_id, content) for doc_id, content, _ in documents]
        # evaluator.evaluate_pairwise_documents now returns the DataFrame
        pairwise_results_df = await evaluator.evaluate_pairwise_documents(documents_for_evaluator)
        print("Pairwise evaluations complete.")
        return pairwise_results_df # Return the accumulated results

async def run_all_evaluations(folder_path: str, db_path: str = DB_PATH, max_concurrent_llm_calls: int = MAX_CONCURRENT_LLM_CALLS) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Runs both single and pairwise evaluations.
    """
    print(f"Starting all evaluations for documents in: {folder_path}")
    _create_tables(db_path)
    
    single_doc_results_df = await run_single_evaluation(folder_path, db_path, max_concurrent_llm_calls)
    pairwise_results_df = await run_pairwise_evaluation(folder_path, db_path, max_concurrent_llm_calls)
    
    print("\nAll evaluations complete.")
    return single_doc_results_df, pairwise_results_df

def get_single_doc_summary(raw_single_doc_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculates and returns summaries for single-document evaluations.
    """
    metrics_calculator = Metrics()
    summary_df = metrics_calculator.calculate_single_doc_metrics(raw_single_doc_df)
    overall_avg_scores_df = metrics_calculator.calculate_overall_average_scores(raw_single_doc_df)
    return summary_df, overall_avg_scores_df

def get_pairwise_summary(raw_pairwise_df: pd.DataFrame, db_path: str = DB_PATH, doc_paths: Dict[str, str] = DOC_PATHS) -> pd.DataFrame:
    """
    Calculates and returns summaries for pairwise evaluations, including Elo ratings.
    """
    metrics_calculator = Metrics()
    overall_win_rates_df = metrics_calculator.calculate_pairwise_win_rates(raw_pairwise_df)
    
    elo_scores = calculate_elo_ratings(db_path=db_path)
    elo_df = pd.DataFrame.from_dict(elo_scores, orient='index', columns=['elo_rating']).reset_index()
    elo_df.rename(columns={'index': 'doc_id'}, inplace=True)

    combined_summary_df = pd.merge(overall_win_rates_df, elo_df, on='doc_id', how='left')
    combined_summary_df['elo_rating'] = combined_summary_df['elo_rating'].fillna(0).round(2)

    # Add full paths to the combined summary DataFrame
    combined_summary_df['full_path'] = combined_summary_df['doc_id'].map(doc_paths)
    
    return combined_summary_df

def get_best_report_by_elo(db_path: str = DB_PATH, doc_paths: Dict[str, str] = DOC_PATHS) -> Optional[str]:
    """
    Identifies the full path of the document with the highest Elo rating from the evaluation results.
    """
    elo_scores = calculate_elo_ratings(db_path=db_path)
    if not elo_scores:
        print("No Elo scores found to determine the best report.")
        return None

    # Find the doc_id with the highest Elo rating
    best_doc_id = max(elo_scores, key=elo_scores.get)
    
    # Retrieve the full path using the doc_paths map
    best_report_path = doc_paths.get(best_doc_id)

    if best_report_path:
        print(f"Identified best report (highest Elo): {best_report_path} with Elo: {elo_scores[best_doc_id]:.2f}")
        return best_report_path
    else:
        print(f"Could not find full path for best doc_id: {best_doc_id}")
        return None