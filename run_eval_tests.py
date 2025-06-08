import subprocess
import os
import sys

# Get the directory of the current script (run_eval_tests.py)
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to cli.py relative to script_dir
cli_path = os.path.join(script_dir, 'llm-doc-eval', 'cli.py')

# Construct the path to the test data relative to script_dir
test_data_path = os.path.join(script_dir, 'test', 'finaldocs')

# Command to execute the llm-doc-eval CLI
command = [
    sys.executable, # Use the current Python executable
    cli_path,
    'run-all-evaluations',
    test_data_path
]

print(f"Executing command: {' '.join(command)}")

# Execute the command
try:
    process = subprocess.Popen(command, stdout=None, stderr=None)
    process.wait() # Wait for the process to terminate

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)

except subprocess.CalledProcessError as e:
    print(f"Command failed with exit code {e.returncode}")
    sys.exit(e.returncode)