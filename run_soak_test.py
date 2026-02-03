#!/usr/bin/env python3
"""Run soak test from repo root: python run_soak_test.py"""
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent
mortal_agent = repo_root / "mortal_agent"
tools = mortal_agent / "tools"
sys.path.insert(0, str(mortal_agent))
sys.path.insert(0, str(tools))
from soak_test import main
if __name__ == "__main__":
    sys.exit(main())
