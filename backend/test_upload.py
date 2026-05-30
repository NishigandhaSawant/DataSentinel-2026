import requests
import time
import sys
import json

API_BASE = "http://localhost:8000"
FILE_PATH = "data/creditcard.csv"

def run_test():
    print(f"Starting test for {FILE_PATH}...")
    start_time = time.time()
    
    # 1. Upload file
    print("Uploading file...")
    upload_start = time.time()
    with open(FILE_PATH, 'rb') as f:
        files = {'file': f}
        try:
            response = requests.post(f"{API_BASE}/api/upload/", files=files)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Upload failed: {e}")
            sys.exit(1)
            
    upload_end = time.time()
    data = response.json()
    session_id = data.get("session_id")
    print(f"Upload completed in {upload_end - upload_start:.2f} seconds. Session ID: {session_id}")
    
    if not session_id:
        print("No session ID returned.")
        sys.exit(1)
        
    # 2. Poll for completion
    print("Polling for completion...")
    status = "started"
    while status != "completed" and status != "failed":
        try:
            res = requests.get(f"{API_BASE}/api/status/{session_id}")
            res.raise_for_status()
            status_data = res.json()
            status = status_data.get("status")
            progress = status_data.get("progress", 0)
            print(f"Status: {status} | Progress: {progress}%")
            if status in ["completed", "failed"]:
                break
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            print(f"Status poll failed: {e}")
            break
            
    total_end = time.time()
    print(f"\n--- TEST COMPLETE ---")
    print(f"Final Status: {status}")
    print(f"Total time (Upload + Processing): {total_end - start_time:.2f} seconds")

if __name__ == "__main__":
    run_test()
