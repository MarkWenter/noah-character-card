"""Bounded event-driven simulator. It only changes a detached Runtime, never a card."""
import copy
from collections import deque
import random
from .catalog import templates,EVENTS
from .expression import RuleError,evaluate,bounded,CMP
from .model import validate_bundle,safe_data,shape,identifier


def entity_from_card(card,id):
    from ..domain import calculate
    computed=calculate(card)
    return {'id':id,'name':card['basic']['姓名'] or id,'attributes':{k:v['最终'] for k,v in computed['attributes'].items()},'resources':{k:card['body'][k] for k in ['HP','MP','TP']},'maxima':copy.deepcopy(computed['maxima']),'statuses':{},'durations':{},'skills':{s['id']:s['enabled'] and s.get('initially_available',True) for s in card.get('talent_derivations',{}).get('skills',[])},'tags':[]}

class Runtime:
    def __init__(self,entities):
        if not isinstance(entities,list) or not 1<=len(entities)<=100: raise RuleError('运行时需要1～100个实体')
        for entity in entities:
            shape(entity,{'id','name','attributes','resources','maxima','statuses','durations','skills','tags'})
            identifier(entity['id'])
            if not isinstance(entity['name'],str): raise RuleError('运行时名称必须为文本')
            for key in ['attributes','resources','maxima','statuses','durations','skills']:
                if not isinstance(entity[key],dict) or len(entity[key])>512: raise RuleError('运行时数值结构错误')
                for name,value in entity[key].items():
                    if not isinstance(name,str): raise RuleError('运行时字段名必须为文本')
                    if key=='skills':
                        if type(value) is not bool: raise RuleError('技能可用性必须为开关')
                    elif type(value) not in (int,float): raise RuleError('运行时属性/资源/状态必须为数值')
                    elif key in ['statuses','durations'] and (type(value) is not int or value<0): raise RuleError('层数/时长必须为非负整数')
            if not isinstance(entity['tags'],list) or any(not isinstance(v,str) for v in entity['tags']): raise RuleError('运行时标签必须为文本列表')
        self.entities={e['id']:copy.deepcopy(e) for e in entities}
        if len(self.entities)!=len(entities): raise RuleError('运行时实体ID重复')
        safe_data(entities); self.events=[]; self.log=[]; self.graph_enabled={}; self.variables={}; self.summons=[]
    def get_status_stacks(self,target,status): return self.entities[target]['statuses'].get(status,0)

