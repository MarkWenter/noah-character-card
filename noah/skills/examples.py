"""Editable end-to-end sample, deliberately implemented entirely as graphs."""
from .model import empty_bundle,new_graph,new_skill
from .ndsl import parse_ndsl

DEFINITIONS='''定义词 压抑:
    ID: status.suppression
    类型: Status
    分类: 负面, 精神
    数据类型: Integer
    默认值: 0
    最小值: 0
    最大值: 3
    可叠加: true
    可驱散: true

定义词 恐惧:
    ID: status.fear
    类型: Status
    数据类型: Integer
    默认值: 0
    最小值: 0
    最大值: 1
    可叠加: false
    可驱散: true
'''

def sample_bundle():
    b=empty_bundle(); b['definitions']=parse_ndsl(DEFINITIONS)['definitions']
    def node(id,template,x,y,**params): return {'id':id,'template':template,'params':params,'position':[x,y]}
    def edge(a,ap,b,bp,kind='flow'): return {'from':[a,ap],'to':[b,bp],'kind':kind}
    graph=new_graph('graph.pressure','施加压抑','skill')
    graph['nodes']=[node('use','event.skill_used',40,80,skill='skill.pressure'),node('apply','effect.apply_status',360,80,definition='status.suppression',value=1)]
    graph['edges']=[edge('use','out','apply','in')]
    conversion=new_graph('graph.conversion','压抑转为恐惧','shared')
    conversion['nodes']=[node('changed','event.status_changed',30,80,definition='status.suppression'),node('stacks','data.status',30,350,definition='status.suppression'),node('compare','condition.compare',360,80,b=3,op='>='),node('remove','effect.remove_status',680,50,definition='status.suppression'),node('fear','effect.apply_status',1000,50,definition='status.fear',value=1)]
    conversion['edges']=[edge('changed','out','compare','in'),edge('stacks','value','compare','a','data'),edge('compare','true','remove','in'),edge('remove','out','fear','in')]
    unlock=new_graph('graph.unlock','根据恐惧解锁技能','shared')
    unlock['nodes']=[node('event','event.status_changed',30,70,definition='status.fear'),node('read','data.status',30,330,definition='status.fear'),node('check','condition.compare',350,70,b=0,op='>'),node('yes','effect.skill',680,50,skill='skill.fear_power',enabled=True),node('no','effect.skill',680,330,skill='skill.fear_power',enabled=False)]
    unlock['edges']=[edge('event','out','check','in'),edge('read','value','check','a','data'),edge('check','true','yes','in'),edge('check','false','no','in')]
    pressure=new_skill('skill.pressure','施压','graph.pressure'); pressure['description']='向指定目标施加1层压抑。达到3层时由公共规则图转为恐惧。';pressure['references']=['status.suppression']
    fear=new_skill('skill.fear_power','恐惧共鸣');fear['type']='passive';fear['initially_available']=False;fear['description']='用于演示状态变化解锁与锁定。';fear['references']=['status.fear']
    b['skills']=[pressure,fear];b['shared_rules']=[graph,conversion,unlock]
    return b
