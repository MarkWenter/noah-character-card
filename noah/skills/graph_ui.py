"""Interactive Tk Canvas node graph editor, with distinct typed flow and data ports."""
import copy
import json
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from pathlib import Path
from .chinese import dump as chinese_dump, parse as chinese_parse, label, internal
from .catalog import templates
from .document import GraphDocument
from .model import validate_bundle,validate_graph,graph_diagnostics
from .expression import RuleError
from .io import read_json,write_json,loads_json

COLORS={'Event':'#287f8b','Condition':'#9e6a2d','Data':'#3b6b9c','Math':'#6572b2','Effect':'#397a59','Control':'#80579c','Rule':'#a04f75'}

def edit_value(text):
    text=text.strip()
    if text.startswith(('记录：','列表：','文字：','数值：','选项：')) or text in {'是','否','空值'}: return chinese_parse(text)
    text=internal(text)
    if len(text)>100000: raise RuleError('参数内容过长')
    if text.startswith('='): return {'expr':text[1:]}
    try: return loads_json(text)
    except RecursionError as exc: raise RuleError('参数嵌套过深') from exc
    except json.JSONDecodeError: return text

def show_value(value):
    if isinstance(value,dict) and set(value)=={'expr'}: return '='+value['expr']
    return label(value) if isinstance(value,str) else chinese_dump(value)

