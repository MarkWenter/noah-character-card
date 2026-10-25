import copy
import unittest
from noah.domain import new_card,validate,calculate,EFFECTS

class IndependentEquipmentTests(unittest.TestCase):
    def test_full_bag_and_independent_gear(self):
        c=new_card()
        bag={'id':'full','name':'占满背包','container':'背包','slot':'','x':0,'y':0,'w':6,'h':6,'quantity':1,'weight':2,'description':'','effects':{k:0 for k in EFFECTS}}
        pen={'id':'pen','name':'独立赋能笔','container':'装备','slot':'赋能笔','quantity':1,'weight':1,'description':'','effects':{k:0 for k in EFFECTS}}
        pen['effects']['力量']=8
        c['inventory']['items']=[bag,pen]; validate(c)
        self.assertEqual(calculate(c)['attributes']['力量']['最终'],58)
        self.assertEqual(bag['w'],6); self.assertEqual(bag['h'],6)
        for k in ['x','y','w','h']: self.assertNotIn(k,pen)
        c['inventory']['items'].append({**copy.deepcopy(pen),'id':'core','slot':'中枢核心','name':'核心','effects':{k:0 for k in EFFECTS}}); validate(c)
        self.assertEqual(calculate(c)['weight'],4)
    def test_equipment_does_not_need_matching_bag_item(self):
        c=new_card(); c['inventory']['items']=[{'id':'pen','name':'独立装备','container':'装备','slot':'赋能笔','quantity':1,'weight':0,'description':'','effects':{k:0 for k in EFFECTS}}]
        validate(c); self.assertTrue(all(i['container']=='装备' for i in c['inventory']['items']))
