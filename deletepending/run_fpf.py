#!/usr/bin/env python3
"""
Launcher for FilePromptForge that ensures the repository root is on sys.path
and runs the FilePromptForge.fpf_main module so package-relative
imports resolve correctly when invoked from a subprocess.
Usage: python -u API_Cost_Multiplier/scripts/run_fpf.py --config <fpf_config.yaml> --file-a <instructions.txt> --file-b <input.md> --out <out.txt> [--env <.env>] [--provider <name>] [--model <id>]
"""
import os
import sys
import runpy

# Compute project root (parent of API_Cost_Multiplier)
scripts_dir = os.path.dirname(os.path.abspath(__file__))  # .../API_Cost_Multiplier/scripts
api_dir = os.path.dirname(scripts_dir)                    # .../API_Cost_Multiplier
project_root = os.path.dirname(api_dir)                   # .../ (repo root)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set argv so the module sees the passed CLI args
# First element is the module name to mimic python -m behavior
sys.argv = ["FilePromptForge.fpf_main"] + sys.argv[1:]

# Run the module as __main__
runpy.run_module("FilePromptForge.fpf_main", run_name="__main__")
