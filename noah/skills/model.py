"""Versioned embedded resources and typed graph validation, independent of Tkinter."""
import copy
import json
import re
from .catalog import BUILTINS,PORT_TYPES,DEFINITION_KINDS,templates,compatible
from .expression import RuleError,parse_expression

ID=re.compile(r'^[\w][\w.-]{0,100}$',re.UNICODE)

def empty_bundle(): return {'version':1,'definitions':[],'node_templates':[],'shared_rules':[],'skills':[]}
def new_graph(id,name,kind='skill'): return {'id':id,'name':name,'kind':kind,'enabled':True,'inputs':{},'outputs':{},'nodes':[],'edges':[]}
def new_skill(id,name,graph_id=''): return {'id':id,'name':name,'type':'active','description':'','cost':'','cooldown':'','graph_id':graph_id,'enabled':True,'references':[]}

def text(value,label,limit=30000):
    if not isinstance(value,str) or len(value)>limit: raise RuleError(label+'必须为有效文本')
def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value): raise RuleError('无效ID：'+str(value)[:120])
def shape(obj,required,optional=()):
    if not isinstance(obj,dict) or not set(required)<=set(obj) or set(obj)-set(required)-set(optional): raise RuleError('字段缺失或不受支持：'+str(set(obj) if isinstance(obj,dict) else type(obj).__name__)[:200])
def safe_data(value,depth=0):
    if depth>16: raise RuleError('规则数据嵌套过深')
    if isinstance(value,dict):
        if len(value)>256 or any(not isinstance(k,str) or len(k)>120 for k in value): raise RuleError('字段过多或字段名过长')
        for v in value.values(): safe_data(v,depth+1)
        if set(value)=={'expr'}: parse_expression(value['expr'])
    elif isinstance(value,list):
        if len(value)>1024: raise RuleError('列表过长')
        for v in value: safe_data(v,depth+1)
    elif isinstance(value,str): text(value,'文本')
    elif type(value) in (int,float):
        if not -1e9<=value<=1e9: raise RuleError('规则数值超出范围或不是有限数值')
    elif type(value) is bool or value is None: pass
    else: raise RuleError('规则只允许JSON数据')

def validate_definition(d):
    shape(d,{'id','name','kind'}, {'categories','tags','value_type','default','min','max','stackable','dispellable','description','fields','display'})
    identifier(d['id']); text(d['name'],'名称',200)
    if 'description' in d: text(d['description'],'定义词描述')
    if not d['name'].strip() or d['kind'] not in DEFINITION_KINDS: raise RuleError('定义词名称或类别无效')
    kind=d.get('value_type','integer')
    if kind not in {'integer','number','boolean','string','object'}: raise RuleError('定义词数据类型不支持')
    default=d.get('default',{'integer':0,'number':0,'boolean':False,'string':'','object':{}}[kind])
    check={'integer':lambda x:type(x) is int,'number':lambda x:type(x) in (int,float),'boolean':lambda x:type(x) is bool,'string':lambda x:isinstance(x,str),'object':lambda x:isinstance(x,dict)}[kind]
    if not check(default): raise RuleError('默认值与定义词数据类型不一致')
    for name in ['min','max']:
        if name in d and (kind not in {'integer','number'} or type(d[name]) not in (int,float)): raise RuleError('最小/最大值只能用于数值定义词')
    if kind in {'integer','number'} and not d.get('min',-1e9)<=default<=d.get('max',1e9): raise RuleError('定义词默认值超出约束')
    for name in ['stackable','dispellable']:
        if name in d and type(d[name]) is not bool: raise RuleError(name+'必须为布尔值')
    if d['kind']=='Status' and (kind!='integer' or d.get('min',0)<0): raise RuleError('首版状态必须是非负整数层数')
    if kind=='integer' and any(type(d[k]) is not int for k in ['min','max'] if k in d): raise RuleError('整数约束必须为整数')
    if d['kind'] in {'Attribute','Resource'} and kind not in {'integer','number'}: raise RuleError('属性和资源必须为数值类型')
    for name in ['categories','tags']:
        if name in d and (not isinstance(d[name],list) or any(not isinstance(v,str) for v in d[name])): raise RuleError('分类和标签必须是文本列表')
    if 'fields' in d:
        if not isinstance(d['fields'],dict): raise RuleError('数据字段必须为对象')
        for field,spec in d['fields'].items():
            identifier(field); shape(spec,{'type','default'},{'min','max'})
            validate_definition({'id':field,'name':field,'kind':'Custom','value_type':spec['type'],**{k:v for k,v in spec.items() if k!='type'}})
    safe_data(d)
    # Static definitions have no expressions or hidden executable hooks anywhere.
    def static(value):
        if isinstance(value,dict):
            if 'expr' in value: raise RuleError('定义词只允许静态数据，动态表达式属于节点图')
            for v in value.values(): static(v)
        elif isinstance(value,list):
            for v in value: static(v)
    static(d); return d

