#!/bin/bash
# Momahub Cookbook Batch Runner Wrapper
# This script calls the Python-based orchestrator.

# Ensure we are in the cookbook directory
cd "$(dirname "$0")"

# Run the Python orchestrator
python3 run_all.py
