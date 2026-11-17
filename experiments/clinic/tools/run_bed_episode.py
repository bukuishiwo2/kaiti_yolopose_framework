"""Deprecated module alias: the implementation lives in support.clinic_runtime.episode.
Original accepted source is preserved in runs/*/source and the convergence snapshot.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from support.clinic_runtime.episode import Bot, Episode, main
if __name__=='__main__':
    import os
    cli=str(Path(__file__).resolve().parents[1]/'clinic_experiment.sh')
    os.execv(cli,[cli,'episode',*sys.argv[1:]])