def validate_template(t):
    shape(t,{'id','name','kind','op','inputs','outputs','params'},{'description'})
    identifier(t['id']); text(t['name'],'模板名称',200)
    if 'description' in t: text(t['description'],'模板描述')
    if t['op'] not in {v['op'] for v in BUILTINS.values()} or t['kind'] not in {'Event','Condition','Data','Math','Effect','Control','Rule'}: raise RuleError('节点操作或类别不支持')
    for name in ['inputs','outputs']:
        if not isinstance(t[name],dict) or len(t[name])>24: raise RuleError('节点端口过多')
        for port,kind in t[name].items():
            identifier(port)
            if kind not in PORT_TYPES: raise RuleError('未知端口类型：'+str(kind))
    if not isinstance(t['params'],dict): raise RuleError('参数必须为对象')
    safe_data(t)
    if t['op']=='calculate': parse_expression(t['params'].get('expression','a + b'))
    return t

def cycle_check(nodes,edges,label):
    adjacency={n:[] for n in nodes}
    for source,target in edges: adjacency[source].append(target)
    seen=set(); active=set()
    def visit(node):
        if node in active: raise RuleError(label+'存在循环；请用事件连锁或子图代替直接回连')
        if node in seen: return
        active.add(node)
        for child in adjacency[node]: visit(child)
        active.remove(node); seen.add(node)
    for node in nodes: visit(node)

def validate_graph(graph,registry):
    shape(graph,{'id','name','kind','enabled','nodes','edges'},{'inputs','outputs'})
    identifier(graph['id']); text(graph['name'],'图名称',200)
    if graph['kind'] not in {'skill','shared','scene'} or type(graph['enabled']) is not bool: raise RuleError('规则图类别或开关错误')
    for key in ['inputs','outputs']:
        ports=graph.get(key,{})
        if not isinstance(ports,dict) or len(ports)>24: raise RuleError('子图接口格式错误')
        for name,kind in ports.items():
            identifier(name)
            if kind not in PORT_TYPES or kind=='Flow': raise RuleError('子图外部数据接口类型错误')
    if not isinstance(graph['nodes'],list) or len(graph['nodes'])>256 or not isinstance(graph['edges'],list) or len(graph['edges'])>512: raise RuleError('每张图最多256节点/512连线')
    nodes={}
    for n in graph['nodes']:
        shape(n,{'id','template','params','position'}); identifier(n['id'])
        if n['id'] in nodes or n['template'] not in registry: raise RuleError('节点ID重复或模板不存在')
        if not isinstance(n['params'],dict) or not isinstance(n['position'],list) or len(n['position'])!=2 or any(type(x) not in (int,float) or not -100000<=x<=100000 for x in n['position']): raise RuleError('节点参数或位置不合法')
        template=registry[n['template']]
        if set(n['params'])-set(template['params'])-set(template['inputs']): raise RuleError('节点包含模板未声明的参数')
        safe_data(n['params']); nodes[n['id']]=n
    occupied=set(); pairs=[]; seen=set()
    for edge in graph['edges']:
        shape(edge,{'from','to','kind'})
        for key in ['from','to']:
            if not isinstance(edge[key],list) or len(edge[key])!=2 or any(not isinstance(v,str) for v in edge[key]): raise RuleError('连线端点格式错误')
        a,ap=edge['from']; b,bp=edge['to']
        if a not in nodes or b not in nodes: raise RuleError('连线指向缺失节点')
        left=registry[nodes[a]['template']]['outputs']; right=registry[nodes[b]['template']]['inputs']
        if ap not in left or bp not in right or not compatible(left[ap],right[bp]): raise RuleError('端口不存在或连线类型不兼容')
        expected='flow' if left[ap]=='Flow' else 'data'
        if edge['kind']!=expected: raise RuleError('执行流和数据流不可混连')
        identity=(a,ap,b,bp)
        if identity in seen: raise RuleError('重复连线')
        seen.add(identity)
        if expected=='data':
            if (b,bp) in occupied: raise RuleError('一个数据输入只能有一个来源')
            occupied.add((b,bp))
        pairs.append((a,b))
    cycle_check(nodes,pairs,'规则图')
    return graph