class Engine:
    def __init__(self,bundle,runtime,owner='A',seed=0,max_events=256,max_steps=2048,max_depth=24):
        validate_bundle(bundle); self.bundle=copy.deepcopy(bundle); self.runtime=runtime; self.owner=owner
        if owner not in runtime.entities: raise RuleError('技能所属实体不存在')
        self.registry=templates(self.bundle); self.definitions={d['id']:d for d in self.bundle['definitions']}; self.graphs={g['id']:g for g in self.bundle['shared_rules']}; self.skills={s['id']:s for s in self.bundle['skills']}
        self.rng=random.Random(seed); self.max_events=max_events; self.max_steps=max_steps; self.max_depth=max_depth; self.sequence=0; self.processing=False
        for entity in self.runtime.entities.values():
            for d in self.definitions.values():
                default=copy.deepcopy(d.get('default',0))
                if d['kind']=='Attribute': entity['attributes'].setdefault(d['id'],default)
                if d['kind']=='Resource': entity['resources'].setdefault(d['id'],default)
                if d['kind']=='Status' and default: entity['statuses'].setdefault(d['id'],default)
    def _entity(self,value,event):
        value={'self':self.owner,'自身':self.owner,'source':event['source'],'来源':event['source'],'target':event['target'],'目标':event['target']}.get(value,value) if isinstance(value,str) else value
        if not isinstance(value,str) or value not in self.runtime.entities: raise RuleError('目标实体不存在：'+str(value))
        return value
    def _typed(self,value,kind,event):
        if kind in {'Number','Integer','Percent'}:
            if type(value) not in (int,float) or (kind=='Integer' and int(value)!=value): raise RuleError('端口值与数值类型不匹配')
            bounded(value)
        elif kind=='Boolean' and type(value) is not bool: raise RuleError('端口值必须为布尔值')
        elif kind=='String' and not isinstance(value,str): raise RuleError('端口值必须为文本')
        elif kind=='Object' and not isinstance(value,dict): raise RuleError('端口值必须为对象')
        elif kind=='Entity': self._entity(value,event)
        return value

    def _view(self,id):
        e=self.runtime.entities[id]; result={**e['attributes'],**e['resources'],'id':id,'生命值':e['resources'].get('HP',0),'最大生命值':e['maxima'].get('HP',0),'状态':copy.deepcopy(e['statuses']),'资源':copy.deepcopy(e['resources'])}
        for key,d in self.definitions.items():
            if d['kind']=='Attribute': result[d['name']]=e['attributes'].get(key,d.get('default',0))
            if d['kind']=='Resource': result[d['name']]=e['resources'].get(key,d.get('default',0))
            if d['kind']=='Status': result[d['name']]=e['statuses'].get(key,0)
        return result
    def _enqueue(self,type,source,target,data=None,skill='',parent=None):
        if type not in EVENTS and not (type in self.definitions and self.definitions[type]['kind']=='Event'): raise RuleError('未知事件：'+str(type))
        if source not in self.runtime.entities or target not in self.runtime.entities: raise RuleError('事件来源/目标不存在')
        safe_data(data or {})
        depth=parent['depth']+1 if parent else 0
        if depth>self.max_depth: raise RuleError('事件连锁深度超过限制')
        self.sequence+=1
        self.queue.append({'id':f'event.{self.sequence}','type':type,'source':source,'target':target,'data':copy.deepcopy(data or {}),'skill':skill,'parent':parent['id'] if parent else None,'depth':depth})
    def _run(self,action):
        if self.processing: raise RuleError('不能重入运行中的模拟器')
        snapshot=copy.deepcopy(self.runtime.__dict__); rng=self.rng.getstate(); sequence=self.sequence
        self.queue=deque(); self.steps=0; count=0; self.processing=True
        try:
            action()
            while self.queue:
                count+=1
                if count>self.max_events: raise RuleError('事件数量超过限制，可能存在无限触发')
                event=self.queue.popleft(); self.runtime.events.append(event)
                self.runtime.events=self.runtime.events[-1024:]
                self._log('事件 '+event['type'],event)
                if event['type']=='turn_ended':
                    entity=self.runtime.entities[event['target']]
                    for status,duration in list(entity['durations'].items()):
                        if duration==1: self._status(event['target'],status,0,event,remove=True)
                        elif duration>1: entity['durations'][status]=duration-1
                for graph in self.bundle['shared_rules']:
                    if not graph['enabled'] or not self.runtime.graph_enabled.get(graph['id'],True): continue
                    if graph['kind']=='skill':
                        owners=[s for s in self.bundle['skills'] if s['graph_id']==graph['id'] and s['enabled'] and self.runtime.entities[self.owner]['skills'].get(s['id'],False)]
                        if not owners or (event['type']=='skill_used' and not any(s['id']==event['skill'] for s in owners)): continue
                    self._execute(graph,event)
            return self.runtime
        except (RuleError,ArithmeticError,ValueError,KeyError,TypeError,RecursionError) as exc:
            self.runtime.__dict__.clear(); self.runtime.__dict__.update(snapshot); self.rng.setstate(rng); self.sequence=sequence
            error=exc if isinstance(exc,RuleError) else RuleError('规则执行失败：'+str(exc))
            self.runtime.log.append({'message':'已回滚本次模拟：'+str(error),'event':None,'node':None,'graph':None})
            self.runtime.log=self.runtime.log[-2000:]
            raise error
        finally: self.processing=False
    def emit(self,type,source,target,data=None): return self._run(lambda:self._enqueue(type,source,target,data))
    def use_skill(self,id,source='A',target='B'):
        def action():
            if id not in self.skills or source not in self.runtime.entities or not self.skills[id]['enabled'] or not self.runtime.entities[source]['skills'].get(id,False): raise RuleError('技能不存在、未持有或已锁定')
            self._enqueue('skill_used',source,target,skill=id)
        return self._run(action)
    def apply_status(self,target,status,stacks,source=None):
        source=source or self.owner
        return self._run(lambda:self._status(target,status,stacks,{'id':'external','source':source,'target':target,'depth':0}))
    def remove_status(self,target,status,source=None):
        source=source or self.owner
        return self._run(lambda:self._status(target,status,0,{'id':'external','source':source,'target':target,'depth':0},remove=True))
    def _log(self,message,event,node=None,graph=None):
        self.runtime.log.append({'message':str(message)[:500],'event':event['id'],'node':node,'graph':graph})
        self.runtime.log=self.runtime.log[-2000:]
    def _tick(self):
        self.steps+=1
        if self.steps>self.max_steps: raise RuleError('节点执行步数超过限制')
    def _status(self,target,id,value,event,remove=False,duration=0):
        d=self.definitions.get(id)
        if not d or d['kind']!='Status': raise RuleError('状态定义词不存在')
        if type(value) is not int and not (type(value) is float and value.is_integer()): raise RuleError('状态层数必须为整数')
        bounded(value); e=self.runtime.entities[target]; before=e['statuses'].get(id,0)
        new=0 if remove else before+value if d.get('stackable',True) else value
        new=int(max(d.get('min',0),min(d.get('max',1e9),new)))
        if remove: new=0
        if new==before: return
        if new>0: e['statuses'][id]=new; e['durations'][id]=max(0,int(duration))
        else: e['statuses'].pop(id,None); e['durations'].pop(id,None)
        data={'definition':id,'before':before,'value':new}
        if before==0 and new>0: self._enqueue('status_applied',event['source'],target,data,parent=event)
        if new==0: self._enqueue('status_removed',event['source'],target,data,parent=event)
        self._enqueue('status_changed',event['source'],target,data,parent=event)
    def _execute(self,graph,event,args=None,depth=0,called=False):
        if depth>self.max_depth: raise RuleError('子图调用深度超过限制')
        nodes={n['id']:n for n in graph['nodes']}; cache={}; active=set(); returned={}; args=args or {}
        incoming={(e['to'][0],e['to'][1]):e['from'] for e in graph['edges'] if e['kind']=='data'}
        def definition(p,kind=None):
            id=p.get('definition',''); d=self.definitions.get(id)
            if not d or (kind and d['kind']!=kind): raise RuleError('节点缺少正确的定义词引用')
            return d
        def compute(id,flow=False):
            if id in active: raise RuleError('数据流递归')
            if not flow and id in cache: return cache[id]
            n=nodes[id]; t=self.registry[n['template']]; op=t['op']; self._tick(); active.add(id)
            p={**copy.deepcopy(t['params']),**n['params']}
            context={'self':self._view(self.owner),'自身':self._view(self.owner),'source':self._view(event['source']),'来源':self._view(event['source']),'target':self._view(event['target']),'目标':self._view(event['target']),'event':event,'事件':event,'变量':copy.deepcopy(self.runtime.variables),'variables':copy.deepcopy(self.runtime.variables),**{key:self._view(self._entity(value,event)) if graph.get('inputs',{}).get(key)=='Entity' else value for key,value in args.items()}}
            for name,kind in t['inputs'].items():
                if kind=='Flow': continue
                if (id,name) in incoming:
                    source,port=incoming[(id,name)]; outputs=compute(source)
                    if port not in outputs: raise RuleError('数据来源尚未执行或未返回：'+source+'.'+port)
                    p[name]=outputs[port]
                elif name not in p: p[name]='target' if kind=='Entity' else False if kind=='Boolean' else {} if kind=='Object' else 0
                value=p[name]
                if not isinstance(value,dict) or set(value)!={'expr'}:
                    context[name]=self._view(self._entity(value,event)) if kind=='Entity' else value
            for name,value in list(p.items()):
                if isinstance(value,dict) and set(value)=={'expr'}: p[name]=evaluate(value['expr'],context); context[name]=p[name]
            for name,kind in t['inputs'].items():
                if kind=='Flow': continue
                value=p[name]
                if kind in {'Number','Percent','Integer'} and (type(value) not in (int,float) or (kind=='Integer' and int(value)!=value)): raise RuleError('数据端口需要数值：'+name)
                if kind=='Boolean' and type(value) is not bool: raise RuleError('数据端口需要布尔值：'+name)
                if kind=='Object' and not isinstance(value,dict): raise RuleError('数据端口需要对象：'+name)
                if kind=='Entity': self._entity(value,event)
            outputs={}; choice=None
            def value_out(value):
                for port,kind in t['outputs'].items():
                    if kind!='Flow': outputs[port]=bounded(value)
            def branch(result):
                for port,kind in t['outputs'].items():
                    if kind=='Boolean': outputs[port]=result
                names=[port for port,kind in t['outputs'].items() if kind=='Flow']
                preferred=['true','成立','是'] if result else ['false','不成立','否']
                return next((v for v in preferred if v in names),names[0 if result else min(1,len(names)-1)] if names else None)
            if op=='event':
                for port,kind in t['outputs'].items():
                    if kind=='Entity': outputs[port]=event['source'] if port in {'source','来源'} else event['target']
                    elif kind=='Object': outputs[port]=event
            elif op=='constant': value_out(p['value'])
            elif op=='entity': value_out(self._entity(p['who'],event))
            elif op=='read_variable': value_out(copy.deepcopy(self.runtime.variables.get(p['name'],p['default'])))
            elif op.startswith('read_'):
                target=self._entity(p['target'],event); d=self.definitions.get(p['definition']); key=p['definition']; e=self.runtime.entities[target]
                if op=='read_status': definition(p,'Status'); value=e['statuses'].get(key,0)
                else:
                    store=e['resources'] if op=='read_resource' else e['attributes']
                    if key not in store: raise RuleError('实体没有该属性或资源：'+str(key))
                    value=store[key]
                value_out(value)
            elif op=='calculate': value_out(evaluate(p['expression'],{**{k:v for k,v in p.items() if k!='expression'},**context}))
            elif op=='logical':
                if p['mode'] not in {'and','or','not'}: raise RuleError('布尔运算模式无效')
                value_out((p['a'] and p['b']) if p['mode']=='and' else (p['a'] or p['b']) if p['mode']=='or' else not p['a'])
            elif op=='random':
                low,high=p['min'],p['max']; bounded(low); bounded(high)
                if low>high: raise RuleError('随机数范围无效')
                value_out(self.rng.uniform(low,high))
            elif op=='dice':
                count,sides=p['count'],p['sides']
                if type(count) is not int or type(sides) is not int or not 1<=count<=100 or not 2<=sides<=10000: raise RuleError('骰子范围为1～100颗、2～10000面')
                value_out(sum(self.rng.randint(1,sides) for _ in range(count)))
            elif op=='compare':
                comparisons={'>=':lambda a,b:a>=b,'>':lambda a,b:a>b,'<=':lambda a,b:a<=b,'<':lambda a,b:a<b,'==':lambda a,b:a==b,'!=':lambda a,b:a!=b}
                if p['op'] not in comparisons: raise RuleError('比较运算符无效')
                choice=branch(comparisons[p['op']](p['a'],p['b']))
            elif op=='boolean': choice=branch(p['value'])
            elif op=='tags': choice=branch(p['tag'] in self.runtime.entities[self._entity(p['target'],event)]['tags'])
            elif op=='graph_input':
                if p['name'] not in args: raise RuleError('子图输入不存在：'+p['name'])
                value_out(args[p['name']])
            elif not flow: raise RuleError('效果或控制节点的数据必须在其执行后读取')
            elif op=='set_variable':
                identifier(p['name']); safe_data(p['value'])
                if p['name'] not in self.runtime.variables and len(self.runtime.variables)>=128: raise RuleError('临时变量数量超过128')
                self.runtime.variables[p['name']]=copy.deepcopy(p['value'])
            elif op in {'apply_status','remove_status'}:
                self._status(self._entity(p['target'],event),p['definition'],p['value'],event,op=='remove_status',p.get('duration',0))
            elif op in {'change_resource','set_resource','damage','heal','set_attribute'}:
                target=self._entity(p['target'],event); e=self.runtime.entities[target]; value=p['value']; bounded(value)
                if type(value) not in (int,float): raise RuleError('效果数值不合法')
                if op=='set_attribute':
                    d=definition(p,'Attribute'); key=d['id']; e['attributes'][key]=max(d.get('min',-1e9),min(d.get('max',1e9),value))
                else:
                    key='HP' if op in {'damage','heal'} else p['definition']
                    d=self.definitions.get(key,{})
                    if key not in {'HP','MP','TP'}: definition(p,'Resource')
                    before=e['resources'].get(key,d.get('default',0)); delta=-max(0,value) if op=='damage' else max(0,value) if op=='heal' else value
                    new=value if op=='set_resource' else bounded(before+delta)
                    new=max(d.get('min',0),min(d.get('max',e['maxima'].get(key,1e9)),new))
                    if d.get('value_type')=='integer':
                        if int(new)!=new: raise RuleError('整数资源不接受小数结果')
                        new=int(new)
                    e['resources'][key]=new
                    if new!=before:
                        self._enqueue('hp_changed' if key=='HP' else 'resource_changed',event['source'],target,{'definition':key,'before':before,'value':new},parent=event)
                        if op=='damage': self._enqueue('damage_resolved',event['source'],target,{'value':before-new},parent=event)
                        if key=='HP' and new==0 and before>0: self._enqueue('entity_died',event['source'],target,parent=event)
            elif op=='set_skill':
                if p['skill'] not in self.skills or type(p['enabled']) is not bool: raise RuleError('技能ID或可用性无效')
                self.runtime.entities[self._entity(p['target'],event)]['skills'][p['skill']]=p['enabled']
            elif op=='rule_enabled':
                if p['graph'] not in self.graphs or type(p['enabled']) is not bool: raise RuleError('规则图或开关无效')
                self.runtime.graph_enabled[p['graph']]=p['enabled']
            elif op=='call':
                if p['graph'] not in self.graphs or not isinstance(p['args'],dict): raise RuleError('子图引用或参数无效')
                child=self.graphs[p['graph']]
                if set(p['args'])!=set(child.get('inputs',{})): raise RuleError('子图参数与声明接口不匹配')
                for key,kind in child.get('inputs',{}).items(): self._typed(p['args'][key],kind,event)
                result=self._execute(child,event,p['args'],depth+1,True); outputs['value']=result.get('value',result)
            elif op=='graph_output': returned[p['name']]=copy.deepcopy(p['value'])
            elif op in {'sequence','stop'}: pass
            else: raise RuleError('尚未实现的节点操作：'+op)
            for port,value in outputs.items():
                if port in t['outputs']: self._typed(value,t['outputs'][port],event)
            active.remove(id); cache[id]=outputs
            self._log(t['name'],event,id,graph['id'])
            return (outputs,choice,op) if flow else outputs
        roots=[]
        for n in graph['nodes']:
            t=self.registry[n['template']]; p={**t['params'],**n['params']}
            if not called and t['op']=='event' and p['event']==event['type'] and (not p.get('definition') or p['definition']==event['data'].get('definition')) and (not p.get('skill') or p['skill']==event['skill']): roots.append(n['id'])
            elif called and t['op']!='event' and any(v=='Flow' for v in t['inputs'].values()) and not any(e['kind']=='flow' and e['to'][0]==n['id'] for e in graph['edges']): roots.append(n['id'])
        todo=list(reversed(roots))
        while todo:
            id=todo.pop(); outputs,choice,op=compute(id,True)
            if op=='stop': continue
            outgoing=[e for e in graph['edges'] if e['kind']=='flow' and e['from'][0]==id and (choice is None or e['from'][1]==choice)]
            if op=='sequence': outgoing.sort(key=lambda e:0 if e['from'][1]=='first' else 1)
            todo.extend(e['to'][0] for e in reversed(outgoing))
        if called:
            for key,kind in graph.get('outputs',{}).items():
                if key not in returned: raise RuleError('子图未产生声明的输出：'+key)
                self._typed(returned[key],kind,event)
        return returned
