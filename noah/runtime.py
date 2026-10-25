"""Locate Tcl/Tk beside the active standard library, including split installations."""
import os
from pathlib import Path


def configure_tk_paths():
    import tkinter
    import _tkinter
    # Use the library belonging to this interpreter, never an unrelated Python.
    library_root = Path(tkinter.__file__).resolve().parents[2]
    for variable, version, marker in [
        ('TCL_LIBRARY', _tkinter.TCL_VERSION, 'init.tcl'),
        ('TK_LIBRARY', _tkinter.TK_VERSION, 'tk.tcl'),
    ]:
        if variable in os.environ:
            continue
        directory = library_root / 'tcl' / (('tcl' if variable == 'TCL_LIBRARY' else 'tk') + version)
        if (directory / marker).is_file():
            os.environ[variable] = str(directory)