def validate_bundle(bundle):
    shape(bundle,{'version','definitions','node_templates','shared_rules','skills'})
    if type(bundle['version']) is not int or bundle['version']!=1: raise RuleError('技能资源版本不支持')
    limits={'definitions':256,'node_templates':128,'shared_rules':64,'skills':128}
    indexed={}
    for key,limit in limits.items():
        values=bundle[key]
        if not isinstance(values,list) or len(values)>limit: raise RuleError(key+'条目过多或格式错误')
        mapping={}
        for value in values:
            if not isinstance(value,dict) or 'id' not in value: raise RuleError('资源缺少ID')
            identifier(value['id'])
            if value['id'] in mapping: raise RuleError('重复资源ID：'+value['id'])
            mapping[value['id']]=value
        indexed[key]=mapping
    for d in bundle['definitions']: validate_definition(d)
    for t in bundle['node_templates']:
        if t['id'] in BUILTINS: raise RuleError('不能覆盖内置节点')
        validate_template(t)
    registry=templates(bundle); calls=[]
    for graph in bundle['shared_rules']:
        validate_graph(graph,registry)
        for node in graph['nodes']:
            p={**registry[node['template']]['params'],**node['params']}; op=registry[node['template']]['op']
            for key,collection in [('definition','definitions'),('tag','definitions'),('skill','skills'),('graph','shared_rules')]:
                ref=p.get(key,'')
                if not isinstance(ref,str) or (ref and ref not in indexed[collection] and not (collection=='definitions' and key=='definition' and ref in {'力量','敏捷','耐受','魅力','智力','感知','意志','HP','MP','TP'} and op in {'read_attribute','read_resource','change_resource','set_resource','event'})): raise RuleError('引用不存在：'+str(ref))
            d=indexed['definitions'].get(p.get('definition',''))
            expected={'apply_status':'Status','remove_status':'Status','read_status':'Status','change_resource':'Resource','set_resource':'Resource','read_resource':'Resource','set_attribute':'Attribute'}.get(op)
            if d and expected and d['kind']!=expected: raise RuleError('定义词类别不符合节点用途')
            if op=='call' and p.get('graph'): calls.append((graph['id'],p['graph']))
    for skill in bundle['skills']:
        shape(skill,{'id','name','type','description','graph_id','enabled'},{'cost','cooldown','references','initially_available'})
        text(skill['name'],'技能名称',200); text(skill['description'],'技能描述')
        if skill['type'] not in {'active','passive','reaction','permanent'} or type(skill['enabled']) is not bool: raise RuleError('技能类型或开关无效')
        if not isinstance(skill['graph_id'],str) or (skill['graph_id'] and skill['graph_id'] not in indexed['shared_rules']): raise RuleError('技能引用的规则图不存在')
        if 'initially_available' in skill and type(skill['initially_available']) is not bool: raise RuleError('初始可用必须为开关')
        for name in ['cost','cooldown']: text(skill.get(name,''),name,2000)
        refs=skill.get('references',[])
        if not isinstance(refs,list) or any(not isinstance(r,str) or r not in indexed['definitions'] for r in refs): raise RuleError('技能引用的定义词不存在')
    cycle_check(indexed['shared_rules'],calls,'子图调用')
    safe_data(bundle); return bundle

