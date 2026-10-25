import copy
import json
from pathlib import Path
import tempfile
import unittest
from noah.domain import new_card,calculate,validate,CardError
from noah.storage import save,load
from noah.skills.catalog import BUILTINS,templates
from noah.skills.model import empty_bundle,new_graph,new_skill,validate_bundle,validate_graph,validate_definition,references,rename_resource
from noah.skills.expression import RuleError,evaluate,parse_expression
from noah.skills.ndsl import parse_ndsl,dump_definition,dump_template
from noah.skills.document import GraphDocument
from noah.skills.engine import Runtime,Engine,entity_from_card
from noah.skills.examples import sample_bundle,DEFINITIONS


def node(id,template,**params): return {'id':id,'template':template,'params':params,'position':[0,0]}
def edge(a,ap,b,bp,kind='flow'): return {'from':[a,ap],'to':[b,bp],'kind':kind}
def engine(bundle=None,**kwargs):
    card=new_card(); card['body'].update(HP=200,MP=40); card['crystal']['能量等级']=30; card['talent_derivations']=copy.deepcopy(bundle or sample_bundle())
    runtime=Runtime([entity_from_card(card,'A'),entity_from_card(card,'B')])
    return Engine(card['talent_derivations'],runtime,**kwargs),card

class NDSLTests(unittest.TestCase):
    def test_example_and_roundtrip(self):
        defs=parse_ndsl(DEFINITIONS)['definitions']; self.assertEqual(defs[0]['max'],3)
        for d in defs: self.assertEqual(parse_ndsl(dump_definition(d))['definitions'][0],d)
    def test_all_definition_kinds(self):
        from noah.skills.catalog import DEFINITION_KINDS
        for kind in DEFINITION_KINDS: validate_definition({'id':'sample.'+kind,'name':kind,'kind':kind,'value_type':'integer','default':0})
    def test_structured_fields(self):
        source='''定义词 事件:
    ID: event.custom
    类型: Event
    数据类型: Object
    默认值: {}
    字段:
        value:
            数据类型: Number
            默认值: 0
            最小值: 0
'''
        d=parse_ndsl(source)['definitions'][0]; self.assertEqual(d['fields']['value']['type'],'number'); self.assertEqual(parse_ndsl(dump_definition(d))['definitions'][0],d)
    def test_no_dynamic_definitions(self):
        for extra in [{'on_change':'fear'},{'default':{'expr':'1+2'},'value_type':'object'}]:
            with self.assertRaises(RuleError): validate_definition({'id':'x','name':'X','kind':'Custom',**extra})
        with self.assertRaises(RuleError): parse_ndsl(DEFINITIONS+'    事件监听: status_changed\n')
    def test_invalid_indentation_and_duplicates(self):
        for source in ['定义词 X:\n  ID: x','定义词 X:\n\tID: x','定义词 X:\n    ID: x\n    ID: y',DEFINITIONS+DEFINITIONS]:
            with self.assertRaises(RuleError): parse_ndsl(source)
    def test_default_constraints(self):
        for d in [{'default':4,'max':3},{'default':True},{'default':0,'min':-1}]:
            with self.assertRaises(RuleError): validate_definition({'id':'s','name':'S','kind':'Status','value_type':'integer',**d})
    def test_custom_hp_ratio_node_executes(self):
        source='''定义节点 生命比例判定:
    ID: node.hp_ratio_check
    模板: 数值比较
    类型: Condition
    输入:
        执行: Flow
        目标: Entity
        阈值: Percent
    左值: 目标.生命值 / 目标.最大生命值
    比较: <=
    右值: 阈值
    输出:
        成立: Flow
        不成立: Flow
'''
        b=sample_bundle(); custom=parse_ndsl(source)['node_templates'][0]; b['node_templates']=[custom]
        self.assertEqual(parse_ndsl(dump_template(custom))['node_templates'][0],custom)
        g=new_graph('graph.ratio','生命比例','shared'); g['nodes']=[node('e','event.attack_hit'),node('c',custom['id'],阈值=.5),node('f','effect.apply_status',definition='status.fear')]; g['edges']=[edge('e','out','c','执行'),edge('c','成立','f','in')]; b['shared_rules'].append(g)
        e,_=engine(b); e.emit('attack_hit','A','B'); self.assertEqual(e.runtime.get_status_stacks('B','status.fear'),1)

class ExpressionTests(unittest.TestCase):
    def test_readonly_chinese_expressions_and_functions(self):
        context={'自身':{'魔法攻击力':80},'目标':{'生命值':30,'最大生命值':100}}
        self.assertEqual(evaluate('自身.魔法攻击力 * 0.3',context),24)
        self.assertTrue(evaluate('目标.生命值 / 目标.最大生命值 <= 0.3',context))
        self.assertEqual(evaluate('max(1, floor(5.8)) + round(1.25, 1)',{}),6.2)
    def test_unsafe_constructs_are_rejected(self):
        for text in ['__import__("os")','open("x")','自身.__class__','[x for x in y]','lambda: 1','2 ** 100000000','(x := 2)']:
            with self.assertRaises(RuleError): parse_expression(text)
    def test_bounds_and_zero_division(self):
        for text in ['1/0','1000000000*1000000000','round(5,-1000000000)','[1]*1000000']:
            with self.assertRaises(RuleError): evaluate(text,{})
    def test_dictionary_only_access(self):
        with self.assertRaises(RuleError): evaluate('x.real',{'x':12})
        with self.assertRaises(RuleError): evaluate('x["__class__"]',{'x':{}})

