"""Run from VS Code: python main.py"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def main():
    directory=Path(__file__).resolve().parent/'.local'
    try:
        directory.mkdir(exist_ok=True)
        handler=RotatingFileHandler(directory/'app.log',maxBytes=256000,backupCount=2,encoding='utf-8')
        logging.basicConfig(level=logging.ERROR,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    except OSError:
        logging.basicConfig(level=logging.ERROR)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    from noah.runtime import configure_tk_paths
    try:
        configure_tk_paths()
    except ImportError:
        raise SystemExit('当前 Python 未安装 Tkinter。请在 Python 安装器中启用 Tcl/Tk 与 IDLE 组件。')
    from noah.ui import App
    import sys
    import tkinter
    try:
        app = App()
    except tkinter.TclError as exc:
        print('窗口初始化失败：当前 Python 的 Tcl/Tk 路径无效或组件不完整。', file=sys.stderr)
        print('请使用 Python 安装器修复 Tcl/Tk 组件；若手动设置过 TCL_LIBRARY/TK_LIBRARY，请检查其路径。', file=sys.stderr)
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    if '--check-runtime' in sys.argv:
        app.update()
        app.destroy()
        print('运行环境检查通过：人物卡窗口已成功创建。')
    else:
        app.mainloop()

if __name__=='__main__': main()


