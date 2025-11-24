import os
import logging
import shutil
import sqlite3
import asyncio
import tempfile
from datetime import datetime
from typing import List, Dict, Optional

# Import FPF runner
try:
    from functions import fpf_runner
except ImportError:
    # Fallback for relative import if needed
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from functions import fpf_runner

class ReportCombiner:
    def __init__(self, config: Dict):
        """
        Initialize the ReportCombiner with configuration settings.
        
        Args:
            config (Dict): The full configuration dictionary, expected to have a 'combine' section.
        """
        self.full_config = config
        self.combine_config = config.get('combine', {})
        self.enabled = self.combine_config.get('enabled', False)
        self.logger = logging.getLogger("ReportCombiner")
        
        # Load model configurations from the 'models' list
        self.models = self.combine_config.get('models', [])
        
        # Paths
        self.prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        self.combine_instructions_path = os.path.join(self.prompts_dir, 'combine_instructions.txt')

    def _load_file_content(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"Failed to read file {file_path}: {e}")
            raise

    def get_top_reports(self, db_path: str, output_folder: str, limit: int = 2) -> List[str]:
        """
        Identify the top-scoring reports from the evaluation database.
        
        Args:
            db_path (str): Path to the SQLite database containing evaluation results.
            output_folder (str): Directory where the report files are located.
            limit (int): Number of top reports to retrieve.
            
        Returns:
            List[str]: List of absolute file paths to the top reports.
        """
        if not os.path.exists(db_path):
            self.logger.error(f"Database not found at {db_path}")
            return []

        top_doc_ids = []
        conn = sqlite3.connect(db_path)
        try:
            # Try single_doc_results first (Average Score)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='single_doc_results'"
            )
            if cursor.fetchone():
                cursor = conn.execute(
                    """
                    SELECT doc_id, AVG(score) as avg_score 
                    FROM single_doc_results 
                    GROUP BY doc_id 
                    ORDER BY avg_score DESC 
                    LIMIT ?
                    """,
                    (limit,)
                )
                rows = cursor.fetchall()
                if rows:
                    top_doc_ids = [row[0] for row in rows]
                    self.logger.info(f"Selected top {len(top_doc_ids)} reports based on Single Doc scores.")

            # If no single doc results, try pairwise (Elo)
            if not top_doc_ids:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='pairwise_results'"
                )
                if cursor.fetchone():
                    # Simple Elo calculation (simplified version of what's in api.py)
                    ratings = {}
                    cursor = conn.execute(
                        "SELECT doc_id_1, doc_id_2, winner_doc_id FROM pairwise_results"
                    )
                    for doc1, doc2, winner in cursor.fetchall():
                        ratings.setdefault(doc1, 1000.0)
                        ratings.setdefault(doc2, 1000.0)
                        r1, r2 = ratings[doc1], ratings[doc2]
                        e1 = 1.0 / (1.0 + 10.0 ** ((r2 - r1) / 400.0))
                        e2 = 1.0 - e1
                        s1 = 1.0 if winner == doc1 else 0.0
                        s2 = 1.0 if winner == doc2 else 0.0
                        # Handle ties if any (though schema implies strict winner)
                        
                        k = 32.0
                        ratings[doc1] = r1 + k * (s1 - e1)
                        ratings[doc2] = r2 + k * (s2 - e2)
                    
                    sorted_ratings = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
                    top_doc_ids = [doc_id for doc_id, _ in sorted_ratings[:limit]]
                    self.logger.info(f"Selected top {len(top_doc_ids)} reports based on Elo ratings.")

        except Exception as e:
            self.logger.error(f"Error querying database: {e}")
        finally:
            conn.close()

        # Resolve doc_ids to full paths
        resolved_paths = []
        for doc_id in top_doc_ids:
            # doc_id is typically the filename
            full_path = os.path.join(output_folder, doc_id)
            if os.path.exists(full_path):
                resolved_paths.append(full_path)
            else:
                # Try finding it if it's just a prefix or slightly different
                # But usually doc_id IS the filename in llm-doc-eval
                self.logger.warning(f"Could not find file for doc_id: {doc_id} at {full_path}")
        
        return resolved_paths

    async def combine(self, report_paths: List[str], instructions_path: str, output_dir: str) -> List[str]:
        """
        Combine the provided reports into new 'Gold Standard' candidates.
        
        Args:
            report_paths (List[str]): List of paths to the top 2 reports.
            instructions_path (str): Path to the original instructions file.
            output_dir (str): Directory to save the combined reports.
            
        Returns:
            List[str]: Paths to the generated combined reports.
        """
        if not self.enabled:
            self.logger.info("Combiner is disabled in config.")
            return []

        if len(report_paths) < 2:
            self.logger.warning("Not enough reports to combine. Need at least 2.")
            return []

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Load contents
        try:
            report_a_content = self._load_file_content(report_paths[0])
            report_b_content = self._load_file_content(report_paths[1])
            original_instructions = self._load_file_content(instructions_path)
            combine_instructions = self._load_file_content(self.combine_instructions_path)
        except Exception as e:
            self.logger.error(f"Error loading assets for combination: {e}")
            return []

        # Construct the prompt
        # Structure: [Combine Instructions] + [Original Instructions] + [Report A] + [Report B]
        prompt_content = (
            f"{combine_instructions}\n\n"
            f"--- ORIGINAL INSTRUCTIONS ---\n{original_instructions}\n\n"
            f"--- REPORT A ---\n{report_a_content}\n\n"
            f"--- REPORT B ---\n{report_b_content}\n\n"
            f"--- END OF INPUTS ---\n"
            f"Please generate the combined Gold Standard report now."
        )

        generated_files = []

        if not self.models:
            self.logger.warning("No models configured for combination.")
            return []

        # Create temp files for FPF
        tmp_input_path = None
        tmp_instr_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp_input:
                tmp_input.write(prompt_content)
                tmp_input_path = tmp_input.name
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp_instr:
                tmp_instr.write("You are an expert editor. Please generate the combined report as requested in the input file.")
                tmp_instr_path = tmp_instr.name

            for idx, model_cfg in enumerate(self.models):
                if not model_cfg or not model_cfg.get('model'):
                    self.logger.warning(f"Skipping model entry {idx}: No model configuration found.")
                    continue

                provider = model_cfg.get('provider', 'openai')
                model_name = model_cfg.get('model')
                label = f"{provider}_{model_name}".replace(":", "_").replace("/", "_")
                
                self.logger.info(f"Generating combined report with {label} ({provider}/{model_name})...")

                try:
                    options = {
                        "provider": provider,
                        "model": model_name,
                        "json": False
                    }
                    
                    # Call FPF
                    results = await fpf_runner.run_filepromptforge_runs(
                        file_a_path=tmp_instr_path,
                        file_b_path=tmp_input_path,
                        num_runs=1,
                        options=options
                    )

                    if results:
                        src_path, _ = results[0]
                        
                        # Save the file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"Combined_{label}_{timestamp}.md"
                        filepath = os.path.join(output_dir, filename)
                        
                        shutil.copy2(src_path, filepath)
                        
                        generated_files.append(filepath)
                        self.logger.info(f"Saved combined report to: {filepath}")
                    else:
                        self.logger.error(f"Failed to get response from {label}")

                except Exception as e:
                    self.logger.error(f"Error generating with {label}: {e}")
        
        finally:
            # Cleanup temp files
            if tmp_input_path and os.path.exists(tmp_input_path):
                try:
                    os.remove(tmp_input_path)
                except Exception:
                    pass
            if tmp_instr_path and os.path.exists(tmp_instr_path):
                try:
                    os.remove(tmp_instr_path)
                except Exception:
                    pass

        return generated_files
