"""Compatibility CLI for frequency-domain zALFF on already aligned images."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'bakend'))
if __name__=='__main__':
    from app.execution.image_summary_worker import main
    sys.argv.extend(['--operation','zalff'])
    main()