class GraphTests(unittest.TestCase):
    def setUp(self): self.bundle=sample_bundle(); self.registry=templates(self.bundle); self.graph=copy.deepcopy(self.bundle['shared_rules'][1])
    def test_bad_ports_and_types(self):
        for edge0 in [edge('changed','out','compare','a'),edge('stacks','value','compare','in','data'),edge('missing','x','compare','in')]:
            graph=copy.deepcopy(self.graph); graph['edges'].append(edge0)
            with self.assertRaises(RuleError): validate_graph(graph,self.registry)
    def test_duplicate_data_connection(self):
        self.graph['edges'].append(edge('stacks','value','compare','a','data'))
        with self.assertRaises(RuleError): validate_graph(self.graph,self.registry)
    def test_cycles_rejected(self):
        g=new_graph('cycle','Cycle');g['nodes']=[node('a','effect.apply_status'),node('b','effect.remove_status')];g['edges']=[edge('a','out','b','in'),edge('b','out','a','in')]
        with self.assertRaises(RuleError): validate_graph(g,self.registry)
    def test_bad_reference_and_resource_rename(self):
        changed=rename_resource(self.bundle,'definitions','status.fear','status.dread'); self.assertTrue(references(changed,'status.dread')); validate_bundle(changed)
        broken=copy.deepcopy(self.bundle);broken['definitions']=[]
        with self.assertRaises(RuleError): validate_bundle(broken)
    def test_malformed_json_is_domain_error(self):
        for path,value in [('nodes',{}),('nodes',[{'id':'x','template':[],'params':{},'position':[0,0]}]),('edges',[{'from':[[],'a'],'to':['b','in'],'kind':'flow'}])]:
            graph=copy.deepcopy(self.graph);graph[path]=value
            with self.assertRaises(RuleError): validate_graph(graph,self.registry)
    def test_undo_redo_copy_paste_preserve_internal_edges(self):
        doc=GraphDocument(self.graph,self.registry); original=copy.deepcopy(doc.graph); selected={'compare','remove'}; clipboard=doc.copy(selected); pasted=doc.paste(clipboard)
        self.assertEqual(len(pasted),2); self.assertEqual(len(doc.graph['edges']),len(original['edges'])+1)
        doc.undo();self.assertEqual(doc.graph,original);doc.redo();self.assertEqual(len(doc.graph['nodes']),len(original['nodes'])+2)
        doc.delete(pasted);self.assertEqual(doc.graph,original)
    def test_invalid_connection_does_not_destroy_history(self):
        doc=GraphDocument(self.graph,self.registry); before=copy.deepcopy(doc.graph)
        with self.assertRaises(RuleError): doc.connect('changed','out','compare','a')
        self.assertEqual(doc.graph,before);self.assertFalse(doc.undo_stack)
    def test_subgraph_recursive_reference_rejected(self):
        g=new_graph('g','g','shared');g['nodes']=[node('n','control.call',graph='g')];b=empty_bundle();b['shared_rules']=[g]
        with self.assertRaises(RuleError): validate_bundle(b)

