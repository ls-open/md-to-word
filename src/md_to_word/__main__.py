"""md_to_word.__main__ — 支持 python -m md_to_word 直接执行。"""

import sys
from md_to_word.cli import main

if __name__ == "__main__":
    sys.exit(main())
