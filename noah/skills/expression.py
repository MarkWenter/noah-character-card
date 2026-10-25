"""Small allowlisted expression interpreter, without eval, exec, imports or object access."""
import ast
import math
import operator

class RuleError(ValueError): pass
OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod,ast.FloorDiv:operator.floordiv}
CMP={ast.Eq:operator.eq,ast.NotEq:operator.ne,ast.Lt:operator.lt,ast.LtE:operator.le,ast.Gt:operator.gt,ast.GtE:operator.ge}
FUNCTIONS={'min':min,'max':max,'abs':abs,'round':round,'floor':math.floor,'ceil':math.ceil}

def bounded(value):
    if type(value) in (int,float):
        if not -1e9<=value<=1e9 or (isinstance(value,float) and not math.isfinite(value)): raise RuleError('表达式数值超出±10亿或不是有限值')
    elif isinstance(value,str) and len(value)>2000: raise RuleError('表达式文本结果过长')
    return value

def parse_expression(text):
    if not isinstance(text,str) or len(text)>2000: raise RuleError('表达式长度不得超过2000')
    try: tree=ast.parse(text,mode='eval')
    except (SyntaxError,RecursionError) as exc: raise RuleError('表达式语法错误：'+str(exc)) from exc
    if sum(1 for _ in ast.walk(tree))>200: raise RuleError('表达式过于复杂')
    allowed=(ast.Expression,ast.Constant,ast.Name,ast.Load,ast.Attribute,ast.Subscript,ast.BinOp,ast.UnaryOp,ast.BoolOp,ast.Compare,ast.Call,ast.IfExp,ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,*OPS,*CMP)
    for node in ast.walk(tree):
        if not isinstance(node,allowed): raise RuleError('不支持的表达式语法：'+type(node).__name__)
        if isinstance(node,ast.Name) and node.id.startswith('_'): raise RuleError('不允许内部名称')
        if isinstance(node,ast.Attribute) and node.attr.startswith('_'): raise RuleError('不允许内部字段')
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in FUNCTIONS or node.keywords or not 1<=len(node.args)<=8): raise RuleError('仅支持min/max/abs/round/floor/ceil函数')
        if isinstance(node,ast.Constant) and type(node.value) not in (int,float,str,bool,type(None)): raise RuleError('常量类型不支持')
        if isinstance(node,ast.Constant): bounded(node.value)
    return tree

def evaluate(text,context):
    tree=parse_expression(text)
    def visit(n):
        if isinstance(n,ast.Constant): return n.value
        if isinstance(n,ast.Name):
            if n.id not in context: raise RuleError('找不到变量：'+n.id)
            return context[n.id]
        if isinstance(n,(ast.Attribute,ast.Subscript)):
            obj=visit(n.value); key=n.attr if isinstance(n,ast.Attribute) else visit(n.slice)
            if not isinstance(obj,dict) or not isinstance(key,str) or key.startswith('_') or key not in obj: raise RuleError('字段不存在或不可访问：'+str(key))
            return obj[key]
        if isinstance(n,ast.BinOp):
            left,right=visit(n.left),visit(n.right)
            if type(left) not in (int,float) or type(right) not in (int,float): raise RuleError('算术运算只允许数值')
            return bounded(OPS[type(n.op)](left,right))
        if isinstance(n,ast.UnaryOp):
            value=visit(n.operand)
            if isinstance(n.op,ast.Not): return not value
            if type(value) not in (int,float): raise RuleError('符号运算需要数值')
            return bounded(-value if isinstance(n.op,ast.USub) else value)
        if isinstance(n,ast.BoolOp):
            for value in n.values:
                result=visit(value)
                if isinstance(n.op,ast.And) and not result: return False
                if isinstance(n.op,ast.Or) and result: return True
            return bool(result)
        if isinstance(n,ast.Compare):
            left=visit(n.left)
            for op,right_node in zip(n.ops,n.comparators):
                right=visit(right_node)
                if not CMP[type(op)](left,right): return False
                left=right
            return True
        if isinstance(n,ast.IfExp): return visit(n.body if visit(n.test) else n.orelse)
        if isinstance(n,ast.Call):
            args=[visit(a) for a in n.args]
            if n.func.id=='round' and (len(args)>2 or (len(args)==2 and (type(args[1]) is not int or not -12<=args[1]<=12))): raise RuleError('round的小数位数必须为-12～12的整数')
            return bounded(FUNCTIONS[n.func.id](*args))
        raise RuleError('不支持的表达式')
    try: return bounded(visit(tree.body))
    except RuleError: raise
    except (ArithmeticError,TypeError,ValueError,RecursionError) as exc: raise RuleError('表达式计算失败：'+str(exc)) from exc