class EngineTests(unittest.TestCase):
    def test_three_uses_convert_and_unlock_then_remove_locks(self):
        e,card=engine(); original=copy.deepcopy(card); computed=calculate(card)
        for count in [1,2]:
            e.use_skill('skill.pressure');self.assertEqual(e.runtime.get_status_stacks('B','status.suppression'),count);self.assertFalse(e.runtime.entities['B']['skills']['skill.fear_power'])
        e.use_skill('skill.pressure');self.assertEqual(e.runtime.get_status_stacks('B','status.suppression'),0);self.assertEqual(e.runtime.get_status_stacks('B','status.fear'),1);self.assertTrue(e.runtime.entities['B']['skills']['skill.fear_power'])
        e.remove_status('B','status.fear');self.assertFalse(e.runtime.entities['B']['skills']['skill.fear_power']);self.assertEqual(card,original);self.assertEqual(calculate(card),computed)
        self.assertTrue(any(x['graph']=='graph.conversion' for x in e.runtime.log));self.assertTrue(any(x['parent'] for x in e.runtime.events))
    def test_conversion_is_not_hardcoded_in_definition(self):
        b=sample_bundle();b['shared_rules']=[g for g in b['shared_rules'] if g['id']!='graph.conversion'];e,_=engine(b)
        for _ in range(4):e.use_skill('skill.pressure')
        self.assertEqual(e.runtime.get_status_stacks('B','status.suppression'),3);self.assertEqual(e.runtime.get_status_stacks('B','status.fear'),0)
    def test_locked_and_disabled_skills(self):
        e,_=engine()
        with self.assertRaises(RuleError):e.use_skill('skill.fear_power')
        self.assertEqual(e.runtime.entities['B']['statuses'],{})
    def test_event_budget_rolls_back_every_effect(self):
        b=empty_bundle();g=new_graph('g','feedback','shared');g['nodes']=[node('e','event.hp_changed'),node('h','effect.heal',value=1)];g['edges']=[edge('e','out','h','in')];b['shared_rules']=[g];e,_=engine(b,max_events=5);before=copy.deepcopy(e.runtime.entities)
        with self.assertRaises(RuleError):e.emit('hp_changed','A','B')
        self.assertEqual(e.runtime.entities,before);self.assertFalse(e.runtime.events);self.assertIn('回滚',e.runtime.log[-1]['message'])
    def test_step_budget_rolls_back(self):
        e,_=engine(max_steps=1)
        with self.assertRaises(RuleError):e.use_skill('skill.pressure')
        self.assertEqual(e.runtime.entities['B']['statuses'],{})
    def test_status_duration(self):
        b=sample_bundle();b['shared_rules'][0]['nodes'][1]['params']['duration']=1;e,_=engine(b);e.use_skill('skill.pressure');e.emit('turn_ended','A','B');self.assertEqual(e.runtime.get_status_stacks('B','status.suppression'),0)
    def test_read_existing_attribute_and_math_damage(self):
        b=empty_bundle();g=new_graph('damage','Damage','shared');g['nodes']=[node('e','event.attack_hit'),node('r','data.attribute',definition='力量',target='self'),node('m','math.calculate',expression='a * 0.3'),node('d','effect.damage')];g['edges']=[edge('e','out','d','in'),edge('r','value','m','a','data'),edge('m','value','d','value','data')];b['shared_rules']=[g];e,_=engine(b);e.emit('attack_hit','A','B');self.assertEqual(e.runtime.entities['B']['resources']['HP'],185)
    def test_subgraph_inputs_and_outputs(self):
        b=empty_bundle();child=new_graph('child','Child','shared');child['inputs']={'amount':'Number'};child['outputs']={'value':'Number'};child['nodes']=[node('i','graph.input',name='amount'),node('o','graph.output',name='value')];child['edges']=[edge('i','value','o','value','data')]
        parent=new_graph('parent','Parent','shared');parent['nodes']=[node('e','event.attack_hit'),node('call','control.call',graph='child',args={'amount':7}),node('damage','effect.damage')];parent['edges']=[edge('e','out','call','in'),edge('call','out','damage','in'),edge('call','value','damage','value','data')]
        # Any output can only enter Any ports: specialize this call's declared data output.
        custom=copy.deepcopy(BUILTINS['control.call']);custom['id']='node.number_call';custom['outputs']['value']='Number';b['node_templates']=[custom];parent['nodes'][1]['template']=custom['id']
        b['shared_rules']=[parent,child];e,_=engine(b);e.emit('attack_hit','A','B');self.assertEqual(e.runtime.entities['B']['resources']['HP'],193)
    def test_seeded_random_repeatability(self):
        b=empty_bundle();g=new_graph('random','random','shared');g['nodes']=[node('e','event.attack_hit'),node('r','math.dice',count=2,sides=6),node('d','effect.damage')];g['edges']=[edge('e','out','d','in'),edge('r','value','d','value','data')];b['shared_rules']=[g]
        e,_=engine(b,seed=42);f,_=engine(b,seed=42);e.emit('attack_hit','A','B');f.emit('attack_hit','A','B');self.assertEqual(e.runtime.entities,f.runtime.entities)
    def test_runtime_rejects_wrong_shape(self):
        with self.assertRaises(RuleError):Runtime([{'id':'A'}])

class PersistenceTests(unittest.TestCase):
    def test_legacy_text_only_card_is_extended_without_loss(self):
        c=new_card();c.pop('talent_derivations');c['crystal']['天赋衍生']='旧版说明'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'old.json';p.write_text(json.dumps(c),encoding='utf-8');restored=load(p)
            self.assertEqual(restored['talent_derivations'],empty_bundle());self.assertEqual(restored['crystal']['天赋衍生'],'旧版说明')
    def test_roundtrip_replays_same_end_to_end_result(self):
        e,c=engine();c['crystal']['天赋衍生']='自然语言描述'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'card.json';save(p,c);restored=load(p);self.assertEqual(restored,c)
            for card in [c,restored]:
                runtime=Runtime([entity_from_card(card,'A'),entity_from_card(card,'B')]);sim=Engine(card['talent_derivations'],runtime)
                for _ in range(3):sim.use_skill('skill.pressure')
                self.assertEqual(runtime.entities['B']['statuses'],{'status.fear':1})
            c['talent_derivations']['skills'][0]['description']='modified';save(p,c);self.assertEqual(load(str(p)+'.bak'),restored)
    def test_invalid_skill_data_does_not_replace_file(self):
        c=new_card()
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'card.json';save(p,c);before=p.read_bytes();c['talent_derivations']=sample_bundle();c['talent_derivations']['shared_rules'][0]['nodes'][0]['template']='missing'
            with self.assertRaises(CardError):save(p,c)
            self.assertEqual(p.read_bytes(),before)
