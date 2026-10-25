import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from noah.skills.expression import RuleError
from noah.skills.model import empty_bundle,new_graph,graph_diagnostics
from noah.skills.catalog import templates
from noah.skills.io import read_json,write_json
from test_skills import engine,node,edge

class SkillBoundaryTests(unittest.TestCase):
    def test_sequence_and_expression_see_runtime_variable(self):
        b=empty_bundle();g=new_graph('sequence','Sequence','shared');g['nodes']=[node('e','event.attack_hit'),node('s','control.sequence'),node('v','effect.variable',name='charge',value=7),node('d','effect.damage',value={'expr':"变量['charge']"})];g['edges']=[edge('e','out','s','in'),edge('s','first','v','in'),edge('s','second','d','in')];b['shared_rules']=[g]
        e,_=engine(b);e.emit('attack_hit','A','B');self.assertEqual(e.runtime.variables['charge'],7);self.assertEqual(e.runtime.entities['B']['resources']['HP'],193)
    def test_wrong_runtime_output_type_rolls_back(self):
        b=empty_bundle();g=new_graph('bad','Bad','shared');g['nodes']=[node('e','event.attack_hit'),node('m','math.calculate',expression='1 > 0'),node('d','effect.damage')];g['edges']=[edge('e','out','d','in'),edge('m','value','d','value','data')];b['shared_rules']=[g];e,_=engine(b);before=copy.deepcopy(e.runtime.entities)
        with self.assertRaises(RuleError):e.emit('attack_hit','A','B')
        self.assertEqual(e.runtime.entities,before)
    def test_integer_resource_rejects_fractional_result(self):
        b=empty_bundle();b['definitions']=[{'id':'resource.anger','name':'怒火','kind':'Resource','value_type':'integer','default':0,'min':0,'max':10}];g=new_graph('anger','Anger','shared');g['nodes']=[node('e','event.attack_hit'),node('r','effect.change_resource',definition='resource.anger',value=.5)];g['edges']=[edge('e','out','r','in')];b['shared_rules']=[g];e,_=engine(b)
        with self.assertRaises(RuleError):e.emit('attack_hit','A','B')
        self.assertEqual(e.runtime.entities['B']['resources']['resource.anger'],0)
    def test_event_depth_limit_rolls_back(self):
        e,_=engine(max_depth=1)
        e.use_skill('skill.pressure');e.use_skill('skill.pressure');before=copy.deepcopy(e.runtime.entities)
        with self.assertRaises(RuleError):e.use_skill('skill.pressure')
        self.assertEqual(e.runtime.entities,before)
    def test_draft_diagnostics_do_not_block_storage_model(self):
        graph=new_graph('draft','Draft');self.assertIn('技能图没有事件入口',graph_diagnostics(graph,templates(empty_bundle())))
    def test_resource_json_duplicates_size_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'resource.json';p.write_text('{"a":1,"a":2}',encoding='utf-8')
            with self.assertRaises(RuleError):read_json(p)
            p.write_bytes(b' '*101)
            with self.assertRaises(RuleError):read_json(p,limit=100)
            write_json(p,{'a':1});write_json(p,{'a':2});self.assertEqual(read_json(str(p)+'.bak'),{'a':1})
            with patch('noah.skills.io.os.replace',side_effect=OSError('disk')):
                with self.assertRaises(RuleError):write_json(p,{'a':3})
            self.assertEqual(read_json(p),{'a':2});self.assertFalse(list(Path(directory).glob('*.tmp')))
