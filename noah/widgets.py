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
    def expand(self):
        win=tk.Toplevel(self); win.title(self.label+' · 放大编辑'); win.geometry('920x680'); win.minsize(600,400); win.transient(self.winfo_toplevel()); win.grab_set()
        frame=ttk.Frame(win,padding=14); frame.pack(fill='both',expand=True)
        editor=tk.Text(frame,wrap='word',undo=True,font=('Microsoft YaHei UI',12),padx=12,pady=12)
        bar=ttk.Scrollbar(frame,command=editor.yview); editor.configure(yscrollcommand=bar.set)
        editor.pack(side='left',fill='both',expand=True); bar.pack(side='right',fill='y'); editor.insert('1.0',self.text.get('1.0','end-1c')); self.bind_wheel(editor)
        buttons=ttk.Frame(win,padding=12); buttons.pack(fill='x')
        def apply():
            value=editor.get('1.0','end-1c')
            if len(value)>30000: return messagebox.showerror('文本过长','每个文本栏最多30000字。',parent=win)
            self.text.delete('1.0','end'); self.text.insert('1.0',value); self.changed(); win.destroy()
        ttk.Button(buttons,text='应用并关闭',command=apply).pack(side='right')
        ttk.Button(buttons,text='取消',command=win.destroy).pack(side='right',padx=8)
        editor.focus_set()

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

