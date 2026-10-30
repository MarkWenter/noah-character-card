"""Deterministic Chinese value language; no executable code or JSON syntax required."""
import math
from .expression import RuleError
WORDS=dict(zip(
    'Attribute Resource Status Tag Entity Event Scene DamageType Custom integer number boolean string object Flow Number Integer Percent Boolean String Object Any active passive reaction permanent skill shared scene Event Condition Data Math Effect Control Rule target source self in out true false result value a b op definition graph enabled duration count sides min max default inputs outputs params name id kind value_type categories tags stackable dispellable fields description type expression event who mode first second args skill_used attack_hit damage_resolved hp_changed resource_changed status_applied status_changed status_removed turn_started turn_ended entity_died and or not'.split(),
    '属性 资源 状态 标签 实体 事件 场景 伤害类型 自定义 整数 小数 是否 文字 记录 执行 数值 整数端口 百分比 是否端口 文字端口 记录端口 任意 主动 被动 反应 常驻 技能流程 公共流程 场景流程 事件节点 条件节点 数据节点 计算节点 效果节点 控制节点 规则节点 当前目标 事件来源 自身 进入 继续 满足 不满足 判断结果 数值内容 左值 右值 比较方式 定义词 关联流程 启用 持续回合 骰子数量 骰子面数 最小值 最大值 默认值 输入接口 输出接口 默认参数 名称 标识 类别 数据类型 分类 标记 可叠加 可驱散 数据字段 说明 技能类别 计算式 触发事件 实体选择 逻辑方式 首先 然后 传入数据 使用技能 攻击命中 伤害结算 生命变化 资源变化 施加状态 状态变化 移除状态 回合开始 回合结束 实体死亡 并且 或者 取反'.split()))
WORDS.update({'expr':'算术表达式','>=':'大于或等于','>':'大于','<=':'小于或等于','<':'小于','==':'等于','!=':'不等于','definitions':'定义词集合','node_templates':'自定义节点集合','statuses':'持有状态','resources':'资源数值','attributes':'属性数值','skills':'可用技能','variables':'临时变量','hp':'生命值','max_hp':'生命上限'})
REVERSE={v:k for k,v in WORDS.items()}
def label(value): return WORDS.get(value,value)
def internal(value): return REVERSE.get(value,value)
def atom(value):
    if isinstance(value,bool): return '是' if value else '否'
    if value is None: return '空值'
    if isinstance(value,(int,float)): return '数值：'+str(value)
    if isinstance(value,str) and value in WORDS: return '选项：'+label(value)
    return '文字：'+str(value).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r')
def dump(value):
    def lines(v,depth):
        pad='    '*depth
        if isinstance(v,dict):
            result=[pad+'记录：']
            for k,x in v.items(): result.append(pad+'    设置 '+(label(k) if k in WORDS else '原名·'+k)+'：'); result.extend(lines(x,depth+2))
            return result
        if isinstance(v,list):
            result=[pad+'列表：']
            for x in v: result.append(pad+'    添加：'); result.extend(lines(x,depth+2))
            return result
        return [pad+atom(v)]
    return '\n'.join(lines(value,0))
def parse(source):
    if len(source)>100000: raise RuleError('句式内容过长')
    rows=[(len(s)-len(s.lstrip(' ')),s.strip(),i) for i,s in enumerate(source.splitlines(),1) if s.strip()]
    def read(index,depth):
        if depth>48: raise RuleError('句式层级过深')
        if index>=len(rows) or rows[index][0]!=depth*4: raise RuleError('缩进应为四个空格；每个设置或添加后需要填写内容')
        _,text,line=rows[index]; index+=1
        if text in {'记录：','列表：'}:
            result={} if text=='记录：' else []
            while index<len(rows) and rows[index][0]>depth*4:
                indent,header,n=rows[index]
                if indent!=(depth+1)*4: raise RuleError(f'第{n}行缩进不正确')
                if isinstance(result,dict):
                    if not header.startswith('设置 ') or not header.endswith('：'): raise RuleError(f'第{n}行请使用“设置 名称：”')
                    raw_key=header[3:-1]; key=raw_key[3:] if raw_key.startswith('原名·') else internal(raw_key)
                    if not key or key in result: raise RuleError(f'第{n}行名称为空或重复')
                elif header!='添加：': raise RuleError(f'第{n}行请使用“添加：”')
                value,index=read(index+1,depth+2)
                if isinstance(result,dict): result[key]=value
                else: result.append(value)
            return result,index
        if text in {'是','否','空值'}: return {'是':True,'否':False,'空值':None}[text],index
        if text.startswith('数值：'):
            try:
                raw=text[3:]; value=float(raw) if any(c in raw for c in '.eE') else int(raw)
                if not math.isfinite(value): raise ValueError()
                return value,index
            except (ValueError,OverflowError): raise RuleError(f'第{line}行需要有限数值')
        if text.startswith('选项：'): return internal(text[3:]),index
        if text.startswith('文字：'):
            raw=text[3:]; out=''; i=0
            while i<len(raw):
                if raw[i]=='\\' and i+1<len(raw):
                    i+=1; out+={'n':'\n','r':'\r','\\':'\\'}.get(raw[i],'\\'+raw[i])
                else: out+=raw[i]
                i+=1
            return out,index
        raise RuleError(f'第{line}行请使用“文字：内容”“数值：数字”“是”“否”“记录：”或“列表：”')
    if not rows: raise RuleError('请填写固定句式')
    value,end=read(0,0)
    if end!=len(rows): raise RuleError('存在多余语句')
    return value
