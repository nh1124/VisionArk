from pydantic import BaseModel
import sys

class NoArgs(BaseModel):
    pass

def test_pydantic_schema():
    print("Testing BaseModel.model_json_schema() - This SHOULD FAIL in Pydantic v2:")
    try:
        schema = BaseModel.model_json_schema()
        print(f"✅ Success (unexpected in v2): {schema}")
    except Exception as e:
        print(f"❌ Expected Failure: {e}")

    print("\nTesting NoArgs.model_json_schema() - This SHOULD SUCCEED:")
    try:
        schema = NoArgs.model_json_schema()
        print(f"✅ Success: {schema}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_pydantic_schema()
