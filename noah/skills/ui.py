"""Transactional skill/resource forms and isolated simulation, integrated into talent UI."""
import copy
import json
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from pathlib import Path
import uuid
from ..widgets import LongText
from .chinese import dump as chinese_dump, parse as chinese_parse, label as chinese_label, internal
from .catalog import BUILTINS,DEFINITION_KINDS,EVENTS,templates
from .model import empty_bundle,new_skill,new_graph,validate_bundle,validate_definition,validate_template,references,rename_resource,graph_diagnostics
from .expression import RuleError
from .ndsl import parse_ndsl,dump_definition,dump_template
from .graph_ui import GraphEditor,edit_value,show_value
from .examples import sample_bundle
from .engine import Runtime,Engine,entity_from_card
from .io import read_json,write_json

LABELS={'skills':'技能','definitions':'定义词','node_templates':'自定义节点','shared_rules':'规则图'}

class Modal(tk.Toplevel):
    def destroy(self):
        parent=self.master
        super().destroy()
        if isinstance(parent,tk.Toplevel) and parent.winfo_exists(): parent.grab_set()

class ResourceEditor(Modal):
    def __init__(self,parent,collection,value,bundle,on_save):
        super().__init__(parent); self.title('编辑'+LABELS[collection]); self.geometry('900x790'); self.minsize(650,500); self.transient(parent); self.grab_set()
        self.collection=collection; self.value=copy.deepcopy(value); self.on_save=on_save; self.variables={}; self.texts={}; self.bundle=bundle
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill='both',expand=True,padx=12,pady=12)
        from ..ui import ScrollPage
        page=ScrollPage(self.tabs); self.tabs.add(page,text='表单'); self.form=page.content
        self.build_form()
        self.ndsl_text=None
        if collection in {'definitions','node_templates'}:
            nd=ttk.Frame(self.tabs,padding=12); self.tabs.add(nd,text='中文句式')
            self.ndsl_text=LongText(nd,lambda:None,'中文固定句式'); self.ndsl_text.pack(fill='both',expand=True); self.ndsl_text.text.configure(height=23)
            self.ndsl_text.text.insert('1.0',chinese_dump(value))
            ttk.Button(nd,text='从表单生成句式',command=self.form_to_ndsl).pack(anchor='w',pady=8)
        footer=ttk.Frame(self,padding=12); footer.pack(fill='x')
        ttk.Label(footer,text='保存采用当前页内容；取消不修改资源。',style='Hint.TLabel').pack(side='left')
        ttk.Button(footer,text='保存',command=self.save).pack(side='right'); ttk.Button(footer,text='取消',command=self.destroy).pack(side='right',padx=8)
    def entry(self,key,label,value,choices=None,multiline=False):
        ttk.Label(self.form,text=label).pack(anchor='w',pady=(8,3))
        if isinstance(value,(dict,list)):
            multiline=True; value=chinese_dump(value)
        if multiline:

            if key in {'references','categories','tags','fields','inputs','outputs','params'}:
                ttk.Label(self.form,text='固定句式：记录： → 设置 名称： → 文字：内容 / 数值：数字 / 是 / 否；每层缩进四个空格。列表使用“添加：”。',wraplength=740,style='Hint.TLabel').pack(anchor='w')
            control=LongText(self.form,lambda:None,label); control.pack(fill='x'); control.text.insert('1.0',value); self.texts[key]=control.text
        else:
            var=tk.StringVar(value=show_value(value)); self.variables[key]=var
            control=ttk.Combobox(self.form,textvariable=var,values=[chinese_label(v) if isinstance(v,str) else v for v in choices],state='readonly') if choices else ttk.Entry(self.form,textvariable=var)
            control.pack(fill='x',pady=3)
        return control
    def build_form(self):
        v=self.value; self.entry('id','内部标识（自动生成，通常无需修改）',v['id']); self.entry('name','名称',v['name'])
        if self.collection=='skills':
            self.entry('type','类别',v['type'],['active','passive','reaction','permanent'])
            self.entry('graph_id','关联规则图（可留空，稍后从技能列表编辑流程）',v['graph_id'],['']+[g['id'] for g in self.bundle['shared_rules']])
            for k,label in [('cost','消耗说明'),('cooldown','冷却说明')]: self.entry(k,label,v.get(k,''))
            self.entry('enabled','启用技能',v['enabled'],['是','否']); self.entry('initially_available','模拟时初始可用',v.get('initially_available',True),['是','否'])
            self.entry('references','引用的定义词（固定句式列表）',v.get('references',[]))
            self.entry('description','自然语言技能说明',v['description'],multiline=True)
        elif self.collection=='definitions':
            self.entry('kind','定义词类别',v['kind'],sorted(DEFINITION_KINDS)); self.entry('value_type','数据类型',v.get('value_type','integer'),['integer','number','boolean','string','object'])
            self.entry('default','默认内容（数值、是/否，或文字）',v.get('default',0))
            self.entry('min','最小值（可留空）',v.get('min','')); self.entry('max','最大值（可留空）',v.get('max',''))
            self.entry('categories','分类（固定句式列表）',v.get('categories',[])); self.entry('tags','标签（固定句式列表）',v.get('tags',[]))
            self.entry('stackable','可叠加',v.get('stackable',True),['是','否']); self.entry('dispellable','可驱散',v.get('dispellable',True),['是','否'])
            self.entry('fields','附加数据（中文固定句式）',v.get('fields',{}))
            self.entry('description','描述',v.get('description',''),multiline=True)
        elif self.collection=='node_templates':
            base=next(k for k,t in BUILTINS.items() if t['op']==v['op']); self.base=tk.StringVar(value=BUILTINS[base]['name'])
            ttk.Label(self.form,text='基础模板（固定内置操作）').pack(anchor='w',pady=8)
            box=ttk.Combobox(self.form,textvariable=self.base,values=[t['name'] for t in BUILTINS.values()],state='readonly'); box.pack(fill='x'); box.bind('<<ComboboxSelected>>',self.change_base)
            self.entry('inputs','传入内容（固定句式）',v['inputs']); self.entry('outputs','传出内容（固定句式）',v['outputs'])
            self.entry('params','默认设置（固定句式）',v['params'],multiline=False)
            self.entry('description','描述',v.get('description',''),multiline=True)
        else:
            self.entry('kind','图类别',v['kind'],['skill','shared','scene']); self.entry('enabled','启用规则图',v['enabled'],['是','否'])
    def change_base(self,event=None):
        t=next(t for t in BUILTINS.values() if t['name']==self.base.get())
        for key in ['inputs','outputs','params']:
            widget=self.texts[key]; widget.delete('1.0','end'); widget.insert('1.0',chinese_dump(t[key]))
    def read_form(self):
        v=copy.deepcopy(self.value)
        raw={k:var.get() for k,var in self.variables.items()}
        for key,value in raw.items():
            if key in {'id','name','type','kind','value_type','graph_id','cost','cooldown'}: v[key]=internal(value) if key in {'type','kind','value_type'} else value
            elif key in {'min','max'} and value=='': v.pop(key,None)
            else: v[key]=edit_value(value)
        for key,widget in self.texts.items():
            text=widget.get('1.0','end-1c'); v[key]=chinese_parse(text) if key in {'references','categories','tags','fields','inputs','outputs','params'} else text
        if self.collection=='node_templates': base=next(t for t in BUILTINS.values() if t['name']==self.base.get()); v['op']=base['op']; v['kind']=base['kind']
        if self.collection=='definitions': validate_definition(v)
        if self.collection=='node_templates': validate_template(v)
        return v
    def form_to_ndsl(self):
        try:
            v=self.read_form(); text=chinese_dump(v)
            self.ndsl_text.text.delete('1.0','end'); self.ndsl_text.text.insert('1.0',text)
        except RuleError as exc: messagebox.showerror('表单无效',str(exc),parent=self)
    def save(self):
        try:
            if self.ndsl_text and self.tabs.index('current')==1:
                value=chinese_parse(self.ndsl_text.text.get('1.0','end-1c'))
            else: value=self.read_form()
            if not isinstance(value,dict) or not isinstance(value.get('id'),str) or not isinstance(value.get('name'),str): raise RuleError('请保留标识和名称设置')
            if self.collection=='definitions': validate_definition(value)
            if self.collection=='node_templates': validate_template(value)
            self.on_save(value); self.destroy()
        except (RuleError,ValueError) as exc: messagebox.showerror('无法保存',str(exc),parent=self)

