import os,tempfile,unittest
from pathlib import Path
from tkinter import ttk
from noah.runtime import configure_tk_paths
from noah.ui import App
from noah.widgets import LongText
from noah.storage import save,load
from noah.domain import new_card,validate,CardError

def buttons(w):
    for child in w.winfo_children():
        if isinstance(child,ttk.Button): yield child
        yield from buttons(child)

@unittest.skipUnless(os.environ.get('NOAH_UI_TESTS')=='1','GUI')
class RichTests(unittest.TestCase):
    def setUp(self):
        configure_tk_paths(); self.app=App(); self.app.update()
    def tearDown(self): self.app.destroy()
    def test_roundtrip_and_definition(self):
        t=self.app.fields[('crystal','固有天赋')][1]; holder=t.master.master
        t.insert('1.0','夜游烬'); t.tag_add('sel','1.0','1.3')
        next(b for b in buttons(holder) if b['text']=='定义').invoke()
        self.assertEqual(t.get('1.0','end-1c'),'「夜游烬」')
        self.app.define_word('夜游烬')
        self.assertEqual(len(self.app.card['talent_derivations']['definitions']),1)
        records=[['rich_bold','1.0','1.5'],['rich_italic','1.1','1.3'],['rich_color_#FF0000','1.0','1.5']]
        LongText.restore_formats(t,records)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'card.json'; save(path,self.app.collect()); self.app.card=load(path); self.app.populate()
            self.assertEqual(sorted(LongText.formats(t)),sorted(records))
        self.assertTrue(t.tag_ranges('rich_combined'))
    def test_expanded_cancel_and_apply(self):
        t=self.app.fields[('crystal','天赋衍生')][1]; holder=t.master.master
        holder.expand(); self.app.update()
        win=next(w for w in holder.winfo_children() if w.winfo_class()=='Toplevel')
        def texts(w):
            for c in w.winfo_children():
                if c.winfo_class()=='Text': yield c
                yield from texts(c)
        editor=next(texts(win)); editor.insert('1.0','新词'); editor.tag_add('sel','1.0','1.2')
        next(b for b in buttons(win) if b['text']=='定义').invoke()
        self.assertFalse(self.app.card['talent_derivations']['definitions'])
        self.assertTrue(next(b for b in buttons(win) if b['text']=='保存').winfo_ismapped())
        next(b for b in buttons(win) if b['text']=='应用并关闭').invoke()
        self.assertEqual(t.get('1.0','end-1c'),'「新词」')
        self.assertEqual(self.app.card['talent_derivations']['definitions'][0]['name'],'新词')

class ValidationTests(unittest.TestCase):
    def test_invalid_color(self):
        c=new_card(); c['extensions']['rich_text']={'x':[['rich_color_bad','1.0','1.1']]}
        with self.assertRaises(CardError): validate(c)
