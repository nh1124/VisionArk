import sys
import os
from pathlib import Path

# Add backend to sys.path
backend_path = Path("c:/Users/nh112/programming/project/VisionArk/core/backend")
sys.path.append(str(backend_path))

from tools.library.markdown import GetCurrentStatusTool
from tools.library.condition import GetCurrentConditionTool

def test_declarations():
    print("Testing GetCurrentStatusTool declaration:")
    try:
        decl = GetCurrentStatusTool.declaration()
        print(f"✅ Success: {decl}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    print("\nTesting GetCurrentConditionTool declaration:")
    try:
        decl = GetCurrentConditionTool.declaration()
        print(f"✅ Success: {decl}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_declarations()
