"""Portable, isolated RTL regression; no installation or remote execution."""
from pathlib import Path
import argparse
import datetime
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--iverilog', default='iverilog')
    ap.add_argument('--vvp', default='vvp')
    args = ap.parse_args()
    iv, vv = shutil.which(args.iverilog), shutil.which(args.vvp)
    if not iv or not vv:
        ap.error('Icarus Verilog and vvp must already be installed')
    out = args.out.resolve()
    if out.exists() or out == ROOT or out in ROOT.parents:
        ap.error('output must be a new, dedicated directory')
    out.mkdir(parents=True)
    # Historical testbenches write build/*.vcd and build/*_trace.log.
    # Keep these artifacts in the new output directory, not the source tree.
    (out/'build').mkdir()
    status = dict(state='running', scope='RTL functional regression only',
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), tests={})
    report = out/'verification.json'
    def save():
        report.write_text(json.dumps(status, indent=2)+'\n', encoding='utf-8')
    save()
    try:
        rtl = [str(p) for p in sorted((ROOT/'rtl/rtl').glob('*.sv'))]
        cases = [('tool_smoke', 'tb_tool_smoke', []), ('switch', 'tb_switch', []),
                 ('aux_router', 'tb_aux_router', []), ('transition', 'tb_transition', []),
                 ('timeout', 'tb_transition', ['+FAIL_MODE']), ('management', 'tb_management', [])]
        for name, top, flags in cases:
            image = out/(name+'.vvp')
            cmd = [iv, '-g2012', '-Wall', '-s', top, '-o', str(image)] + rtl + [str(ROOT/'rtl/tb'/(top+'.sv'))]
            cp = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=180)
            (out/(name+'.compile.log')).write_text(cp.stdout+cp.stderr, encoding='utf-8')
            if cp.returncode:
                raise RuntimeError(name + ': compilation failed')
            run = subprocess.run([vv, str(image)] + flags, cwd=out, capture_output=True, text=True, timeout=300)
            log = run.stdout+run.stderr
            (out/(name+'.run.log')).write_text(log, encoding='utf-8')
            passed = run.returncode == 0 and 'PASS '+name in log and 'FATAL' not in log
            status['tests'][name] = dict(passed=passed, compile_returncode=cp.returncode,
                                         simulation_returncode=run.returncode, output=log.strip())
            save()
            print(name+': '+('PASS' if passed else 'FAIL'), flush=True)
            if not passed:
                raise RuntimeError(name + ': functional regression failed')
        # Prove that a broken compiler invocation cannot silently pass.
        cp = subprocess.run([iv, '-g2012', '-s', 'tb_tool_invalid', '-o', str(out/'invalid.vvp'),
                             str(ROOT/'rtl/negative/invalid.sv')], capture_output=True, text=True, timeout=30)
        assert cp.returncode != 0 and 'syntax error' in cp.stderr
        status.update(state='passed', negative_compile_rejected=True)
    except BaseException as error:
        status.update(state='failed', reason=repr(error))
        raise
    finally:
        save()

if __name__ == '__main__':
    main()
