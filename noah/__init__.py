import sys
from pathlib import Path
# Bundled Pillow is for CPython 3.12 on Windows; other environments use requirements.txt.
_local = Path(__file__).resolve().parent.parent / '.deps'
if sys.platform == 'win32' and sys.version_info[:2] == (3, 12) and _local.is_dir():
    sys.path.append(str(_local))
