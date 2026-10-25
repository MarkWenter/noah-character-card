"""Bounded JSON resource files with duplicate-key rejection and atomic replacement."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from .expression import RuleError
from .model import safe_data

def pairs(values):
    result={}
    for key,value in values:
        if key in result: raise RuleError('JSON重复字段：'+key)
        result[key]=value
    return result

def constant(value): raise RuleError('不允许NaN或Infinity')
def loads_json(text): return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)

def read_json(path,limit=2*1024*1024):
    try:
        with Path(path).open('rb') as stream: data=stream.read(limit+1)
        if len(data)>limit: raise RuleError('资源文件超过大小限制')
        result=loads_json(data.decode('utf-8-sig')); safe_data(result); return result
    except RuleError: raise
    except (OSError,ValueError,RecursionError) as exc: raise RuleError('无法读取资源JSON：'+str(exc)) from exc

def write_json(path,value,limit=2*1024*1024):
    temporary=None; path=Path(path)
    try:
        safe_data(value); data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        if len(data)>limit: raise RuleError('导出的资源超过大小限制')
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name,suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if path.exists(): shutil.copy2(path,path.with_name(path.name+'.bak'))
        os.replace(temporary,path); temporary=None
    except RuleError: raise
    except (OSError,ValueError,RecursionError) as exc: raise RuleError('资源导出失败：'+str(exc)) from exc
    finally:
        if temporary is not None:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass
