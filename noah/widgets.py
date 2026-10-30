"""Reusable long-text editor and constrained ID-photo crop dialog."""
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageTk
from .photos import encode_crop


def wheel_steps(event):
    return -1 if getattr(event,'num',0)==4 else 1 if getattr(event,'num',0)==5 else (-1 if event.delta>0 else 1)

class LongText(ttk.Frame):
    def __init__(self,parent,changed,label='文本'):
        super().__init__(parent)
        self.changed=changed; self.label=label
        toolbar=ttk.Frame(self); toolbar.pack(fill='x')
        ttk.Button(toolbar,text='− 收起',command=lambda:self.resize(-2),width=8).pack(side='left')
        ttk.Button(toolbar,text='＋ 扩展',command=lambda:self.resize(2),width=8).pack(side='left',padx=4)
        ttk.Button(toolbar,text='放大编辑',command=self.expand).pack(side='right')
        body=ttk.Frame(self); body.pack(fill='both',expand=True,pady=(4,0))
        self.text=tk.Text(body,height=5,wrap='word',font=('Microsoft YaHei UI',10),relief='solid',bd=1,undo=True,padx=8,pady=6)
        scroll=ttk.Scrollbar(body,orient='vertical',command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set); self.text.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        self.bind_wheel(self.text)
        self.text.bind('<<Modified>>',self.modified)
    def modified(self,event=None):
        if self.text.edit_modified(): self.text.edit_modified(False); self.changed()
    @staticmethod
    def bind_wheel(text):
        def scroll(event): text.yview_scroll(wheel_steps(event),'units'); return 'break'
        for event in ['<MouseWheel>','<Button-4>','<Button-5>']: text.bind(event,scroll)
    def resize(self,delta): self.text.configure(height=max(4,min(17,int(self.text.cget('height'))+delta)))
    def enable_rich(self, define=None, save=None):
        self.define_callback=define; self.save_callback=save
        self.text.configure(exportselection=False)
        self.rich_toolbar(self, self.text, before=self.text.master)

    def rich_toolbar(self, parent, text, before=None):
        from tkinter import colorchooser
        bar=ttk.Frame(parent)
        if before: bar.pack(fill='x',before=before)
        else: bar.pack(fill='x')
        def selection():
            try: return text.index('sel.first'),text.index('sel.last')
            except tk.TclError: return None
        def style(kind,color=None):
            selected=selection()
            if not selected: return
            start,end=selected
            tag='rich_'+kind if not color else 'rich_color_'+color
            if kind=='color':
                for old in text.tag_names():
                    if old.startswith('rich_color_'): text.tag_remove(old,start,end)
                text.tag_configure(tag,foreground=color)
            else:
                text.tag_configure('rich_bold',font=('Microsoft YaHei UI',11,'bold'))
                text.tag_configure('rich_italic',font=('Microsoft YaHei UI',11,'italic'))
            if kind!='color' and tag in text.tag_names(start): text.tag_remove(tag,start,end)
            else: text.tag_add(tag,start,end)
            self.combine_styles(text); self.changed()
        ttk.Button(bar,text='加粗',command=lambda:style('bold'),width=6).pack(side='left')
        ttk.Button(bar,text='斜体',command=lambda:style('italic'),width=6).pack(side='left')
        def colors():
            if not selection(): return
            win=tk.Toplevel(parent); win.title('字体颜色'); win.transient(parent.winfo_toplevel())
            palette=['#000000','#FFFFFF','#808080','#C0C0C0','#FF0000','#800000','#FF8000','#FFD700','#FFFF00','#808000','#008000','#00FF00','#008080','#00FFFF','#0000FF','#000080','#800080','#FF00FF','#FFC0CB','#A52A2A']
            def choose(color):
                if color: style('color',color.upper()); win.destroy()
            for i,color in enumerate(palette):
                tk.Button(win,bg=color,width=5,height=2,command=lambda c=color:choose(c)).grid(row=i//5,column=i%5,padx=3,pady=3)
            ttk.Button(win,text='RGB 调色器',command=lambda:choose(colorchooser.askcolor(parent=win)[1])).grid(row=4,column=0,columnspan=5,sticky='ew')
        ttk.Button(bar,text='字体颜色',command=colors).pack(side='left')
        if getattr(self,'define_callback',None):
            def define():
                selected=selection()
                if not selected: return
                start,end=selected; name=text.get(start,end).strip().strip('「」').strip()
                if not name: return
                if len(name)>200 or '\n' in name:
                    messagebox.showerror('无法定义','请选择不超过200字的单行名称。',parent=parent); return
                # Expanded editors defer registration until the edit is applied.
                if text is self.text: self.define_callback(name)
                else: text.pending_definitions.add(name)
                text.delete(start,end); text.insert(start,'「'+name+'」'); self.changed()
            ttk.Button(bar,text='定义',command=define).pack(side='left')

    @staticmethod
    def combine_styles(text):
        text.tag_configure('rich_combined',font=('Microsoft YaHei UI',11,'bold italic'))
        text.tag_remove('rich_combined','1.0','end')
        bold=text.tag_ranges('rich_bold'); italic=text.tag_ranges('rich_italic')
        for a,b in zip(bold[::2],bold[1::2]):
            for c,d in zip(italic[::2],italic[1::2]):
                start=a if text.compare(a,'>',c) else c; end=b if text.compare(b,'<',d) else d
                if text.compare(start,'<',end): text.tag_add('rich_combined',start,end)
        text.tag_raise('rich_combined'); text.tag_raise('sel')

    @staticmethod
    def formats(text):
        result=[]
        for tag in text.tag_names():
            if tag in ('rich_bold','rich_italic') or tag.startswith('rich_color_'):
                ranges=text.tag_ranges(tag)
                for a,b in zip(ranges[::2],ranges[1::2]): result.append([tag,str(a),str(b)])
        return result

    @staticmethod
    def restore_formats(text, records):
        import re
        for tag in text.tag_names():
            if tag.startswith('rich_'): text.tag_delete(tag)
        for tag,a,b in records:
            if tag in ('rich_bold','rich_italic'):
                text.tag_configure(tag,font=('Microsoft YaHei UI',11,'bold' if tag=='rich_bold' else 'italic'))
            elif re.fullmatch(r'rich_color_#[0-9A-Fa-f]{6}',tag): text.tag_configure(tag,foreground=tag[11:])
            else: continue
            text.tag_add(tag,a,b)
        LongText.combine_styles(text)

    def expand(self):
        win=tk.Toplevel(self); win.title(self.label+' · 放大编辑')
        width=min(920,win.winfo_screenwidth()-80); height=min(680,win.winfo_screenheight()-120)
        win.geometry(f'{width}x{height}+30+30'); win.minsize(500,350); win.transient(self.winfo_toplevel()); win.grab_set()
        buttons=ttk.Frame(win,padding=8); buttons.pack(side='top',fill='x')
        frame=ttk.Frame(win,padding=12)
        editor=tk.Text(frame,wrap='word',undo=True,exportselection=False,font=('Microsoft YaHei UI',11),padx=12,pady=12)
        editor.pending_definitions=set()
        if hasattr(self,'save_callback'): self.rich_toolbar(win,editor)
        frame.pack(fill='both',expand=True)
        bar=ttk.Scrollbar(frame,command=editor.yview); editor.configure(yscrollcommand=bar.set)
        editor.pack(side='left',fill='both',expand=True); bar.pack(side='right',fill='y')
        editor.insert('1.0',self.text.get('1.0','end-1c')); self.restore_formats(editor,self.formats(self.text)); self.bind_wheel(editor)
        def apply(close=True, disk=False):
            value=editor.get('1.0','end-1c')
            if len(value)>30000: return messagebox.showerror('文本过长','每个文本栏最多30000字。',parent=win)
            records=self.formats(editor)
            for name in editor.pending_definitions:
                if '「'+name+'」' in value: self.define_callback(name)
            editor.pending_definitions.clear()
            self.text.delete('1.0','end'); self.text.insert('1.0',value); self.restore_formats(self.text,records); self.changed()
            if disk and getattr(self,'save_callback',None):
                if not self.save_callback(): return
            if close: win.destroy()
        ttk.Button(buttons,text='保存',command=lambda:apply(False,True)).pack(side='left')
        ttk.Button(buttons,text='应用并关闭',command=apply).pack(side='right')
        ttk.Button(buttons,text='取消',command=win.destroy).pack(side='right',padx=8)
        win.bind('<Control-s>',lambda e:(apply(False,True),'break')[1])
        def close():
            if editor.get('1.0','end-1c')!=self.text.get('1.0','end-1c') or self.formats(editor)!=self.formats(self.text):
                choice=messagebox.askyesnocancel('保存编辑','是否应用本次编辑后关闭？',parent=win)
                if choice is None: return
                if choice: apply(); return
            win.destroy()
        win.protocol('WM_DELETE_WINDOW',close); editor.focus_set()

class PhotoCrop(tk.Toplevel):
    """Drag a fixed 5:7 rectangle; slider controls its size; normalized output 240x336."""
    def __init__(self,parent,image,on_apply):
        super().__init__(parent); self.title('证件照裁剪 · 拖动选框调整位置'); self.transient(parent); self.grab_set(); self.resizable(False,False)
        self.source=image; self.on_apply=on_apply
        preview=image.copy(); preview.thumbnail((650,460),Image.Resampling.LANCZOS)
        self.scale=image.width/preview.width; self.pw,self.ph=preview.size; self.center=[self.pw/2,self.ph/2]
        self.preview=ImageTk.PhotoImage(preview,master=self)
        ttk.Label(self,text='拖动裁剪框定位；调整滑块可缩小选区。输出比例5:7，随人物卡内嵌保存。',padding=12).pack()
        self.canvas=tk.Canvas(self,width=self.pw,height=self.ph,highlightthickness=0,bg='#253445'); self.canvas.pack(padx=16)
        self.canvas.create_image(0,0,anchor='nw',image=self.preview)
        self.amount=tk.DoubleVar(value=100)
        ttk.Scale(self,from_=15,to=100,variable=self.amount,command=lambda v:self.draw()).pack(fill='x',padx=18,pady=12)
        self.canvas.bind('<Button-1>',self.drag); self.canvas.bind('<B1-Motion>',self.drag)
        bar=ttk.Frame(self,padding=12); bar.pack(fill='x')
        ttk.Button(bar,text='使用裁剪结果',command=self.apply).pack(side='right'); ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=8)
        self.draw()
    def draw(self):
        height=min(self.ph,self.pw*7/5)*self.amount.get()/100; width=height*5/7
        cx=max(width/2,min(self.pw-width/2,self.center[0])); cy=max(height/2,min(self.ph-height/2,self.center[1])); self.center=[cx,cy]
        self.box=(cx-width/2,cy-height/2,cx+width/2,cy+height/2)
        self.canvas.delete('selection')
        x0,y0,x1,y1=self.box
        for region in [(0,0,self.pw,y0),(0,y1,self.pw,self.ph),(0,y0,x0,y1),(x1,y0,self.pw,y1)]: self.canvas.create_rectangle(*region,fill='#162330',stipple='gray50',outline='',tags='selection')
        self.canvas.create_rectangle(*self.box,outline='#10c8b5',width=3,tags='selection')
    def drag(self,event): self.center=[event.x,event.y]; self.draw()
    def apply(self):
        # Map the rounded preview dimensions separately to avoid edge rounding errors.
        sx=self.source.width/self.pw; sy=self.source.height/self.ph
        box=tuple(round(v*(sx if i%2==0 else sy)) for i,v in enumerate(self.box))
        try: result=encode_crop(self.source,box); self.on_apply(result); self.destroy()
        except ValueError as exc: messagebox.showerror('裁剪失败',str(exc),parent=self)

