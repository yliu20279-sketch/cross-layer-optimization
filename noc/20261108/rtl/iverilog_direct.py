"""Invoke real Icarus preprocessor and elaborator without the Windows shell driver.

Configuration keys follow v13_0 driver/main.c, not a replacement HDL model.
Every subprocess must return zero; a produced file alone is never accepted.
"""
from pathlib import Path
import hashlib,subprocess

def compile_sv(iverilog,top,sources,image):
    lib=Path(iverilog).resolve().parent.parent/'lib/ivl'
    preprocessor=lib/'ivlpp.exe'
    compiler=lib/'ivl.exe'
    stem=Path(image).stem
    pp=Path('build')/(stem+'.preprocessed.sv')
    defines=Path('build')/(stem+'.defines')
    config=Path('build')/(stem+'.conf')
    defines.write_text('D:__ICARUS__=1\n',encoding='ascii')
    pp_cmd=[str(preprocessor),'-L','-F',str(defines),'-o',str(pp)]+sources
    p=subprocess.run(pp_cmd,capture_output=True,text=True,errors='replace',timeout=120)
    if p.returncode:raise RuntimeError(f'ivlpp failed ({p.returncode}): {p.stderr}')
    lines=[f'root:{top}',f'basedir:{lib.as_posix()}']
    for plugin in ('system','vhdl_sys','vhdl_textio','v2005_math','va_math','v2009'):
        lines.append(f'module:{(lib/(plugin+".vpi")).as_posix()}')
    for generation in ('2012','no-specify','no-interconnect','assertions','xtypes','io-range-error',
                       'no-strict-ca-eval','no-strict-expr-width','shared-loop-index','no-verilog-ams','icarus-misc'):
        lines.append('generation:'+generation)
    lines += ['warnings:nidRpsta','ignore_missing_modules:false',f'out:{image}','iwidth:32','widthcap:65536']
    config.write_text('\n'.join(lines)+'\n',encoding='ascii')
    cmd=[str(compiler),'-C',str(config),'-C',str(lib/'vvp.conf'),str(pp)]
    c=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=180)
    log=p.stdout+p.stderr+c.stdout+c.stderr
    metadata={'preprocessor_command':pp_cmd,'compile_command':cmd,'ivlpp_returncode':p.returncode,
              'ivl_returncode':c.returncode,'config':config.as_posix(),'preprocessed':pp.as_posix(),
              'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
              'preprocessed_sha256':hashlib.sha256(pp.read_bytes()).hexdigest()}
    return c.returncode,log,metadata
