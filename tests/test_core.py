import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from noah.domain import new_card, validate, calculate, roll_race, ATTRS, EFFECTS, CATALOG, CardError
from noah.storage import save, load

def item(name='物品',container='背包',slot='',**changes):
    result={'id':name,'name':name,'container':container,'slot':slot,'x':0,'y':0,'w':1,'h':1,'quantity':1,'weight':1.0,'effects':{k:0.0 for k in EFFECTS},'description':''}
    result.update(changes); return result

class RulesTests(unittest.TestCase):
    def setUp(self): self.card=new_card()
    def test_defaults_and_all_catalog_races(self):
        for race in CATALOG['races']:
            card=new_card(); card['race']=race; roll_race(card); validate(card)
            self.assertTrue(all(math.isfinite(v['最终']) for v in calculate(card)['attributes'].values()))
    def test_signed_dice_persist_without_reroll(self):
        self.card['race']='猫人'
        with patch('noah.domain.secrets.randbelow',return_value=5): roll_race(self.card)
        result=calculate(self.card)['attributes']
        self.assertEqual(result['力量']['种族'],-6); self.assertEqual(result['敏捷']['种族'],12)
        self.assertEqual(calculate(self.card),calculate(self.card))
    def test_cap_only_first_three_sources(self):
        self.card['attributes']['力量']['base']=500; self.card['attributes']['力量']['correction']=7
        self.card['form']['enabled']=True; self.card['form']['增幅']['力量']=10
        self.assertEqual(calculate(self.card)['attributes']['力量']['最终'],117)
    def test_equipment_only_when_equipped_and_skills_absent(self):
        self.assertNotIn('skills',self.card)
        i=item(); i['effects']['力量']=8; self.card['inventory']['items']=[i]
        self.assertEqual(calculate(self.card)['attributes']['力量']['最终'],50)
        i['container']='装备'; i['slot']='赋能笔'; validate(self.card)
        self.assertEqual(calculate(self.card)['attributes']['力量']['最终'],58)
        self.assertNotIn('技能',calculate(self.card)['attributes']['力量'])
    def test_psionic_extremes_and_sign_symmetry(self):
        c=self.card['crystal']; c.update({'活跃度':0,'烈性':0,'适配度':100,'适配度符号':'-','能量等级':0})
        self.assertEqual(calculate(self.card)['level'],0)
        for a in [-99,99]:
            for s in [-99,99]:
                c.update({'活跃度':abs(a),'活跃度符号':'-' if a<0 else '+','烈性':abs(s),'烈性符号':'-' if s<0 else '+','适配度':100,'适配度符号':'+','能量等级':100})
                self.assertEqual(calculate(self.card)['level'],100)
        for a in [-99,0,99]:
            for s in [-99,0,99]:
                for c0 in [-100,0,100]:
                    for e in [0,50,100]:
                        c.update({'活跃度':abs(a),'活跃度符号':'-' if a<0 else '+','烈性':abs(s),'烈性符号':'-' if s<0 else '+','适配度':abs(c0),'适配度符号':'-' if c0<0 else '+','能量等级':e}); validate(self.card)
                        self.assertTrue(0<=calculate(self.card)['level']<=100)
    def test_hp_uses_base_plus_racial_not_final_endurance(self):
        self.card['crystal']['适配度']=50; self.card['crystal']['适配度符号']='-'; self.card['attributes']['耐受']['base']=60
        self.card['attributes']['耐受']['correction']=999
        self.assertEqual(calculate(self.card)['maxima']['HP'],800)
    def test_signed_recovery_and_mp_zero(self):
        self.card['body']['MP']=1; self.card['crystal']['活跃度']=10
        self.assertAlmostEqual(calculate(self.card)['regen']['HP'],2)
        self.assertAlmostEqual(calculate(self.card)['regen']['MP'],1)
        self.card['crystal']['活跃度符号']='-'
        self.assertAlmostEqual(calculate(self.card)['regen']['HP'],1)
        self.assertAlmostEqual(calculate(self.card)['regen']['MP'],2)
        self.card['body']['MP']=0
        self.assertEqual(calculate(self.card)['regen']['HP'],0)
    def test_overload_quarter_boundary(self):
        self.card['crystal'].update({'能量等级':100,'活跃度':10}); self.card['overload']['enabled']=True
        self.card['overload']['消耗'].update({'HP':5,'MP':3,'TP':2})
        self.card['body']['MP']=50
        r=calculate(self.card)['regen']; self.assertEqual(r['MP'],0); self.assertEqual(r['HP'],2)
        self.card['body']['MP']=49
        self.assertEqual(calculate(self.card)['regen']['HP'],-3)
        self.card['body']['MP']=51
        self.assertEqual(calculate(self.card)['regen']['MP'],-2)
    def test_invalid_numbers_and_crystal_ranges(self):
        for value in [float('nan'),float('inf'),10**1000,-1,100,True,'5']:
            card=new_card(); card['crystal']['活跃度']=value
            with self.assertRaises(CardError): validate(card)
    def test_inventory_collision_bounds_and_sizes(self):
        for items in [[item('a',w=7)],[item('a'),item('b')],[item('a',x=-1)],[item('a',w=0)]]:
            self.card['inventory']['items']=items
            with self.assertRaises(CardError): validate(self.card)
        self.card['inventory']['size']=[9,12]; self.card['inventory']['items']=[item('a',x=8,y=11)]; validate(self.card)
        self.card['inventory']['size']=[6,6]
        with self.assertRaises(CardError): validate(self.card)
    def test_pen_component_lifecycle(self):
        part=item('核心','装备','中枢核心'); pen=item('笔','装备','赋能笔')
        self.card['inventory']['items']=[part]
        with self.assertRaises(CardError): validate(self.card)
        self.card['inventory']['items'].append(pen); validate(self.card)
        self.card['inventory']['items'].remove(pen)
        with self.assertRaises(CardError): validate(self.card)
    def test_equipment_duplicate_slot_and_stack(self):
        self.card['inventory']['items']=[item('a','装备','赋能笔'),item('b','装备','赋能笔')]
        with self.assertRaises(CardError): validate(self.card)
        self.card['inventory']['items']=[item('a','装备','赋能笔',quantity=2)]
        with self.assertRaises(CardError): validate(self.card)
    def test_foreign_version_and_unknown_keys(self):
        for key,value in [('version',3),('rules_version','future'),('extra',{})]:
            card=new_card(); card[key]=value
            with self.assertRaises(CardError): validate(card)
    def test_bad_dice_and_extension(self):
        self.card['dice']['力量']=[7]
        with self.assertRaises(CardError): validate(self.card)
        self.card=new_card(); self.card['extensions']={'a':float('nan')}
        with self.assertRaises(CardError): validate(self.card)

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.card=new_card()
        self.card['basic']['姓名']='诺阿<&>人物'; self.card['background']['背景故事']='第一行\n第二行'
        self.card['extensions']={'未来字段':[True,None,12,{'名称':'示例'}]}; roll_race(self.card)
    def tearDown(self): self.temp.cleanup()
    def test_all_formats_roundtrip(self):
        for suffix in ['.json']:
            p=self.root/('card'+suffix); save(p,self.card); self.assertEqual(load(p),self.card)
    def test_backup_is_previous_revision(self):
        p=self.root/'card.json'; save(p,self.card); original=copy.deepcopy(self.card)
        self.card['basic']['姓名']='新版'; save(p,self.card)
        self.assertEqual(load(str(p)+'.bak'),original); self.assertEqual(load(p),self.card)
    def test_invalid_save_preserves_existing(self):
        p=self.root/'card.json'; save(p,self.card); data=p.read_bytes(); self.card['crystal']['能量等级']=101
        with self.assertRaises(CardError): save(p,self.card)
        self.assertEqual(p.read_bytes(),data)
    def test_replace_failure_keeps_original_and_cleans_temporary(self):
        p=self.root/'card.json'; save(p,self.card); data=p.read_bytes()
        with patch('noah.storage.os.replace',side_effect=OSError('模拟写入失败')):
            with self.assertRaises(CardError): save(p,self.card)
        self.assertEqual(p.read_bytes(),data); self.assertFalse(list(self.root.glob('*.tmp')))
    def test_dtd_and_entities_rejected(self):
        p=self.root/'bad.xml'; p.write_text('<!DOCTYPE x [<!ENTITY y "z">]><noah-card/>',encoding='utf-8')
        with self.assertRaises(CardError): load(p)
    def test_size_malformed_duplicates_nonfinite(self):
        p=self.root/'bad.json'
        for text in ['x'*(2*1024*1024+1),'{bad','{"format":1,"format":2}','{"x":NaN}']:
            p.write_text(text,encoding='utf-8')
            with self.assertRaises(CardError): load(p)
    def test_xml_save_rejected(self):
        with self.assertRaises(CardError): save(self.root/'card.xml',self.card)
    def test_json_control_character_roundtrip(self):
        p=self.root/'card.json'; self.card['basic']['姓名']='name\x00text'; save(p,self.card)
        self.assertEqual(load(p),self.card)

if __name__=='__main__': unittest.main()

