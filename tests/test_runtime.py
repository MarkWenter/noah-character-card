import os
from pathlib import Path
import tempfile
import tkinter
import _tkinter
import unittest
from unittest.mock import patch
from noah.runtime import configure_tk_paths

class RuntimeTests(unittest.TestCase):
    def test_split_library_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for prefix,version,marker in [('tcl',_tkinter.TCL_VERSION,'init.tcl'),('tk',_tkinter.TK_VERSION,'tk.tcl')]:
                directory=root/'tcl'/(prefix+version); directory.mkdir(parents=True); (directory/marker).touch()
            with patch.object(tkinter,'__file__',str(root/'Lib'/'tkinter'/'__init__.py')),patch.dict(os.environ,{},clear=True):
                configure_tk_paths()
                self.assertEqual(os.environ['TCL_LIBRARY'],str(root/'tcl'/('tcl'+_tkinter.TCL_VERSION)))
                self.assertEqual(os.environ['TK_LIBRARY'],str(root/'tcl'/('tk'+_tkinter.TK_VERSION)))
    def test_explicit_environment_is_preserved(self):
        with patch.dict(os.environ,{'TCL_LIBRARY':'explicit-tcl','TK_LIBRARY':'explicit-tk'},clear=True):
            configure_tk_paths()
            self.assertEqual(os.environ['TCL_LIBRARY'],'explicit-tcl')
            self.assertEqual(os.environ['TK_LIBRARY'],'explicit-tk')
    def test_missing_resources_do_not_invent_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(tkinter,'__file__',str(Path(folder)/'Lib'/'tkinter'/'__init__.py')),patch.dict(os.environ,{},clear=True):
                configure_tk_paths()
                self.assertNotIn('TCL_LIBRARY',os.environ); self.assertNotIn('TK_LIBRARY',os.environ)
