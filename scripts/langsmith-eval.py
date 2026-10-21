#!/usr/bin/env python3
"""Run from any directory, using the optional LangSmith environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AgentEval'))
from experiments.langsmith_eval import main

if __name__ == '__main__':
    raise SystemExit(main())