class GraphEditor(tk.Toplevel):
    def __init__(self,parent,bundle,graph_id,on_save,card=None):
        super().__init__(parent); self.title('规则流程 · '+graph_id); self.geometry('1420x900'); self.minsize(1050,650); self.transient(parent); self.grab_set()
        self.card=copy.deepcopy(card); self.test_engine=None; self.test_bundle=None
        self.bundle=copy.deepcopy(bundle); graph=next(g for g in bundle['shared_rules'] if g['id']==graph_id)
        self.doc=GraphDocument(graph,templates(bundle)); self.original=copy.deepcopy(graph); self.on_save=on_save
        self.selected=set(); self.clipboard=''; self.zoom=1.; self.offset=[40,40]; self.port_positions={}; self.drag=None; self.connection=None; self.form_vars={}; self.form_node=None
        bar=ttk.Frame(self,padding=8); bar.pack(fill='x')
        actions=[('保存规则图',self.save),('取消',self.cancel),('验证',self.check),('测试当前图',self.test_current),('撤销',self.undo),('重做',self.redo),('复制',self.copy_nodes),('粘贴',self.paste),('删除',self.delete),('适应画布',self.fit),('导入JSON',self.import_json),('导出JSON',self.export_json),('子图接口',self.interfaces)]
        for index,(name,action) in enumerate(actions):
            ttk.Button(bar,text=name,command=action,width=8).grid(row=index//7,column=index%7,sticky='ew',padx=3,pady=3)
            bar.columnconfigure(index%7,weight=1)
        panes=ttk.Panedwindow(self,orient='horizontal'); self.panes=panes; panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes,padding=8); center=ttk.Frame(panes); right=ttk.Frame(panes,padding=8); panes.add(left,weight=1); panes.add(center,weight=5); panes.add(right,weight=2)
        ttk.Label(left,text='节点库',style='Metric.TLabel').pack(anchor='w')
        ttk.Label(left,text='搜索后双击添加，或拖入画布',style='Hint.TLabel',wraplength=210).pack(anchor='w')
        self.search=tk.StringVar(); ttk.Entry(left,textvariable=self.search,width=22).pack(fill='x',pady=8); self.search.trace_add('write',lambda *a:self.library())
        self.lib=tk.Listbox(left,width=24,font=('Microsoft YaHei UI',9),exportselection=False); self.lib.pack(fill='both',expand=True); self.lib.bind('<Double-1>',lambda e:self.add_from_library())
        self.lib.bind('<ButtonRelease-1>',self.drop_library)
        ttk.Button(left,text='添加选中节点',command=self.add_from_library).pack(fill='x',pady=8)
        self.canvas=tk.Canvas(center,bg='#192632',highlightthickness=0); self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self.press); self.canvas.bind('<B1-Motion>',self.motion); self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Button-2>',self.pan_start); self.canvas.bind('<B2-Motion>',self.pan_move); self.canvas.bind('<Button-3>',self.right_click)
        self.canvas.bind('<MouseWheel>',self.wheel); self.canvas.bind('<Configure>',lambda e:self.draw())
        for key,fn in [('<Delete>',self.delete),('<Control-z>',self.undo),('<Control-y>',self.redo),('<Control-c>',self.copy_nodes),('<Control-v>',self.paste)]: self.canvas.bind(key,lambda e,f=fn:f())
        ttk.Label(right,text='节点参数',style='Metric.TLabel').pack(anchor='w')
        from ..ui import ScrollPage
        scroll=ScrollPage(right); scroll.pack(fill='both',expand=True); self.properties=scroll.content
        ttk.Button(right,text='应用参数',command=self.apply_params).pack(fill='x',pady=6)
        self.log=tk.Text(self,height=5,wrap='word',font=('Microsoft YaHei UI',9),bg='#eef4f7',relief='flat'); self.log.pack(fill='x')
        self.note('白色端口为执行流，蓝色端口为数据流。拖动节点；点击输出端口后点击输入端口连线；右键连线断开。空白拖动框选；中键平移；滚轮缩放。')
        self.protocol('WM_DELETE_WINDOW',self.cancel); self.library(); self._fit_job=self.after_idle(self.layout)
    def destroy(self):
        if hasattr(self,'_fit_job'):
            try: self.after_cancel(self._fit_job)
            except tk.TclError: pass
        parent=self.master
        super().destroy()
        try:
            if isinstance(parent,tk.Toplevel) and parent.winfo_exists(): parent.grab_set()
        except tk.TclError: pass

    def layout(self):
        width=self.panes.winfo_width()
        if width>700:
            self.panes.sashpos(0,235); self.panes.sashpos(1,width-320)
        self._fit_job=self.after_idle(self.fit)

    def note(self,text): self.log.delete('1.0','end'); self.log.insert('1.0',text)
    def library(self):
        query=self.search.get().lower(); self.lib_ids=[]; self.lib.delete(0,'end')
        for id,t in self.doc.registry.items():
            if query in (t['name']+' '+id+' '+t['kind']).lower(): self.lib_ids.append(id); self.lib.insert('end',label(t['kind'])+' · '+t['name'])
    def world(self,x,y): return ((x-self.offset[0])/self.zoom,(y-self.offset[1])/self.zoom)
    def screen(self,x,y): return (x*self.zoom+self.offset[0],y*self.zoom+self.offset[1])
    def add_from_library(self,position=None):
        choice=self.lib.curselection()
        if not choice: return
        point=position or self.world(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2)
        try: id=self.doc.add_node(self.lib_ids[choice[0]],point); self.selected={id}; self.draw(); self.properties_for(id)
        except RuleError as exc: self.note(str(exc))
    def drop_library(self,event):
        x=event.x_root-self.canvas.winfo_rootx(); y=event.y_root-self.canvas.winfo_rooty()
        if 0<=x<self.canvas.winfo_width() and 0<=y<self.canvas.winfo_height(): self.add_from_library(self.world(x,y))
    def draw(self):
        c=self.canvas; c.delete('all'); self.port_positions={}; z=self.zoom
        spacing=40*z
        if spacing>=10:
            for x in range(int(self.offset[0]%spacing),max(1,c.winfo_width()),max(1,int(spacing))): c.create_line(x,0,x,c.winfo_height(),fill='#223440')
            for y in range(int(self.offset[1]%spacing),max(1,c.winfo_height()),max(1,int(spacing))): c.create_line(0,y,c.winfo_width(),y,fill='#223440')
        for n in self.doc.graph['nodes']:
            t=self.doc.registry[n['template']]; x,y=self.screen(*n['position']); width=240*z; height=(62+max(len(t['inputs']),len(t['outputs']),1)*28)*z
            tags=('node',n['id']); c.create_rectangle(x,y,x+width,y+height,fill='#293c4a',outline='#f4ce73' if n['id'] in self.selected else '#476173',width=3 if n['id'] in self.selected else 1,tags=tags)
            c.create_rectangle(x,y,x+width,y+32*z,fill=COLORS[t['kind']],outline='',tags=tags)
            c.create_text(x+12*z,y+16*z,text=t['name'],anchor='w',fill='white',font=('Microsoft YaHei UI',max(6,int(10*z)),'bold'),tags=tags)
            for side,key in [('input','inputs'),('output','outputs')]:
                for i,(port,kind) in enumerate(t[key].items()):
                    px=x if side=='input' else x+width; py=y+(52+i*28)*z
                    identity=(n['id'],side,port); self.port_positions[identity]=(px,py)
                    radius=max(4,6*z); tag='port:'+json.dumps(identity,ensure_ascii=False)
                    c.create_oval(px-radius,py-radius,px+radius,py+radius,fill='#ffffff' if kind=='Flow' else '#57c2e6',outline='#172630',tags=('port',tag))
                    c.create_text(px+(12*z if side=='input' else -12*z),py,text=label(port),anchor='w' if side=='input' else 'e',fill='#e3edf4',font=('Microsoft YaHei UI',max(6,int(8*z))),tags=tags)
        for index,edge in enumerate(self.doc.graph['edges']):
            a=self.port_positions.get((edge['from'][0],'output',edge['from'][1])); b=self.port_positions.get((edge['to'][0],'input',edge['to'][1]))
            if a and b:
                bend=max(40*z,abs(b[0]-a[0])/2)
                line=c.create_line(*a,a[0]+bend,a[1],b[0]-bend,b[1],*b,smooth=True,width=max(2,3*z),fill='#f3f1d7' if edge['kind']=='flow' else '#4fc5e9',arrow='last',tags=('edge','edge:'+str(index))); c.tag_lower(line)
        c.tag_raise('port')
        c.create_text(12,12,anchor='nw',text=f'{int(z*100)}%  ·  {len(self.doc.graph["nodes"])} 节点',fill='#90aebb',font=('Microsoft YaHei UI',9))
    def hit_port(self,x,y):
        for identity,point in self.port_positions.items():
            if (point[0]-x)**2+(point[1]-y)**2<=144: return identity
    def press(self,event):
        self.canvas.focus_set(); port=self.hit_port(event.x,event.y)
        if port:
            if port[1]=='output': self.connection=port
            elif self.connection:
                try: self.doc.connect(self.connection[0],self.connection[2],port[0],port[2]); self.note('已连接；撤销可恢复。')
                except (RuleError,KeyError) as exc: self.note('连线无效：'+str(exc))
                self.connection=None; self.draw()
            return
        current=self.canvas.find_withtag('current'); tags=self.canvas.gettags(current[0]) if current else ()
        if 'node' in tags:
            id=tags[1]
            if event.state&1: self.selected.symmetric_difference_update({id})
            elif id not in self.selected: self.selected={id}
            self.drag=('nodes',self.world(event.x,event.y),{n['id']:list(n['position']) for n in self.doc.graph['nodes'] if n['id'] in self.selected})
            self.properties_for(id); self.draw()
        else:
            if not event.state&1: self.selected=set()
            self.drag=('select',(event.x,event.y)); self.draw()
    def motion(self,event):
        if self.connection:
            self.canvas.delete('rubber'); x,y=self.port_positions[self.connection]; self.canvas.create_line(x,y,event.x,event.y,fill='#edc96e',width=2,tags='rubber'); return
        if not self.drag: return
        if self.drag[0]=='nodes':
            start,positions=self.drag[1:]; end=self.world(event.x,event.y)
            for node in self.doc.graph['nodes']:
                if node['id'] in positions: node['position']=[positions[node['id']][0]+end[0]-start[0],positions[node['id']][1]+end[1]-start[1]]
            self.draw()
        else:
            self.canvas.delete('selection'); self.canvas.create_rectangle(*self.drag[1],event.x,event.y,outline='#e9c776',dash=(4,3),tags='selection')
    def release(self,event):
        if self.connection:
            port=self.hit_port(event.x,event.y)
            if port and port[1]=='input': self.press(event)
            self.canvas.delete('rubber')
        if not self.drag: return
        if self.drag[0]=='nodes':
            old=self.drag[2]; new={n['id']:list(n['position']) for n in self.doc.graph['nodes'] if n['id'] in old}
            for n in self.doc.graph['nodes']:
                if n['id'] in old: n['position']=old[n['id']]
            try: self.doc.move(new)
            except RuleError as exc: self.note(str(exc))
        else:
            a=self.world(*self.drag[1]); b=self.world(event.x,event.y)
            for n in self.doc.graph['nodes']:
                x,y=n['position']
                if min(a[0],b[0])<=x<=max(a[0],b[0]) and min(a[1],b[1])<=y<=max(a[1],b[1]): self.selected.add(n['id'])
        self.drag=None; self.draw()
    def pan_start(self,event): self.pan_origin=(event.x,event.y,*self.offset)
    def pan_move(self,event):
        x,y,ox,oy=self.pan_origin; self.offset=[ox+event.x-x,oy+event.y-y]; self.draw()
    def wheel(self,event):
        point=self.world(event.x,event.y); self.zoom=max(.35,min(2.,self.zoom*(1.12 if event.delta>0 else 1/1.12))); self.offset=[event.x-point[0]*self.zoom,event.y-point[1]*self.zoom]; self.draw(); return 'break'
    def right_click(self,event):
        items=self.canvas.find_overlapping(event.x-5,event.y-5,event.x+5,event.y+5)
        for item in reversed(items):
            tags=self.canvas.gettags(item)
            if 'edge' in tags:
                try: self.doc.disconnect(int(next(t[5:] for t in tags if t.startswith('edge:')))); self.draw()
                except RuleError as exc: self.note(str(exc))
                return
        self.connection=None; self.note('已取消待连接端口。')
    def properties_for(self,id):
        if self.form_node and self.form_node!=id and any(n['id']==self.form_node for n in self.doc.graph['nodes']):
            if not self.apply_params(): return
        for w in self.properties.winfo_children(): w.destroy()
        self.form_node=id; self.form_vars={}; n=next(n for n in self.doc.graph['nodes'] if n['id']==id); t=self.doc.registry[n['template']]
        ttk.Label(self.properties,text=t['name'],style='Metric.TLabel',wraplength=270).pack(anchor='w',pady=8)
        ttk.Label(self.properties,text=id,style='Hint.TLabel',wraplength=270).pack(anchor='w')
        ttk.Label(self.properties,text='数值直接填写；是或否表示开关。\n复杂内容使用中文固定句式；= 后填写计算式。',wraplength=270).pack(anchor='w',pady=8)
        params={**copy.deepcopy(t['params']),**{k:('target' if v=='Entity' else False if v=='Boolean' else 0) for k,v in t['inputs'].items() if v!='Flow' and k not in t['params']},**n['params']}
        for key,value in params.items():
            connected=any(e['kind']=='data' and e['to']==[id,key] for e in self.doc.graph['edges'])
            ttk.Label(self.properties,text=label(key)+(' · 连线值优先' if connected else '')).pack(anchor='w',pady=(6,0)); var=tk.StringVar(value=show_value(value)); self.form_vars[key]=var
            choices=[]
            if key in {'definition','tag'}: choices=[d['id'] for d in self.bundle['definitions']]+['力量','敏捷','耐受','魅力','智力','感知','意志','HP','MP','TP']
            elif key=='skill': choices=[s['id'] for s in self.bundle['skills']]
            elif key=='graph': choices=[g['id'] for g in self.bundle['shared_rules'] if g['id']!=self.doc.graph['id']]
            elif key=='op': choices=['>=','>','<=','<','==','!=']
            elif key=='target': choices=['target','source','self','A','B']
            choices=[label(v) for v in choices]
            if isinstance(value,(dict,list)) and not (isinstance(value,dict) and set(value)=={'expr'}):
                from ..widgets import LongText
                holder=LongText(self.properties,lambda:None,label(key)); holder.pack(fill='x'); holder.text.insert('1.0',show_value(value)); self.form_vars[key]=holder.text; continue
            widget=ttk.Combobox(self.properties,textvariable=var,values=choices,width=24) if choices else ttk.Entry(self.properties,textvariable=var,width=24)
            widget.pack(fill='x',pady=3)
    def apply_params(self):
        if self.form_node is None: return True
        try:
            values={k:edit_value(v.get('1.0','end-1c') if isinstance(v,tk.Text) else v.get()) for k,v in self.form_vars.items()}; id=self.form_node
            self.doc.mutate(lambda g:next(n for n in g['nodes'] if n['id']==id).update(params=values)); self.draw(); return True
        except (RuleError,StopIteration) as exc: self.note('参数未应用：'+str(exc)); return False
    def delete(self): self.doc.delete(self.selected); self.selected=set(); self.form_node=None; self.draw()
    def copy_nodes(self): self.clipboard=self.doc.copy(self.selected); self.note('已复制所选节点与内部连线。')
    def paste(self):
        if not self.clipboard: return
        try: self.selected=self.doc.paste(self.clipboard); self.draw()
        except RuleError as exc: self.note(str(exc))
    def undo(self): self.doc.undo(); self.form_node=None; self.draw()
    def redo(self): self.doc.redo(); self.form_node=None; self.draw()
    def fit(self):
        if not self.doc.graph['nodes']: self.draw(); return
        xs=[n['position'][0] for n in self.doc.graph['nodes']]; ys=[n['position'][1] for n in self.doc.graph['nodes']]
        self.zoom=max(.35,min(1.,(max(400,self.canvas.winfo_width())-100)/(max(xs)-min(xs)+300),(max(350,self.canvas.winfo_height())-100)/(max(ys)-min(ys)+240))); self.offset=[40-min(xs)*self.zoom,50-min(ys)*self.zoom]; self.draw()
    def check(self):
        if not self.apply_params(): return False
        proposed=copy.deepcopy(self.bundle); proposed['shared_rules']=[self.doc.graph if g['id']==self.doc.graph['id'] else g for g in proposed['shared_rules']]
        try:
            validate_bundle(proposed); issues=graph_diagnostics(self.doc.graph,self.doc.registry)
            self.note('结构检查通过，可保存草稿。\n待完善：\n'+'\n'.join(issues) if issues else '类型、端口、引用和无环检查通过。未连接端口使用参数默认值；执行结果请在模拟页检查。'); return True
        except RuleError as exc: self.note('验证失败：'+str(exc)); return False
    def test_current(self):
        if not self.check(): return
        issues=graph_diagnostics(self.doc.graph,self.doc.registry)
        if issues: self.note('请先完善规则图：\n'+'\n'.join(issues)); return
        from .engine import Runtime,Engine,entity_from_card
        from ..domain import new_card
        proposed=copy.deepcopy(self.bundle)
        proposed['shared_rules']=[self.doc.graph if g['id']==self.doc.graph['id'] else g for g in proposed['shared_rules']]
        try:
            if self.test_bundle!=proposed:
                card=copy.deepcopy(self.card) if self.card else new_card(); card['talent_derivations']=proposed
                runtime=Runtime([entity_from_card(card,'A'),entity_from_card(card,'B')]); self.test_engine=Engine(proposed,runtime); self.test_bundle=copy.deepcopy(proposed)
            first=next((n for n in self.doc.graph['nodes'] if self.doc.registry[n['template']]['op']=='event'),None)
            if first is None: raise RuleError('当前图无事件入口；请通过调用节点或模拟页测试子图')
            params={**self.doc.registry[first['template']]['params'],**first['params']}
            if params['event']=='skill_used':
                skill=next((v for v in proposed['skills'] if v['graph_id']==self.doc.graph['id']),None)
                if not skill: raise RuleError('请先将技能绑定到此图，或在模拟页指定技能测试公共机制')
                self.test_engine.use_skill(skill['id'])
            else: self.test_engine.emit(params['event'],'A','B',{'definition':params.get('definition','')})
            runtime=self.test_engine.runtime
            self.note('连续点击会复用测试副本；规则修改后自动重置。\nB状态：'+json.dumps(runtime.entities['B']['statuses'],ensure_ascii=False)+'\n'+'\n'.join(f"{v['event']} [{v['graph']} / {v['node']}] {v['message']}" for v in runtime.log[-80:])); self.log.see('end')
        except RuleError as exc: self.note('测试失败：'+str(exc))

    def save(self):
        if self.check(): self.on_save(copy.deepcopy(self.doc.graph)); self.destroy()
    def cancel(self):
        # Explicit Cancel discards the entire editing transaction.
        self.destroy()
    def export_json(self):
        if not self.check(): return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',filetypes=[('规则图JSON','*.json')])
        if path:
            try: write_json(path,self.doc.graph,500000)
            except (OSError,RuleError) as exc: self.note(str(exc))
    def import_json(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('规则图JSON','*.json')])
        if not path: return
        try:
            graph=read_json(path,500000); graph['id']=self.doc.graph['id']; validate_graph(graph,self.doc.registry)
            self.doc.snapshot(); self.doc.graph=graph; self.form_node=None; self.fit()
        except (OSError,ValueError,TypeError) as exc: self.note('导入失败：'+str(exc))
    def interfaces(self):
        win=tk.Toplevel(self); win.title('子图数据接口'); win.geometry('540x420'); win.transient(self); win.grab_set()
        ttk.Label(win,text='声明外部输入与输出：名称 → 端口类型。\n内部使用“子图输入/输出”节点，调用时通过传入数据填写。\n使用“记录：”“设置 输入接口：”等固定句式。',padding=12).pack()
        editor=tk.Text(win,height=12); editor.pack(fill='both',expand=True,padx=12); editor.insert('1.0',chinese_dump({k:self.doc.graph.get(k,{}) for k in ['inputs','outputs']}))
        def apply():
            try:
                value=chinese_parse(editor.get('1.0','end-1c'))
                if not isinstance(value,dict) or set(value)!={'inputs','outputs'}: raise RuleError('仅填写输入接口与输出接口')
                self.doc.mutate(lambda g:g.update(value)); win.destroy()
            except (ValueError,RuleError) as exc: messagebox.showerror('接口错误',str(exc),parent=win)
        ttk.Button(win,text='应用接口',command=apply).pack(pady=10)
