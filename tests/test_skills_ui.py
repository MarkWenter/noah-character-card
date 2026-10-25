import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
from noah.runtime import configure_tk_paths
from noah.ui import App
from noah.storage import load
from noah.skills.ui import TalentManager,ResourceEditor
from noah.skills.graph_ui import GraphEditor
from noah.skills.examples import sample_bundle
from noah.skills.model import new_skill

@unittest.skipUnless(os.environ.get('NOAH_UI_TESTS')=='1','set NOAH_UI_TESTS=1 for real-window tests')
class TalentUITests(unittest.TestCase):
    def setUp(self):
        configure_tk_paths();self.app=App();self.app.update()
        self.errors=patch('tkinter.messagebox.showerror',side_effect=AssertionError('Unexpected UI validation error'));self.errors.start()
    def tearDown(self):
        self.errors.stop();self.app.destroy()
    def manager(self):
        self.app.edit_talents();self.app.update()
        return next(w for w in self.app.winfo_children() if isinstance(w,TalentManager))
    def test_cancel_does_not_change_main_card(self):
        before=copy.deepcopy(self.app.card);manager=self.manager();manager.example();manager.destroy();self.assertEqual(self.app.card,before)
    def test_sample_simulate_apply_autosave_reopen(self):
        manager=self.manager();manager.example();manager.simulate('skill',3)
        self.assertEqual(manager.sim_engine.runtime.entities['B']['statuses'],{'status.fear':1})
        self.assertTrue(manager.sim_engine.runtime.entities['B']['skills']['skill.fear_power'])
        manager.apply();self.app.refresh();self.assertTrue(self.app.dirty);self.assertEqual(len(self.app.talent_tree.get_children()),2)
        with tempfile.TemporaryDirectory() as directory:
            self.app.recovery=Path(directory)/'recovery.json';self.app.autosave();restored=load(self.app.recovery)
            self.assertEqual(restored['talent_derivations'],sample_bundle())
    def test_definition_form_and_cancel(self):
        manager=self.manager();manager.create('definitions');self.app.update()
        editor=next(w for w in manager.winfo_children() if isinstance(w,ResourceEditor));editor.variables['id'].set('status.test');editor.variables['name'].set('测试状态');editor.save()
        self.assertEqual(manager.bundle['definitions'][0]['id'],'status.test')
        manager.edit('definitions') # no selection, no dialog
        manager.views['definitions']['tree'].selection_set('status.test');manager.edit('definitions');self.app.update();editor=next(w for w in manager.winfo_children() if isinstance(w,ResourceEditor));editor.variables['name'].set('取消的修改');editor.destroy()
        self.assertEqual(manager.bundle['definitions'][0]['name'],'测试状态')
    def test_blank_skill_graph_cancel_does_not_create_binding(self):
        manager=self.manager();manager.bundle['skills']=[new_skill('skill.text','文本技能')];manager.refresh();manager.views['skills']['tree'].selection_set('skill.text');manager.open_graph('skills');self.app.update()
        editor=next(w for w in manager.winfo_children() if isinstance(w,GraphEditor));editor.cancel()
        self.assertEqual(manager.bundle['skills'][0]['graph_id'],'');self.assertFalse(manager.bundle['shared_rules'])
    def test_canvas_connect_params_and_test_current_graph(self):
        manager=self.manager();manager.example();manager.views['skills']['tree'].selection_set('skill.pressure');manager.open_graph('skills');self.app.update()
        editor=next(w for w in manager.winfo_children() if isinstance(w,GraphEditor));editor.doc.disconnect(0);editor.draw();self.app.update()
        start=editor.port_positions[('use','output','out')];end=editor.port_positions[('apply','input','in')]
        editor.canvas.event_generate('<Button-1>',x=int(start[0]),y=int(start[1]));editor.canvas.event_generate('<ButtonRelease-1>',x=int(start[0]),y=int(start[1]));self.app.update()
        editor.canvas.event_generate('<Button-1>',x=int(end[0]),y=int(end[1]));editor.canvas.event_generate('<ButtonRelease-1>',x=int(end[0]),y=int(end[1]));self.app.update();self.assertEqual(len(editor.doc.graph['edges']),1)
        editor.properties_for('apply');editor.form_vars['value'].set('1');self.assertTrue(editor.apply_params())
        for _ in range(3):editor.test_current()
        self.assertEqual(editor.test_engine.runtime.entities['B']['statuses'],{'status.fear':1})
        editor.copy_nodes();editor.undo();editor.redo();editor.save();self.assertEqual(len(manager.bundle['shared_rules'][0]['edges']),1)
    def test_resource_json_export_import(self):
        manager=self.manager();manager.example()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'resources.json'
            with patch('tkinter.filedialog.asksaveasfilename',return_value=str(path)):manager.export_bundle()
            original=copy.deepcopy(manager.bundle);manager.bundle['skills'][0]['name']='temporary'
            with patch('tkinter.filedialog.askopenfilename',return_value=str(path)),patch('tkinter.messagebox.askyesno',return_value=True):manager.import_bundle()
            self.assertEqual(manager.bundle,original)
