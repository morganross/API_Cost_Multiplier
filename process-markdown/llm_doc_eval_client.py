import subprocess
import re
import os
import shutil # Import shutil for rmtree
import uuid # Import uuid for unique directory names

def evaluate_reports(report_paths):
    """
    Executes the llm-doc-eval CLI command to evaluate reports and identifies the best report.
    It creates a temporary directory, copies the reports into it, and passes the directory path
    to llm-doc-eval's run-pairwise command.
    """
    # Create a temporary directory for the reports to be evaluated
    temp_eval_dir = os.path.join("temp_llm_eval_reports", str(uuid.uuid4()))
    os.makedirs(temp_eval_dir, exist_ok=True)
    
    copied_report_paths = []
    try:
        # Copy reports to the temporary directory
        for report_path in report_paths:
            shutil.copy(report_path, temp_eval_dir)
            copied_report_paths.append(os.path.join(temp_eval_dir, os.path.basename(report_path)))

        # Construct the command for pairwise evaluation, passing the temporary directory
        # Ensure cli_script_path is an absolute path
        cli_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'llm-doc-eval', 'cli.py'))
        # Ensure temp_eval_dir is an absolute path
        abs_temp_eval_dir = os.path.abspath(temp_eval_dir)
        command = ["python", cli_script_path, "run-all-evaluations", abs_temp_eval_dir]
        
        print(f"Running llm-doc-eval command: {' '.join(command)}")
        
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True  # Raise an exception for non-zero exit codes
        )
        output = process.stdout
        error_output = process.stderr # Capture stderr as well
        print(f"llm-doc-eval stdout:\n{output}")
        if error_output:
            print(f"llm-doc-eval stderr:\n{error_output}") # Print stderr if present
        
        # Parse the output to find the best report path
        # The output from summary-pairwise typically looks like:
        # "full path and filename of file with highest elo: /path/to/best_report.md"
        
        match = re.search(r"full path and filename of file with highest elo: (.+)", output)
        if match:
            best_report_path_temp = match.group(1).strip()
            
            # The best_report_path_temp is within the temporary directory.
            # We need to map it back to the original report_paths to return the correct one.
            # This assumes the filenames are preserved.
            best_report_filename = os.path.basename(best_report_path_temp)
            original_best_report_path = next((p for p in report_paths if os.path.basename(p) == best_report_filename), None)
            
            if original_best_report_path:
                print(f"Identified best report: {original_best_report_path}")
                return original_best_report_path
            else:
                raise Exception(f"Could not map best report filename '{best_report_filename}' back to original paths.")
        else:
            # If the expected pattern is not found, raise an error with the full output for debugging.
            raise Exception(f"Could not identify best report from llm-doc-eval output. Full stdout:\n{output}\nFull stderr:\n{error_output}")

    except subprocess.CalledProcessError as e:
        print(f"Error running llm-doc-eval: {e.stderr}")
        raise Exception(f"llm-doc-eval failed with error: {e.stderr}")
    except FileNotFoundError:
        print(f"Error: llm-doc-eval cli.py not found at {cli_script_path}. Ensure it's correctly installed or path is correct.")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during llm-doc-eval: {e}")
        raise
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_eval_dir):
            shutil.rmtree(temp_eval_dir)
            print(f"Cleaned up temporary evaluation directory: {temp_eval_dir}")

if __name__ == "__main__":
    # This part is for testing the client in isolation.
    
    # Dummy report paths for testing
    # These paths should exist for a successful test run of llm-doc-eval
    dummy_report_paths = [
        "gptr-eval-process/test/finaldocs/report1.md",
        "gptr-eval-process/test/finaldocs/report2.md",
        "gptr-eval-process/test/finaldocs/report3.md",
    ]

    # Create dummy files if they don't exist for testing purposes
    for path in dummy_report_paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"# Dummy Report for {os.path.basename(path)}\n\nThis is a dummy report content.")

    print(f"Evaluating reports: {dummy_report_paths}")
    try:
        best_report = evaluate_reports(dummy_report_paths)
        print(f"The best report is: {best_report}")
    except Exception as e:
        print(f"Failed to evaluate reports: {e}")
    finally:
        # Clean up dummy files after testing
        for path in dummy_report_paths:
            if os.path.exists(path):
                os.remove(path)
        # Remove dummy directories if empty
        for path in dummy_report_paths:
            try:
                os.removedirs(os.path.dirname(path))
            except OSError:
                pass # Directory might not be empty or already removed