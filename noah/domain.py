"""Domain rules. Only trusted Python code calculates; card files contain data only."""
import copy
import json
import math
import re
import secrets
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
ATTRS = ['力量', '敏捷', '耐受', '魅力', '智力', '感知', '意志']
SLOTS = ['赋能笔', '蓄能器', '抑制器', '变形重组器', '中枢核心']
ELEMENTS_PRIMARY = ['火','水','冰','电','磁','音','气','风','岩','金','光','暗']
ELEMENTS_SECONDARY = ELEMENTS_PRIMARY + ['生命','情绪','社会','语言','概念']
CONTAINERS = {'背包': (6, 6), '安全箱': (3, 3), '腰带': (6, 1)}
EFFECTS = ATTRS + ['HP上限', 'MP上限', 'TP上限', 'HP恢复', 'MP恢复', 'TP恢复']

class CardError(ValueError):
    pass

def new_card():
    return {
        'format': 'noah-card', 'version': 2, 'rules_version': '0.2-provisional',
        'basic': {k: '' for k in ['姓名', '玩家', '身高cm', '体重kg', '性别', '年龄', '故乡', '民族', '住址', '职业', '阵营', '所属组织', '立场', '战斗职业']},
        'portrait': {'mime': 'image/png', 'data': ''},
        'race': '智人', 'dice': {k: [] for k in ATTRS},
        'attributes': {k: {'base': 50.0, 'correction': 0.0} for k in ATTRS},
        'crystal': {'名称': '', '属性一': '火', '属性二': '火', '意象': '', '形象': '', '固有天赋': '', '天赋衍生': '', '活跃度': 0.0, '活跃度符号': '+', '烈性': 0.0, '烈性符号': '+', '适配度': 0.0, '适配度符号': '+', '能量等级': 0.0},
        'form': {'enabled': False, '描述': '', '天赋增幅': '', '增幅': {k: 0.0 for k in ATTRS + ['烈性', '活跃度']}},
        'overload': {'enabled': False, '特殊天赋': '', '描述': '', '增幅': {k: 0.0 for k in ['力量', '敏捷', '耐受', '意志', '活跃度', '烈性']}, '消耗': {k: 0.0 for k in ['HP', 'MP', 'TP']}},
        'body': {'HP': 0.0, 'MP': 0.0, 'TP': 100.0, '移动': 1.0, '护盾': 0.0, '常驻效果': '', '幸运': 60.0},
        'modifiers': {k: {x: 0.0 for x in ['额外数值', '天赋恢复', '技能恢复', '状态恢复']} for k in ['HP', 'MP', 'TP']},
        'background': {k: '' for k in ['性格', '爱好', '理念', '外貌', '头衔', '出身', '背景故事', '人物标签', '人物关系', '角色台词']},
        'academic': {k: '' for k in ['学历', '毕业院校', '院校地址', '领域偏向', '综合成绩', '毕业时间', '院校简介', '所学专业', '取得学位', '获得奖项', '学术论文', '个人专利', '学术地位']},
        'inventory': {'size': [6, 6], 'items': []}, 'extensions': {},
        'talent_derivations': {'version':1,'definitions':[],'node_templates':[],'shared_rules':[],'skills':[]}
    }

