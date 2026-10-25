"""Typed, declarative operations; templates never contain executable Python."""
import copy

PORT_TYPES={'Flow','Number','Integer','Percent','Boolean','String','Entity','Object','Any'}
DEFINITION_KINDS={'Attribute','Resource','Status','Tag','Entity','Event','Scene','DamageType','Custom'}
EVENTS=['skill_used','attack_hit','damage_resolved','hp_changed','resource_changed','status_applied','status_changed','status_removed','turn_started','turn_ended','entity_died']
BUILTINS={}
def add(id,name,kind,op,inputs=None,outputs=None,params=None):
    BUILTINS[id]={'id':id,'name':name,'kind':kind,'op':op,'inputs':inputs or {},'outputs':outputs or {},'params':params or {},'description':''}
for event,label in zip(EVENTS,['技能使用','攻击命中','伤害结算','生命值变化','资源变化','状态施加','状态变化','状态移除','回合开始','回合结束','实体死亡']):
    add('event.'+event,label,'Event','event',outputs={'out':'Flow','source':'Entity','target':'Entity','event':'Object'},params={'event':event,'definition':'','skill':''})
add('condition.compare','数值比较','Condition','compare',{'in':'Flow','a':'Number','b':'Number'},{'true':'Flow','false':'Flow','result':'Boolean'},{'a':0,'b':0,'op':'>='})
add('condition.boolean','布尔判断','Condition','boolean',{'in':'Flow','value':'Boolean'},{'true':'Flow','false':'Flow','result':'Boolean'},{'value':True})
add('condition.tags','标签判断','Condition','tags',{'in':'Flow','target':'Entity'},{'true':'Flow','false':'Flow','result':'Boolean'},{'target':'target','tag':''})
add('math.calculate','计算表达式','Math','calculate',{'a':'Number','b':'Number'},{'value':'Number'},{'expression':'a + b','a':0,'b':0})
add('math.boolean','与或非','Math','logical',{'a':'Boolean','b':'Boolean'},{'value':'Boolean'},{'mode':'and','a':True,'b':False})
add('math.random','随机数','Math','random',outputs={'value':'Number'},params={'min':0,'max':1})
add('math.dice','骰子','Math','dice',outputs={'value':'Number'},params={'count':1,'sides':6})
for op,label in [('attribute','读取属性'),('resource','读取资源'),('status','读取状态')]:
    add('data.'+op,label,'Data','read_'+op,{'target':'Entity'},{'value':'Number'},{'target':'target','definition':''})
for who,label in [('source','获取事件来源'),('target','获取事件目标'),('self','获取当前实体')]:
    add('data.'+who,label,'Data','entity',outputs={'value':'Entity'},params={'who':who})
add('data.constant','常量','Data','constant',outputs={'value':'Any'},params={'value':0})
for op,label in [('apply_status','施加状态'),('remove_status','移除状态'),('change_resource','修改资源'),('set_resource','设置资源'),('damage','造成伤害'),('heal','治疗'),('set_attribute','设置属性')]:
    params={'target':'target','definition':'','value':1}
    if op=='apply_status': params['duration']=0
    add('effect.'+op,label,'Effect',op,{'in':'Flow','target':'Entity','value':'Number'},{'out':'Flow'},params)
add('effect.skill','技能可用性','Effect','set_skill',{'in':'Flow','target':'Entity','enabled':'Boolean'},{'out':'Flow'},{'target':'target','skill':'','enabled':True})
add('control.sequence','顺序执行','Control','sequence',{'in':'Flow'},{'first':'Flow','second':'Flow'})
add('control.stop','终止','Control','stop',{'in':'Flow'})
add('control.call','调用公共子图','Control','call',{'in':'Flow','args':'Object'},{'out':'Flow','value':'Any'},{'graph':'','args':{}})
add('graph.input','子图输入','Data','graph_input',outputs={'value':'Any'},params={'name':'value'})
add('graph.output','子图输出','Control','graph_output',{'in':'Flow','value':'Any'},{'out':'Flow'},{'name':'value','value':0})
add('rule.enabled','规则图开关','Rule','rule_enabled',{'in':'Flow'},{'out':'Flow'},{'graph':'','enabled':True})

add('data.variable','读取临时变量','Data','read_variable',outputs={'value':'Any'},params={'name':'temp.value','default':0})
add('effect.variable','设置临时变量','Effect','set_variable',{'in':'Flow','value':'Any'},{'out':'Flow'},{'name':'temp.value','value':0})
add('data.number','数值常量','Data','constant',outputs={'value':'Number'},params={'value':0})
add('data.boolean','布尔常量','Data','constant',outputs={'value':'Boolean'},params={'value':True})


def templates(bundle):
    result=copy.deepcopy(BUILTINS)
    result.update({t['id']:copy.deepcopy(t) for t in bundle['node_templates']})
    return result


def compatible(source,target):
    if source=='Flow' or target=='Flow': return source==target
    return source==target or target=='Any' or (source in {'Integer','Percent'} and target=='Number')
