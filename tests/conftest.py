import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (pytest를 어디서 실행해도 동작)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
