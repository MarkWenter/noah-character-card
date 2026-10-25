"""NDSL v1: indentation-based static definitions and safe template specialization."""
import copy
import json
import re
from .catalog import BUILTINS
from .model import validate_definition,validate_template
from .expression import RuleError
from .io import loads_json

DEF_KEYS={'ID':'id','名称':'name','类型':'kind','分类':'categories','标签':'tags','数据类型':'value_type','默认值':'default','最小值':'min','最大值':'max','最小层数':'min','最大层数':'max','可叠加':'stackable','可驱散':'dispellable','描述':'description','字段':'fields','显示':'display'}

def scalar(text):
    text=text.strip()
    if not text: return {}
    try:
        if text[0] in '[{"' or text in ['true','false','null'] or re.fullmatch(r'-?\d+(\.\d+)?([eE][+-]?\d+)?',text): return loads_json(text)
    except (ValueError,RecursionError) as exc: raise RuleError('无效JSON值：'+text[:100]) from exc
    return text

def parse_ndsl(source):
    if not isinstance(source,str) or len(source)>100000: raise RuleError('NDSL文档最多100000字')
    records=[]; stack=[]
    for line_no,raw in enumerate(source.splitlines(),1):
        if not raw.strip() or raw.lstrip().startswith('#'): continue
        if '\t' in raw: raise RuleError(f'第{line_no}行：请使用空格缩进，不要使用Tab')
        indent=len(raw)-len(raw.lstrip(' ')); line=raw.strip()
        top=re.fullmatch(r'(定义词|定义节点)\s+(.+?)[：:]',line)
        if indent==0:
            if not top: raise RuleError(f'第{line_no}行：需要“定义词 名称:”或“定义节点 名称:”')
            root={}; records.append((top[1],top[2],root)); stack=[(0,root)]; continue
        if not stack or indent%4: raise RuleError(f'第{line_no}行：缩进须为4个空格的倍数')
        parts=re.split(r'[:：]',line,maxsplit=1)
        if len(parts)!=2 or not parts[0].strip(): raise RuleError(f'第{line_no}行：字段需写为 名称: 值')
        while stack and indent<=stack[-1][0]: stack.pop()
        if not stack or indent!=stack[-1][0]+4: raise RuleError(f'第{line_no}行：缩进层级不正确')
        container=stack[-1][1]; key=parts[0].strip()
        if key in container: raise RuleError(f'第{line_no}行：重复字段 {key}')
        value=scalar(parts[1]); container[key]=value
        if not parts[1].strip(): stack.append((indent,value))
    definitions=[]; nodes=[]
    for kind,name,raw in records:
        if kind=='定义词':
            unknown=set(raw)-set(DEF_KEYS)
            if unknown: raise RuleError('定义词不支持动态字段或未知字段：'+','.join(unknown))
            obj={DEF_KEYS[k]:v for k,v in raw.items()}; obj.setdefault('name',name); obj.setdefault('kind','Custom')
            if 'id' not in obj: raise RuleError('定义词必须声明ID')
            obj['value_type']=str(obj.get('value_type','integer')).lower()
            for field in ['categories','tags']:
                if field in obj and isinstance(obj[field],str): obj[field]=[v.strip() for v in re.split('[,，]',obj[field]) if v.strip()]
            if 'fields' in obj:
                fields={}
                for key,spec in obj['fields'].items():
                    if not isinstance(spec,dict): raise RuleError('字段必须包含数据类型与默认值')
                    mapping={'类型':'type','数据类型':'type','默认值':'default','最小值':'min','最大值':'max'}
                    if set(spec)-set(mapping): raise RuleError('数据字段存在未知声明')
                    fields[key]={mapping[k]:v for k,v in spec.items()}; fields[key]['type']=str(fields[key].get('type','')).lower()
                obj['fields']=fields
            validate_definition(obj); definitions.append(obj)
        else:
            allowed={'ID','模板','类型','输入','输出','参数','左值','右值','比较','描述'}
            if set(raw)-allowed: raise RuleError('未知节点声明：'+','.join(set(raw)-allowed))
            base=next((v for v in BUILTINS.values() if raw.get('模板') in (v['id'],v['name'])),None)
            if base is None: raise RuleError('模板必须引用内置节点ID或名称')
            obj=copy.deepcopy(base); obj.update({'id':raw.get('ID',''),'name':name,'kind':raw.get('类型',base['kind']),'description':raw.get('描述','')})
            for source_key,key in [('输入','inputs'),('输出','outputs')]:
                if source_key in raw: obj[key]=raw[source_key]
            if '参数' in raw:
                if not isinstance(raw['参数'],dict): raise RuleError('参数必须为字段对象')
                obj['params'].update(raw['参数'])
            for source_key,key in [('左值','a'),('右值','b')]:
                if source_key in raw:
                    value=raw[source_key]; obj['params'][key]={'expr':value} if isinstance(value,str) else value
            if '比较' in raw: obj['params']['op']=raw['比较']
            validate_template(obj); nodes.append(obj)
    if not records: raise RuleError('NDSL没有任何声明')
    for values in [definitions,nodes]:
        if len({v['id'] for v in values})!=len(values): raise RuleError('NDSL包含重复ID')
    return {'definitions':definitions,'node_templates':nodes}


def dump_definition(d):
    lines=['定义词 '+d['name']+':']
    mapping={v:k for k,v in DEF_KEYS.items() if k not in ['名称','最小层数','最大层数']}
    for key,value in d.items():
        if key=='name': continue
        if key=='fields':
            lines.append('    字段:')
            for name,spec in value.items():
                lines.append('        '+name+':')
                for field,val in spec.items(): lines.append('            '+{'type':'数据类型','default':'默认值','min':'最小值','max':'最大值'}[field]+': '+json.dumps(val,ensure_ascii=False))
        else: lines.append('    '+mapping[key]+': '+json.dumps(value,ensure_ascii=False))
    return '\n'.join(lines)


def dump_template(t):
    base=next(v['id'] for v in BUILTINS.values() if v['op']==t['op'])
    return '\n'.join(['定义节点 '+t['name']+':','    ID: '+t['id'],'    模板: '+base,'    类型: '+t['kind'],'    输入: '+json.dumps(t['inputs'],ensure_ascii=False),'    输出: '+json.dumps(t['outputs'],ensure_ascii=False),'    参数: '+json.dumps(t['params'],ensure_ascii=False),'    描述: '+json.dumps(t.get('description',''),ensure_ascii=False)])
