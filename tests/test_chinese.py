import unittest
from noah.skills.chinese import dump,parse
from noah.skills.examples import sample_bundle
from noah.skills.expression import RuleError
from noah.domain import validate
from noah.storage import load
from pathlib import Path
class ChineseTests(unittest.TestCase):
    def test_bundle_roundtrip(self):
        bundle=sample_bundle()
        self.assertEqual(parse(dump(bundle)),bundle)
    def test_values(self):
        for value in [True,False,None,1,-2.5,'hello\nworld',{'输入接口':[]},[],{}, {'x':'\\n'}]:
            self.assertEqual(parse(dump(value)),value)
    def test_reject(self):
        for text in ['记录：\n    设置 x：\n        是\n    设置 x：\n        否','数值：nan','执行任意代码','记录：\n 添加：']:
            with self.assertRaises(RuleError): parse(text)
    def test_previous_card(self):
        path=Path(__file__).resolve().parents[1]/'examples'/'NDSL技能示例人物.json'
        card=load(path)
        before=card['talent_derivations']
        card['talent_derivations']=parse(dump(before))
        validate(card)
        self.assertEqual(before,card['talent_derivations'])
