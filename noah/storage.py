"""Versioned, bounded data files. No pickle, eval, macros or executable imports."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from .domain import CardError, validate

MAX_BYTES=2*1024*1024

def _reject_constant(value):
    raise CardError('不允许非有限数值')

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise CardError('JSON 中存在重复字段')
        result[key]=value
    return result

def load(path):
    path=Path(path)
    try:
        with path.open('rb') as stream: raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise CardError('文件超过2MB限制')
        text=raw.decode('utf-8-sig')
        if text.lstrip().startswith('<'): raise CardError('新版仅支持JSON人物卡，不支持XML')
        card=json.loads(text,parse_constant=_reject_constant,object_pairs_hook=_pairs)
        return validate(card)
    except CardError: raise
    except (OSError,UnicodeError,ValueError,RecursionError) as exc:
        raise CardError(f'无法读取人物卡：{exc}') from exc

def save(path,card):
    validate(card); path=Path(path); temporary=None
    try:
        if path.suffix.lower()=='.xml': raise CardError('请保存为.json，XML已停用')
        data=json.dumps(card,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        if len(data)>MAX_BYTES: raise CardError('人物卡超过2MB限制')
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if path.exists(): shutil.copy2(path,path.with_name(path.name+'.bak'))
        os.replace(temporary,path); temporary=None
    except CardError: raise
    except (OSError,ValueError) as exc: raise CardError(f'保存失败，原文件未被替换：{exc}') from exc
    finally:
        if temporary is not None:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass
