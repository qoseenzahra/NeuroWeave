"""Compatibility CLI for the reviewed MNE implementation.

Use --operation for an individual analysis. Legacy --resting selects continuous
cleaning; event-related analyses require explicit --events through --operation.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'bakend'))

if __name__=='__main__':
    from app.execution.eeg_worker import main
    args=sys.argv[1:]
    resting='--resting' in args
    args=[a for a in args if a!='--resting']
    if '--operation' not in args:args+=['--operation','clean' if resting else 'inspect']
    if '--output-dir' not in args:args+=['--output-dir','eeg_output']
    main(args)
