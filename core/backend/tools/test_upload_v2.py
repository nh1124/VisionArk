import httpx
import os
import time

# Configuration
BASE_URL = "http://127.0.0.1:8000"
USER_ID = "00000000-0000-0000-0000-000000000001" # Atmos Dev User
PROJECT_NAME = "hub" # Default project
FILE_NAME = "test_upload_v2.txt"
FILE_CONTENT = "This is a test file for the final verification of the project_dir upload flow."

def test_file_upload():
    # 1. Prepare file
    with open(FILE_NAME, "w") as f:
        f.write(FILE_CONTENT)
    
    print(f"🚀 Testing file upload to {PROJECT_NAME}...")
    
    try:
        # 2. Send multi-part request
        with open(FILE_NAME, "rb") as f:
            files = [("files", (FILE_NAME, f, "text/plain"))]
            data = {
                "message": "Analyze this file please.",
                "stream": "false"
            }
            # Add dev user header if required by resolve_identity
            headers = {"X-User-ID": USER_ID} 
            
            response = httpx.post(
                f"{BASE_URL}/api/agents/project/{PROJECT_NAME}/chat",
                data=data,
                files=files,
                headers=headers,
                timeout=30.0
            )
        
        if response.status_code != 200:
            print(f"❌ Upload failed: {response.status_code}")
            print(response.text)
            return

        result = response.json()
        task_id = result.get("task_id")
        print(f"✅ Task enqueued: {task_id}")

        # 3. Polling
        print(f"⌛ Polling for task {task_id}...")
        for _ in range(30):
            status_resp = httpx.get(f"{BASE_URL}/api/agents/tasks/{task_id}", headers=headers)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                status = status_data.get("status")
                print(f"   Current status: {status}")
                if status == "completed":
                    print("🎉 Task completed successfully!")
                    print("--- Result ---")
                    print(status_data.get("result"))
                    return
                elif status == "failed":
                    print(f"❌ Task failed: {status_data.get('result')}")
                    return
            time.sleep(2)
        else:
            print("🕒 Polling timed out.")

    finally:
        if os.path.exists(FILE_NAME):
            os.remove(FILE_NAME)

if __name__ == "__main__":
    test_file_upload()