def references(bundle,id):
    found=[]
    def contains(value):
        if isinstance(value,dict): return any(contains(v) for k,v in value.items() if k not in {'id','name','description','position'})
        if isinstance(value,list): return any(contains(v) for v in value)
        return value==id
    for key in ['skills','shared_rules','node_templates']:
        for value in bundle[key]:
            if value['id']!=id and contains(value): found.append(key+': '+value['name']+' ('+value['id']+')')
    # Include defaults on templates used by graphs.
    registry=templates(bundle)
    for graph in bundle['shared_rules']:
        if any(contains(registry[n['template']]['params']) for n in graph['nodes']): found.append('shared_rules: '+graph['name'])
    return sorted(set(found))

def rename_resource(bundle,collection,old,new):
    identifier(new); result=copy.deepcopy(bundle)
    if any(v['id']==new for v in result[collection]): raise RuleError('新ID已存在')
    item=next((v for v in result[collection] if v['id']==old),None)
    if item is None: raise RuleError('资源不存在')
    item['id']=new
    # Only rewrite typed reference locations, never descriptions or expression text.
    for skill in result['skills']:
        if collection=='definitions': skill['references']=[new if r==old else r for r in skill.get('references',[])]
        if collection=='shared_rules' and skill['graph_id']==old: skill['graph_id']=new
    reference_key={'definitions':('definition','tag'),'shared_rules':('graph',),'skills':('skill',),'node_templates':()}[collection]
    for template in result['node_templates']:
        for key in reference_key:
            if template['params'].get(key)==old: template['params'][key]=new
    for graph in result['shared_rules']:
        for node in graph['nodes']:
            if collection=='node_templates' and node['template']==old: node['template']=new
            for key in reference_key:
                if node['params'].get(key)==old: node['params'][key]=new
    validate_bundle(result); return result


def graph_diagnostics(graph,registry):
    issues=[]
    if graph['kind']=='skill' and not any(registry[n['template']]['op']=='event' for n in graph['nodes']): issues.append('技能图没有事件入口')
    for n in graph['nodes']:
        t=registry[n['template']]; p={**t['params'],**n['params']}; op=t['op']
        if op in {'apply_status','remove_status','read_status','read_attribute','read_resource','change_resource','set_resource','set_attribute'} and not p.get('definition'): issues.append(n['id']+'：未选择定义词/属性/资源')
        if op=='set_skill' and not p.get('skill'): issues.append(n['id']+'：未指定技能ID')
        if op in {'call','rule_enabled'} and not p.get('graph'): issues.append(n['id']+'：未指定规则图')
        if op=='compare' and (not isinstance(p.get('op'),str) or p.get('op') not in {'>=','>','<=','<','==','!='}): issues.append(n['id']+'：比较符无效')
        if op=='calculate':
            try: parse_expression(p.get('expression',''))
            except RuleError as exc: issues.append(n['id']+'：'+str(exc))
    return issues


# Normalize malformed external JSON into domain errors, rather than GUI callback crashes.
def _guard_validation(function):
    from functools import wraps
    @wraps(function)
    def guarded(*args,**kwargs):
        try: return function(*args,**kwargs)
        except RuleError: raise
        except (TypeError,KeyError,IndexError,AttributeError,OverflowError,RecursionError) as exc:
            raise RuleError('规则资源结构无效：'+str(exc)[:180]) from exc
    return guarded

validate_definition=_guard_validation(validate_definition)
validate_template=_guard_validation(validate_template)
validate_graph=_guard_validation(validate_graph)
validate_bundle=_guard_validation(validate_bundle)
