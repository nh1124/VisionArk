import asyncio
from unittest.mock import MagicMock, patch
from google.genai import types

# Add project root to sys.path
import sys
import os
sys.path.append(os.path.join(os.getcwd(), "core", "backend"))

from llm.gemini_provider import GeminiProvider
from tools.agent_tools import ToolResult

async def test_tool_uri_injection():
    print("Starting verification test...")
    
    # 1. Setup mock provider
    provider = GeminiProvider(api_key="mock_key", model_name="gemini-2.0-flash-exp")
    provider.client = MagicMock()
    
    # 2. Mock Tool Function returning a Gemini URI
    mock_tool_result = ToolResult(
        success=True,
        message="Found file",
        data={
            "gemini_file_uri": "https://generativelanguage.googleapis.com/v1beta/files/mock-pdf-123",
            "mime_type": "application/pdf"
        }
    )
    
    mock_tool_func = MagicMock(return_value=mock_tool_result)
    
    # 3. Mock Gemini API response to trigger tool use
    mock_fc = MagicMock()
    mock_fc.name = "read_reference"
    mock_fc.args = {"file_path": "test.pdf"}
    
    mock_part_fc = MagicMock()
    mock_part_fc.function_call = mock_fc
    mock_part_fc.text = None
    mock_part_fc.executable_code = None
    mock_part_fc.code_execution_result = None
    
    mock_content = MagicMock()
    mock_content.parts = [mock_part_fc]
    
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    
    mock_response_1 = MagicMock()
    mock_response_1.candidates = [mock_candidate]
    
    # Final response to end the loop
    mock_part_text = MagicMock()
    mock_part_text.text = "I see the PDF content. It's about scenario planning."
    mock_part_text.function_call = None
    
    mock_content_2 = MagicMock()
    mock_content_2.parts = [mock_part_text]
    
    mock_candidate_2 = MagicMock()
    mock_candidate_2.content = mock_content_2
    
    mock_response_2 = MagicMock()
    mock_response_2.candidates = [mock_candidate_2]
    mock_response_2.usage_metadata = None
    
    provider.client.models.generate_content.side_effect = [mock_response_1, mock_response_2]
    
    # 4. Execute completion
    print("Calling provider.complete...")
    await provider.complete(
        messages=[{"role": "user", "content": "Read test.pdf"}],
        tool_functions={"read_reference": mock_tool_func},
        tool_context={"user_id": "test_user"}
    )
    
    # 5. Verify history in the second call
    call_args_list = provider.client.models.generate_content.call_args_list
    if len(call_args_list) < 2:
        print("FAIL: Second call didn't happen")
        return

    hist = call_args_list[1].kwargs['contents']
    print(f"History length: {len(hist)}")
    
    # Check tool response entry
    tool_entry = hist[-1]
    print(f"Last entry role: {tool_entry.role}")
    
    has_file_part = False
    for part in tool_entry.parts:
        if hasattr(part, 'file_data') and part.file_data:
            print(f"SUCCESS: Found file_data part: {part.file_data.file_uri}")
            if part.file_data.file_uri == "https://generativelanguage.googleapis.com/v1beta/files/mock-pdf-123":
                has_file_part = True
        elif hasattr(part, 'function_response') and part.function_response:
            print(f"Found function_response: {part.function_response.name}")

    if has_file_part:
        print("VERIFICATION SUCCESSFUL!")
    else:
        print("FAIL: File part not found in tool response history")

if __name__ == "__main__":
    asyncio.run(test_tool_uri_injection())
