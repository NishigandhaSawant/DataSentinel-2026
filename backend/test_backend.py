import requests
import time
import os

print("Starting integration test for async upload and PDF generation...")
base_url = "http://localhost:8000"

# 1. Load a sample asynchronously
print("1. Triggering async sample load (fraud_transactions.csv)")
res = requests.post(f"{base_url}/api/load-sample/fraud_transactions.csv")
res.raise_for_status()
data = res.json()
session_id = data.get("session_id")
print(f"Session ID: {session_id}")

# 2. Poll for completion
while True:
    time.sleep(1)
    status_res = requests.get(f"{base_url}/api/status/{session_id}")
    status_data = status_res.json()
    current_status = status_data.get("status")
    if current_status == "completed":
        print("Async ML processing completed successfully!")
        break
    elif current_status == "error":
        print(f"Async ML processing failed: {status_data.get('error')}")
        exit(1)

print("2. Cleaning dataset...")
clean_res = requests.post(f"{base_url}/api/clean/{session_id}?action=quarantine")
clean_res.raise_for_status()

# 3. Test PDF download
print("3. Testing PDF download...")
pdf_res = requests.get(f"{base_url}/api/report/download/{session_id}")
if pdf_res.status_code == 200:
    print(f"PDF download successful! Content-Type: {pdf_res.headers.get('Content-Type')}")
    print(f"File size: {len(pdf_res.content)} bytes")
    # Save it to verify
    with open("test_report.pdf", "wb") as f:
        f.write(pdf_res.content)
    print("Saved as test_report.pdf")
else:
    print(f"PDF download failed with status {pdf_res.status_code}: {pdf_res.text}")
    exit(1)

print("Integration test passed.")