def number(value, name, low=-1000000, high=1000000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high or (isinstance(value, float) and not math.isfinite(value)):
        raise CardError(f'{name} 必须是 {low}～{high} 的有限数值')

def dice_spec(race):
    return {name: int(n) for name, n in re.findall(r'(力量|敏捷|耐受|魅力|智力|感知|意志)([+-]\d+)', CATALOG['races'][race]['dice'])}

def roll_race(card):
    result = {k: [secrets.randbelow(6) + 1 for _ in range(abs(dice_spec(card['race']).get(k, 0)))] for k in ATTRS}
    card['dice'] = result
    return result

def validate(card):
    if not isinstance(card, dict) or card.get('format') != 'noah-card' or type(card.get('version')) is not int or card['version'] != 2:
        raise CardError('不是受支持的人物卡，或文件版本过新')
    from .skills.model import empty_bundle,validate_bundle
    from .skills.expression import RuleError
    card.setdefault('talent_derivations',empty_bundle())
    try: validate_bundle(card['talent_derivations'])
    except RuleError as exc: raise CardError('技能资源：'+str(exc)) from exc
    template = new_card()
    def walk(obj, expected, path='', depth=0):
        if depth > 24: raise CardError('文件嵌套过深')
        if path in ('extensions', 'inventory.items', 'dice', 'inventory.size', 'portrait', 'talent_derivations'): return
        if isinstance(expected, dict):
            if not isinstance(obj, dict) or set(obj) != set(expected): raise CardError(f'{path or "根节点"} 字段缺失或未知')
            for k, v in expected.items(): walk(obj[k], v, f'{path}.{k}'.lstrip('.'), depth+1)
        elif isinstance(expected, bool):
            if type(obj) is not bool: raise CardError(f'{path} 必须为开关')
        elif isinstance(expected, (float, int)): number(obj, path)
        elif not isinstance(obj, str) or len(obj) > 30000: raise CardError(f'{path} 文本过长或类型错误')
    walk(card, template)
    if card['rules_version'] != template['rules_version']: raise CardError('不支持此规则版本')
    if card['race'] not in CATALOG['races']: raise CardError('未知亚种')
    for k, lo, hi in [('活跃度', 0, 99), ('烈性', 0, 99), ('适配度', 0, 100), ('能量等级', 0, 100)]: number(card['crystal'][k], k, lo, hi)
    for k in ['活跃度','烈性','适配度']:
        if card['crystal'][k+'符号'] not in ('+','-'): raise CardError(k+'符号必须为+或-')
    if card['crystal']['属性一'] not in ELEMENTS_PRIMARY or card['crystal']['属性二'] not in ELEMENTS_SECONDARY: raise CardError('晶灵属性不在可选列表中')
    from .photos import validate_portrait
    try: validate_portrait(card['portrait'])
    except ValueError as exc: raise CardError(str(exc)) from exc
    if not isinstance(card['extensions'], dict): raise CardError('扩展数据必须为对象')
    def extension_check(obj, depth=0):
        if depth > 12: raise CardError('扩展数据嵌套过深')
        if isinstance(obj, dict):
            if len(obj)>500 or any(not isinstance(k,str) or len(k)>200 for k in obj): raise CardError('扩展字段过多或名称过长')
            for v in obj.values(): extension_check(v,depth+1)
        elif isinstance(obj,list):
            if len(obj)>500: raise CardError('扩展列表过长')
            for v in obj: extension_check(v,depth+1)
        elif isinstance(obj,str):
            if len(obj)>30000: raise CardError('扩展文本过长')
        elif obj is None or type(obj) is bool: pass
        else: number(obj,'扩展数值')
    extension_check(card['extensions'])
    rich=card['extensions'].get('rich_text',{})
    if not isinstance(rich,dict) or len(rich)>128: raise CardError('文本格式数据无效')
    import re
    for key,records in rich.items():
        if not isinstance(key,str) or not isinstance(records,list) or len(records)>10000: raise CardError('文本格式记录无效')
        for record in records:
            if not isinstance(record,list) or len(record)!=3 or any(not isinstance(v,str) for v in record): raise CardError('文本格式记录无效')
            tag,a,b=record
            if tag not in ('rich_bold','rich_italic') and not re.fullmatch(r'rich_color_#[0-9a-fA-F]{6}',tag): raise CardError('文本颜色或格式无效')
            if any(not re.fullmatch(r'[1-9][0-9]{0,5}\.[0-9]{1,6}',v) for v in (a,b)): raise CardError('文本格式位置无效')

    spec=dice_spec(card['race'])
    if not isinstance(card['dice'],dict) or set(card['dice']) != set(ATTRS): raise CardError('骰点结构错误')
    for k, rolls in card['dice'].items():
        if not isinstance(rolls,list) or len(rolls) not in (0,abs(spec.get(k,0))) or any(type(x) is not int or not 1<=x<=6 for x in rolls): raise CardError(f'{k} 骰点不合法')
    size=card['inventory']['size']
    if not isinstance(size,list) or size not in [[6,6],[7,9],[9,12]]: raise CardError('背包尺寸不合法')
    items=card['inventory']['items']
    if not isinstance(items,list) or len(items)>200: raise CardError('物品数量超过200或格式错误')
    occupied=set(); slots=set(); ids=set()
    item_fields={'id','name','container','quantity','weight','slot','effects','description'}
    geometry={'x','y','w','h'}
    for item in items:
        if not isinstance(item,dict): raise CardError('物品字段不完整')
        expected=item_fields if item.get('container')=='装备' else item_fields|geometry
        if set(item)!=expected and not (item.get('container')=='装备' and set(item)==item_fields|geometry): raise CardError('物品字段不完整')
        for k in ['id','name','container','slot','description']:
            if not isinstance(item[k],str) or len(item[k])>30000: raise CardError('物品文本不合法')
        if not item['id'] or item['id'] in ids: raise CardError('物品编号重复或为空')
        ids.add(item['id'])
        if not item['name'].strip(): raise CardError('物品必须填写名称')
        if type(item['quantity']) is not int: raise CardError('数量必须为整数')
        number(item['quantity'],'数量',1,9999); number(item['weight'],'重量',0,100000)
        if not isinstance(item['effects'],dict) or set(item['effects'])!=set(EFFECTS): raise CardError('物品效果字段不合法')
        for k,v in item['effects'].items(): number(v,k)
        if item['container']=='装备':
            if item['slot'] not in SLOTS or item['slot'] in slots: raise CardError('装备槽无效或已占用')
            if item['quantity']!=1: raise CardError('装备数量必须为1')
            for key in geometry.intersection(item): number(item[key],key)
            slots.add(item['slot'])
        else:
            if item['container'] not in CONTAINERS or item['slot']: raise CardError('物品容器或装备槽不合法')
            for k in ['x','y','w','h']:
                if type(item[k]) is not int: raise CardError('位置和尺寸必须为整数')
            for key in ['x','y']: number(item[key],key,0,12)
            for key in ['w','h']: number(item[key],key,1,12)
            width,height=size if item['container']=='背包' else CONTAINERS[item['container']]
            if item['w']<1 or item['h']<1 or item['x']<0 or item['y']<0 or item['x']+item['w']>width or item['y']+item['h']>height: raise CardError('物品超出容器边界')
            for x in range(item['x'],item['x']+item['w']):
                for y in range(item['y'],item['y']+item['h']):
                    cell=(item['container'],x,y)
                    if cell in occupied: raise CardError('物品占格重叠')
                    occupied.add(cell)
    if '赋能笔' not in slots and slots.intersection(SLOTS[1:5]): raise CardError('必须先装备赋能笔，才能安装四个部件')
    return card

def calculate(card):
    race=CATALOG['races'][card['race']]; spec=dice_spec(card['race']); result={}; subtotal={}
    equipment={k:sum(i['effects'][k] for i in card['inventory']['items'] if i['container']=='装备') for k in EFFECTS}
    for k in ATTRS:
        a=card['attributes'][k]; racial=sum(card['dice'][k]) * (-1 if spec.get(k,0)<0 else 1)
        cap=100+race['caps'][k]
        limited=min(a['base']+racial,cap); subtotal[k]=limited
        form=card['form']['增幅'][k] if card['form']['enabled'] else 0
        overload=card['overload']['增幅'].get(k,0) if card['overload']['enabled'] else 0
        result[k]={'基础':a['base'],'种族':racial,'上限':cap,'封顶小计':limited,'灵能形态':form+overload,'装备':equipment[k],'补正':a['correction'],'最终':limited+form+overload+equipment[k]+a['correction']}
    c=card['crystal']; a=signed_indicator(c,'活跃度'); e=c['能量等级']; overload=card['overload']; mods=card['modifiers']
    maxima={'HP':max(0,race['hp']+(card['attributes']['耐受']['base']+result['耐受']['种族'])*c['适配度']*.1+mods['HP']['额外数值']+equipment['HP上限']), 'MP':max(0,e*race['energy']+mods['MP']['额外数值']+equipment['MP上限']), 'TP':max(0,100+mods['TP']['额外数值']+equipment['TP上限'])}
    regen={'HP':abs(a)*(2 if a>=0 else 1)*race['hp_regen'],'MP':abs(a)*(1 if a>=0 else 2)*.1,'TP':(subtotal['耐受']+subtotal['意志'])*race['tp_regen']*.01}
    if overload['enabled']:
        if card['body']['MP']<.25*maxima['MP']: regen['HP']-=overload['消耗']['HP']
        regen['MP']-=overload['消耗']['MP'] if card['body']['MP']>.25*maxima['MP'] else regen['MP']
        regen['TP']-=overload['消耗']['TP']
    for k in regen: regen[k]+=sum(mods[k][v] for v in ['天赋恢复','技能恢复','状态恢复'])+equipment[k+'恢复']
    warnings=[]
    if card['body']['MP']<=0:
        regen['HP']=regen['MP']=0; warnings.append('MP 已清零，HP/MP 自然恢复停止（附表文字规则）')
    if card['body']['HP']<=0: warnings.append('HP 已清零：战斗结束')
    if card['body']['TP']<=0: warnings.append('TP 已清零：人物劳累')
    if any(spec.get(k,0) and not card['dice'][k] for k in ATTRS): warnings.append('尚未投掷种族奖励骰，种族属性暂按0计算')
    for k in maxima:
        if not 0<=card['body'][k]<=maxima[k]: warnings.append(f'{k} 当前值超出0～{maxima[k]:g}，请检查')
    level=round((abs(c['活跃度'])+abs(c['烈性'])+signed_indicator(c,'适配度')+100)/7.96+e/2,2)
    grade=next((g for bound,g in [(40,'E'),(55,'D'),(70,'C'),(85,'B'),(100,'A')] if level<=bound),'A')
    return {'attributes':result,'maxima':maxima,'regen':regen,'level':level,'grade':grade,'warnings':warnings,'weight':sum(i['quantity']*i['weight'] for i in card['inventory']['items'])}





def signed_indicator(crystal, name):
    return crystal[name] * (-1 if crystal[name+'符号']=='-' else 1)
