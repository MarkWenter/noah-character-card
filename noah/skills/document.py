"""Undoable graph document; all operations are usable and testable without a GUI."""
import copy
import json
import uuid
from .model import validate_graph
from .expression import RuleError

class GraphDocument:
    def __init__(self,graph,registry):
        validate_graph(graph,registry); self.graph=copy.deepcopy(graph); self.registry=registry; self.undo_stack=[]; self.redo_stack=[]
    def snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.graph)); self.undo_stack=self.undo_stack[-50:]; self.redo_stack=[]
    def mutate(self,callback):
        proposed=copy.deepcopy(self.graph); callback(proposed); validate_graph(proposed,self.registry)
        if proposed!=self.graph: self.snapshot(); self.graph=proposed
    def add_node(self,template,position):
        id='node.'+uuid.uuid4().hex[:12]
        self.mutate(lambda g:g['nodes'].append({'id':id,'template':template,'params':{},'position':list(position)})); return id
    def connect(self,source,source_port,target,target_port):
        kind='flow' if self.registry[next(n for n in self.graph['nodes'] if n['id']==source)['template']]['outputs'][source_port]=='Flow' else 'data'
        edge={'from':[source,source_port],'to':[target,target_port],'kind':kind}
        self.mutate(lambda g:g['edges'].append(edge))
    def disconnect(self,index): self.mutate(lambda g:g['edges'].pop(index))
    def delete(self,selection):
        selection=set(selection)
        def change(g):
            g['nodes']=[n for n in g['nodes'] if n['id'] not in selection]; g['edges']=[e for e in g['edges'] if e['from'][0] not in selection and e['to'][0] not in selection]
        self.mutate(change)
    def copy(self,selection):
        selection=set(selection)
        return json.dumps({'nodes':[n for n in self.graph['nodes'] if n['id'] in selection],'edges':[e for e in self.graph['edges'] if e['from'][0] in selection and e['to'][0] in selection]},ensure_ascii=False)
    def paste(self,text):
        if len(text)>500000: raise RuleError('粘贴数据过大')
        try: content=json.loads(text)
        except (ValueError,RecursionError) as exc: raise RuleError('粘贴数据不是有效JSON') from exc
        if not isinstance(content,dict) or set(content)!={'nodes','edges'} or not isinstance(content['nodes'],list) or not isinstance(content['edges'],list): raise RuleError('粘贴格式不支持')
        mapping={n.get('id'):'node.'+uuid.uuid4().hex[:12] for n in content['nodes'] if isinstance(n,dict)}
        def change(g):
            for n in content['nodes']:
                node=copy.deepcopy(n); node['id']=mapping[n['id']]; node['position']=[v+40 for v in n['position']]; g['nodes'].append(node)
            for e in content['edges']:
                edge=copy.deepcopy(e); edge['from'][0]=mapping[e['from'][0]]; edge['to'][0]=mapping[e['to'][0]]; g['edges'].append(edge)
        try: self.mutate(change)
        except (KeyError,TypeError,IndexError) as exc: raise RuleError('粘贴内容不完整') from exc
        return set(mapping.values())
    def move(self,positions):
        def change(g):
            for n in g['nodes']:
                if n['id'] in positions: n['position']=list(positions[n['id']])
        self.mutate(change)
    def undo(self):
        if self.undo_stack: self.redo_stack.append(copy.deepcopy(self.graph)); self.graph=self.undo_stack.pop()
    def redo(self):
        if self.redo_stack: self.undo_stack.append(copy.deepcopy(self.graph)); self.graph=self.redo_stack.pop()