class TalentManager(Modal):
    def __init__(self,parent,card,on_apply,selected_skill=None):
        super().__init__(parent); self.title('天赋衍生 · 技能与规则资源'); self.geometry('1180x830'); self.minsize(1050,650); self.transient(parent); self.grab_set()
        self.card=copy.deepcopy(card); self.bundle=copy.deepcopy(card.get('talent_derivations',empty_bundle())); self.on_apply=on_apply; self.views={}; self.sim_engine=None
        toolbar=ttk.Frame(self,padding=10); toolbar.pack(fill='x')
        ttk.Button(toolbar,text='应用到人物卡',command=self.apply).pack(side='right')
        ttk.Button(toolbar,text='取消本次编辑',command=self.destroy).pack(side='right',padx=8)
        for label,fn in [('载入完整示例',self.example),('导入资源JSON',self.import_bundle),('导出资源JSON',self.export_bundle),('批量中文声明',self.batch_ndsl)]: ttk.Button(toolbar,text=label,command=fn).pack(side='left',padx=3)
        ttk.Label(self,text='所有编辑先保存在此窗口；点击“应用到人物卡”后参与主窗口的保存、备份与自动草稿。取消可放弃本次所有更改。',style='Hint.TLabel',padding=10).pack(fill='x')
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill='both',expand=True,padx=12,pady=8)
        for collection in ['skills','definitions','node_templates','shared_rules']: self.resource_tab(collection)
        self.sim_tab(); self.refresh()
        if selected_skill and self.views['skills']['tree'].exists(selected_skill): self.views['skills']['tree'].selection_set(selected_skill)
    def resource_tab(self,collection):
        page=ttk.Frame(self.tabs,padding=12); self.tabs.add(page,text=LABELS[collection]); top=ttk.Frame(page); top.pack(fill='x')
        query=tk.StringVar(); ttk.Label(top,text='搜索名称 / ID / 类别').pack(side='left'); ttk.Entry(top,textvariable=query,width=30).pack(side='left',padx=8)
        actions=ttk.Frame(page); actions.pack(fill='x',pady=(10,0))
        for label,cmd in [('新建',lambda:self.create(collection)),('编辑',lambda:self.edit(collection)),('删除',lambda:self.delete_resource(collection)),('查看引用',lambda:self.show_references(collection))]: ttk.Button(actions,text=label,command=cmd).pack(side='left',padx=3)
        if collection in {'skills','shared_rules'}: ttk.Button(actions,text='编辑流程',command=lambda:self.open_graph(collection)).pack(side='left',padx=4)
        tree=ttk.Treeview(page,columns=['name','id','kind','description'],show='headings',height=11)
        for key,label,width in [('name','名称',180),('id','ID',230),('kind','类别 / 规则图',180),('description','简介',420)]: tree.heading(key,text=label); tree.column(key,width=width,minwidth=100)
        bar=ttk.Scrollbar(page,command=tree.yview); tree.configure(yscrollcommand=bar.set); bar.pack(side='right',fill='y',pady=12); tree.pack(fill='both',expand=True,pady=12)
        tree.bind('<Double-1>',lambda e:self.edit(collection)); self.views[collection]={'tree':tree,'query':query}; query.trace_add('write',lambda *a:self.refresh_collection(collection))
    def refresh_collection(self,collection):
        view=self.views[collection]; tree=view['tree']; selection=tree.selection(); tree.delete(*tree.get_children()); query=view['query'].get().lower()
        for v in self.bundle[collection]:
            if query not in json.dumps(v,ensure_ascii=False).lower(): continue
            kind=chinese_label(v.get('type',v.get('kind',''))); description=v.get('description','')
            if collection=='skills':
                graph=next((g for g in self.bundle['shared_rules'] if g['id']==v['graph_id']),None)
                kind+=(' · 草稿待完善' if graph and graph_diagnostics(graph,templates(self.bundle)) else ' · 有规则图' if graph else ' · 纯文本')
            tree.insert('', 'end',iid=v['id'],values=[v['name'],v['id'],kind,description[:130].replace('\n',' ')])
        for id in selection:
            if tree.exists(id): tree.selection_add(id)
    def refresh(self):
        for collection in self.views: self.refresh_collection(collection)
        if hasattr(self,'sim_skill'): self.sim_skill.configure(values=[s['id'] for s in self.bundle['skills']])
        if hasattr(self,'event_box'): self.event_box.configure(values=[chinese_label(e) for e in EVENTS]+[d['id'] for d in self.bundle['definitions'] if d['kind']=='Event'])
    def selected(self,collection):
        choice=self.views[collection]['tree'].selection()
        return next((v for v in self.bundle[collection] if choice and v['id']==choice[0]),None)
    def store(self,collection,value,old=None):
        proposed=copy.deepcopy(self.bundle)
        if old is not None and old!=value['id']: proposed=rename_resource(proposed,collection,old,value['id'])
        if old is None and any(v['id']==value['id'] for v in proposed[collection]): raise RuleError('该ID已存在')
        proposed[collection]=[v for v in proposed[collection] if v['id']!=value['id']]+[copy.deepcopy(value)]
        validate_bundle(proposed); self.bundle=proposed; self.refresh()
    def create(self,collection):
        suffix=uuid.uuid4().hex[:8]
        if collection=='skills': value=new_skill('skill.'+suffix,'新技能')
        elif collection=='definitions': value={'id':'status.'+suffix,'name':'新定义词','kind':'Status','value_type':'integer','default':0,'min':0,'max':3,'stackable':True,'dispellable':True}
        elif collection=='node_templates': value=copy.deepcopy(BUILTINS['condition.compare']); value.update(id='node.'+suffix,name='自定义比较')
        else: value=new_graph('graph.'+suffix,'新规则图','shared')
        ResourceEditor(self,collection,value,self.bundle,lambda value:self.store(collection,value))
    def edit(self,collection):
        v=self.selected(collection)
        if v: ResourceEditor(self,collection,v,self.bundle,lambda value:self.store(collection,value,v['id']))
    def delete_resource(self,collection):
        v=self.selected(collection)
        if not v: return
        proposed=copy.deepcopy(self.bundle)
        # A skill and its exclusively owned skill graph are a single removable resource.
        if collection=='skills' and v['graph_id']:
            graph=next(g for g in proposed['shared_rules'] if g['id']==v['graph_id'])
            if graph['kind']=='skill' and not any(s['id']!=v['id'] and s['graph_id']==graph['id'] for s in proposed['skills']): proposed['shared_rules']=[g for g in proposed['shared_rules'] if g['id']!=graph['id']]
        proposed[collection]=[x for x in proposed[collection] if x['id']!=v['id']]
        try: validate_bundle(proposed)
        except RuleError as exc: return messagebox.showerror('仍被引用','请先修改关联资源，再删除。\n'+str(exc),parent=self)
        if messagebox.askyesno('删除资源','删除 '+v['name']+'？可以通过取消整个编辑窗口放弃本次更改。',parent=self): self.bundle=proposed; self.refresh()
    def show_references(self,collection):
        v=self.selected(collection)
        if v: messagebox.showinfo('引用位置','\n'.join(references(self.bundle,v['id'])) or '当前没有其他资源引用。',parent=self)
    def open_graph(self,collection):
        v=self.selected(collection)
        if not v: return
        proposed=copy.deepcopy(self.bundle)
        if collection=='skills':
            graph_id=v['graph_id']
            if not graph_id:
                graph_id='graph.'+uuid.uuid4().hex[:10]; proposed['shared_rules'].append(new_graph(graph_id,v['name']+' · 规则图','skill'))
                next(s for s in proposed['skills'] if s['id']==v['id'])['graph_id']=graph_id
        else: graph_id=v['id']
        def commit(graph):
            proposed['shared_rules']=[graph if g['id']==graph_id else g for g in proposed['shared_rules']]; validate_bundle(proposed); self.bundle=proposed; self.refresh()
        GraphEditor(self,proposed,graph_id,commit,self.card)
    def apply(self):
        try: validate_bundle(self.bundle); self.on_apply(copy.deepcopy(self.bundle)); self.destroy()
        except RuleError as exc: messagebox.showerror('无法应用',str(exc),parent=self)
    def example(self):
        if any(self.bundle[k] for k in LABELS) and not messagebox.askyesno('载入示例','示例会替换本窗口中的技能与规则资源，原天赋衍生文本保留。继续？',parent=self): return
        self.bundle=sample_bundle(); self.refresh(); self.reset_sim()
    def export_bundle(self):
        try: validate_bundle(self.bundle)
        except RuleError as exc: return messagebox.showerror('无法导出',str(exc),parent=self)
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',filetypes=[('技能资源JSON','*.json')])
        if path:
            try: write_json(path,self.bundle)
            except (OSError,RuleError) as exc: messagebox.showerror('导出失败',str(exc),parent=self)
    def import_bundle(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('技能资源JSON','*.json')])
        if not path: return
        try:
            value=read_json(path); validate_bundle(value)
            if messagebox.askyesno('导入资源','以文件中的资源替换当前编辑窗口的技能库？',parent=self): self.bundle=value; self.refresh(); self.reset_sim()
        except (OSError,ValueError,RecursionError) as exc: messagebox.showerror('导入失败',str(exc),parent=self)
    def batch_ndsl(self):
        win=Modal(self); win.title('批量中文声明'); win.geometry('850x700'); win.transient(self); win.grab_set()
        editor=LongText(win,lambda:None,'NDSL'); editor.pack(fill='both',expand=True,padx=12,pady=12); editor.text.configure(height=22)
        from .examples import DEFINITIONS
        editor.text.insert('1.0',chinese_dump(parse_ndsl(DEFINITIONS)))
        def apply():
            try:
                values=chinese_parse(editor.text.get('1.0','end-1c')); proposed=copy.deepcopy(self.bundle)
                for key,items in values.items():
                    if {x['id'] for x in proposed[key]}&{x['id'] for x in items}: raise RuleError('ID已存在；请到对应资源编辑窗口修改')
                    proposed[key].extend(items)
                validate_bundle(proposed); self.bundle=proposed; self.refresh(); win.destroy()
            except RuleError as exc: messagebox.showerror('声明失败',str(exc),parent=win)
        ttk.Button(win,text='注册这些定义词与模板',command=apply).pack(pady=10)
    def sim_tab(self):
        page=ttk.Frame(self.tabs,padding=12); self.tabs.add(page,text='模拟与日志')
        ttk.Label(page,text='独立模拟：A为自身、B为测试目标。读取人物卡属性快照；任何变化只作用于模拟副本。资源更改后会自动重置模拟。',style='Hint.TLabel',wraplength=1050).pack(anchor='w',pady=8)
        bar=ttk.Frame(page); bar.pack(fill='x'); self.skill_id=tk.StringVar(); self.sim_skill=ttk.Combobox(bar,textvariable=self.skill_id,width=30,state='readonly'); self.sim_skill.pack(side='left',padx=4)
        for text,fn in [('使用一次',lambda:self.simulate('skill')),('连续使用三次',lambda:self.simulate('skill',3)),('重置模拟',self.reset_sim),('编辑模拟实体',self.edit_runtime)]: ttk.Button(bar,text=text,command=fn).pack(side='left',padx=4)
        events=ttk.Frame(page); events.pack(fill='x',pady=10); self.event_type=tk.StringVar(value=chinese_label('status_changed')); self.event_definition=tk.StringVar(); self.sim_target=tk.StringVar(value='B')
        ttk.Label(events,text='事件').pack(side='left'); self.event_box=ttk.Combobox(events,textvariable=self.event_type,values=[chinese_label(e) for e in EVENTS],state='readonly',width=22); self.event_box.pack(side='left',padx=4)
        ttk.Label(events,text='定义词ID').pack(side='left'); ttk.Entry(events,textvariable=self.event_definition,width=24).pack(side='left',padx=4)
        ttk.Label(events,text='目标').pack(side='left'); ttk.Combobox(events,textvariable=self.sim_target,values=['A','B'],state='readonly',width=4).pack(side='left',padx=4)
        ttk.Button(events,text='发送事件',command=lambda:self.simulate('event')).pack(side='left',padx=4)
        ttk.Button(events,text='移除指定状态',command=lambda:self.simulate('remove')).pack(side='left',padx=4)
        self.sim_summary=ttk.Label(page,text='尚未运行模拟',style='Metric.TLabel',wraplength=1050); self.sim_summary.pack(fill='x',pady=(0,10))
        body=ttk.Panedwindow(page,orient='horizontal'); body.pack(fill='both',expand=True)
        state_frame=ttk.Frame(body); log_frame=ttk.Frame(body); body.add(state_frame,weight=1); body.add(log_frame,weight=2)
        self.sim_state=tk.Text(state_frame,width=48,wrap='word',font=('Microsoft YaHei UI',9)); self.sim_log=tk.Text(log_frame,width=60,wrap='word',font=('Microsoft YaHei UI',9))
        for frame,widget in [(state_frame,self.sim_state),(log_frame,self.sim_log)]:
            bar=ttk.Scrollbar(frame,command=widget.yview); widget.configure(yscrollcommand=bar.set); bar.pack(side='right',fill='y'); widget.pack(side='left',fill='both',expand=True)
        LongText.bind_wheel(self.sim_state); LongText.bind_wheel(self.sim_log)
    def reset_sim(self):
        try:
            card=copy.deepcopy(self.card); card['talent_derivations']=copy.deepcopy(self.bundle)
            runtime=Runtime([entity_from_card(card,'A'),entity_from_card(card,'B')]); self.sim_engine=Engine(self.bundle,runtime); self.sim_bundle=copy.deepcopy(self.bundle)
            if self.bundle['skills'] and self.skill_id.get() not in {s['id'] for s in self.bundle['skills']}: self.skill_id.set(self.bundle['skills'][0]['id'])
            self.render_sim()
        except RuleError as exc: self.sim_engine=None; messagebox.showerror('无法模拟',str(exc),parent=self)
    def simulate(self,mode,count=1):
        if self.sim_engine is None or self.sim_bundle!=self.bundle: self.reset_sim()
        if self.sim_engine is None: return
        try:
            for _ in range(count):
                if mode=='skill': self.sim_engine.use_skill(self.skill_id.get(),target=self.sim_target.get())
                elif mode=='remove': self.sim_engine.remove_status(self.sim_target.get(),self.event_definition.get())
                else: self.sim_engine.emit(internal(self.event_type.get()),'A',self.sim_target.get(),{'definition':self.event_definition.get()})
        except RuleError as exc: messagebox.showerror('模拟未完成',str(exc),parent=self)
        self.render_sim()
    def render_sim(self):
        if not self.sim_engine: return
        runtime=self.sim_engine.runtime
        entity=runtime.entities[self.sim_target.get()]; names={d['id']:d['name'] for d in self.bundle['definitions']}
        statuses='、'.join(names.get(id,id)+'×'+str(count) for id,count in entity['statuses'].items()) or '无'
        available='、'.join(s['name'] for s in self.bundle['skills'] if entity['skills'].get(s['id'],False) and s['enabled']) or '无'
        self.sim_summary.configure(text=self.sim_target.get()+' · 状态：'+statuses+'；可用技能：'+available)
        self.sim_state.configure(state='normal'); self.sim_state.delete('1.0','end'); self.sim_state.insert('1.0',chinese_dump(runtime.entities)); self.sim_state.configure(state='disabled')
        self.sim_log.configure(state='normal'); self.sim_log.delete('1.0','end'); self.sim_log.insert('1.0','\n'.join(f"{v['event'] or '-'}  [{v['graph'] or '-'} / {v['node'] or '-'}] {v['message']}" for v in runtime.log)); self.sim_log.see('end'); self.sim_log.configure(state='disabled')
    def edit_runtime(self):
        if self.sim_engine is None: self.reset_sim()
        if not self.sim_engine: return
        win=Modal(self); win.title('仅编辑模拟实体'); win.geometry('850x700'); win.transient(self); win.grab_set()
        text=LongText(win,lambda:None,'运行时副本'); text.pack(fill='both',expand=True,padx=12,pady=12); text.text.configure(height=23); text.text.insert('1.0',chinese_dump(list(self.sim_engine.runtime.entities.values())))
        def apply():
            try:
                entities=chinese_parse(text.text.get('1.0','end-1c')); runtime=Runtime(entities)
                if set(runtime.entities)!={'A','B'}: raise RuleError('本模拟界面保留A、B两个实体ID')
                self.sim_engine=Engine(self.bundle,runtime); self.sim_bundle=copy.deepcopy(self.bundle); self.render_sim(); win.destroy()
            except (ValueError,TypeError,KeyError) as exc: messagebox.showerror('运行时数据无效',str(exc),parent=win)
        ttk.Button(win,text='应用到模拟副本',command=apply).pack(pady=10)
