"""Optional real-window interaction checks: set NOAH_UI_TESTS=1 to run."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
from noah.runtime import configure_tk_paths
from noah.ui import App
from noah.widgets import LongText,PhotoCrop
from noah.domain import SLOTS,ELEMENTS_PRIMARY,ELEMENTS_SECONDARY
from noah.storage import load
from PIL import Image

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

@unittest.skipUnless(os.environ.get('NOAH_UI_TESTS')=='1','set NOAH_UI_TESTS=1 for real-window tests')
class UIRevisionTests(unittest.TestCase):
    def setUp(self):
        configure_tk_paths(); self.app=App(); self.app.update()
        self.errors=patch('noah.ui.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')); self.errors.start()
    def tearDown(self):
        self.errors.stop()
        if self.app.pending: self.app.after_cancel(self.app.pending)
        self.app.destroy()
    def test_removed_sections_and_dropdowns(self):
        self.assertFalse(hasattr(self.app,'skill_tree')); self.assertNotIn(('crystal','开发描述'),self.app.fields)
        self.assertEqual(set(self.app.equipment_labels),set(SLOTS))
        for name,values in [('属性一',ELEMENTS_PRIMARY),('属性二',ELEMENTS_SECONDARY)]:
            field=self.app.fields[('crystal',name)][1]; self.assertIsInstance(field,ttk.Combobox); self.assertEqual(list(field['values']),values)
        for k in ['活跃度','烈性','适配度']:
            self.app.fields[('crystal',k+'符号')][0].set('-'); self.app.fields[('crystal',k)][0].set('20')
        self.app.refresh(); self.assertEqual(self.app.card['crystal']['适配度符号'],'-'); self.assertEqual(self.app.card['crystal']['适配度'],20)
        self.assertGreaterEqual(self.app.fields[('form','enabled')][1].winfo_reqheight(),40)
    def test_long_text_scroll_and_expansion(self):
        field=self.app.fields[('crystal','固有天赋')][1]; holder=field.master.master; self.assertIsInstance(holder,LongText)
        field.insert('1.0','\n'.join('内容'+str(n) for n in range(200))); self.app.update(); field.yview_moveto(0)
        field.event_generate('<MouseWheel>',delta=-120); self.app.update(); self.assertGreater(field.yview()[0],0)
        old=int(field.cget('height')); holder.resize(2); self.assertEqual(int(field.cget('height')),old+2)
        holder.expand(); self.app.update(); win=next(w for w in descendants(self.app) if isinstance(w,tk.Toplevel))
        editor=next(w for w in descendants(win) if isinstance(w,tk.Text)); editor.delete('1.0','end'); editor.insert('1.0','放大编辑后的内容')
        next(w for w in descendants(win) if isinstance(w,ttk.Button) and w.cget('text')=='应用并关闭').invoke(); self.app.refresh()
        self.assertEqual(self.app.card['crystal']['固有天赋'],'放大编辑后的内容')
    def test_all_background_fields_use_long_text(self):
        for path,(_,field,_) in self.app.fields.items():
            if path[0] in ('background','academic'): self.assertIsInstance(field.master.master,LongText)
    def test_photo_upload_crop_save_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.jpg'; Image.new('RGB',(500,700),'blue').save(path)
            with patch('noah.ui.filedialog.askopenfilename',return_value=str(path)): self.app.upload_photo()
            self.app.update(); crop=next(w for w in self.app.winfo_children() if isinstance(w,PhotoCrop))
            crop.amount.set(60); crop.draw(); crop.drag(SimpleNamespace(x=160,y=200)); crop.apply(); self.app.refresh()
            self.assertTrue(self.app.card['portrait']['data']); self.assertIsNotNone(self.app._photo_image)
            output=Path(directory)/'人物.json'
            with patch('noah.ui.filedialog.asksaveasfilename',return_value=str(output)): self.assertTrue(self.app.save(True))
            self.assertTrue(output.read_text(encoding='utf-8').lstrip().startswith('{'))
            self.assertEqual(load(output),self.app.card)
            with patch('noah.ui.filedialog.askopenfilename',return_value=str(output)): self.app.open()
            self.assertTrue(self.app.card['portrait']['data']); self.app.remove_photo(); self.assertEqual(self.app.card['portrait']['data'],'')
    def test_attribute_tables_have_fixed_cells_and_readable_rows(self):
        self.assertEqual(list(self.app.summary_table['columns']),['力量','敏捷','耐受','魅力','智力','感知','意志','幸运'])
        row=self.app.summary_table.get_children()[0]
        self.assertEqual(len(self.app.summary_table.item(row,'values')),8)
        self.assertGreaterEqual(self.app.row_height,36)
        self.assertEqual(len(self.app.attr_tree.get_children()),7)

    def test_equipment_component_dialog(self):
        for slot in ['赋能笔','中枢核心']:
            self.app.edit_item(container='装备',slot=slot); self.app.update()
            win=next(w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel))
            entry=next(w for w in descendants(win) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox)); entry.insert(0,slot)
            next(w for w in descendants(win) if isinstance(w,ttk.Button) and w.cget('text')=='保存物品').invoke(); self.app.refresh()
        self.assertEqual(len(self.app.card['inventory']['items']),2)
        self.assertEqual(len(self.app.item_tree.get_children()),0)
        for item in self.app.card['inventory']['items']:
            for key in ['x','y','w','h']: self.assertNotIn(key,item)
