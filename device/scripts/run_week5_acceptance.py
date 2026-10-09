"""Log the real Week 5 acceptance checks and regressions without device access."""
import argparse
from pathlib import Path
import os
from run_week5_preparation import ROOT, PYTHON, run

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--preparation',type=Path,required=True)
    p.add_argument('--stage',choices=['regression','recheck','accept','tests'],required=True)
    a = p.parse_args()
    session = a.session.resolve()
    env = os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH'): env.pop(key,None)
    env['PYTHONIOENCODING'] = 'utf-8'
    def py(name, script, *args, optimized=False):
        run(session,name,[str(PYTHON),'-B',*(['-O'] if optimized else []),str(ROOT/script),*map(str,args)],env)
    if a.stage == 'regression':
        for opt in (False,True):
            suffix = '-O' if opt else ''
            py('package-preflight'+suffix,'device/scripts/verify_week5_package.py','--preparation',a.preparation,optimized=opt)
            for name,script,args in [
                ('current-gate','ml/scripts/verify_week4_current.py',['--compiler','C:/msys64/ucrt64/bin/gcc.exe']),
                ('current-policy','ml/scripts/test_week4_current.py',[]),
                ('handoff-policy','device/scripts/test_week4_handoff.py',[]),
                ('python-quantization','ml/scripts/test_week5_quantization.py',[]),
                ('historical-capture','device/scripts/check_week4_capture.py',['--capture','results/week4/logs/week4_capture.txt',
                    '--report',session/('historical-capture'+suffix+'.json'),'--bench-sample','0','--mixed-order'])]:
                py(name+suffix,script,*args,optimized=opt)
            py('parser-regression'+suffix,'device/scripts/test_week5_capture.py','--output',session/('parser-regression'+suffix),
               '--host',a.preparation.parent/'evidence/host',optimized=opt)
    elif a.stage == 'recheck':
        for opt in (False,True):
            suffix = '-O' if opt else ''
            py('real-mcu-recheck'+suffix,'device/scripts/check_week5_capture.py','--capture',session/'week5_capture.txt',
               '--collection-receipt',session/'week5_capture.receipt.json','--report',
               session/('week5_mcu_recheck_O.json' if opt else 'week5_mcu_recheck.json'),optimized=opt)
    elif a.stage == 'accept':
        for opt in (False,True):
            py('technical-acceptance'+('-O' if opt else ''),'device/scripts/accept_week5_mcu.py','--session',session,
               '--preparation',a.preparation,'--output',session/('acceptance-O' if opt else 'acceptance'),optimized=opt)
    else:
        for opt in (False,True):
            py('acceptance-negative-tests'+('-O' if opt else ''),'device/scripts/test_week5_acceptance.py','--session',session,
               '--preparation',a.preparation,'--output',session/('acceptance-tests-O.json' if opt else 'acceptance-tests.json'),optimized=opt)

if __name__ == '__main__': main()
