import requests
import json
import time

# Replace with your actual Worker URL
WORKER_URL = "https://dopamine.hacolby.workers.dev"

def run_local_diagnostics():
    print("Initiating local hardware diagnostics...")
    try:
        # Hit the local Flask app to run the physical print test
        local_res = requests.post("http://127.0.0.1:8080/test", timeout=10)
        report = local_res.json()
        print(f"Local test complete. Status: {report['status']}")
    except Exception as e:
        print(f"Failed to reach local print server: {e}")
        report = {
            "status": "offline",
            "printer": "unreachable",
            "error": str(e),
            "timestamp": time.time()
        }

    print("Pushing diagnostic report to Cloudflare Worker...")
    try:
        # Push the report to the Worker's logging/telemetry endpoint
        cf_res = requests.post(
            f"{WORKER_URL}/api/printer/telemetry", 
            json=report,
            timeout=5
        )
        if cf_res.status_code == 200:
            print("✅ Report successfully logged to Cloudflare D1.")
        else:
            print(f"❌ Failed to log to Cloudflare. Status: {cf_res.status_code}")
    except Exception as e:
        print(f"❌ Network error reaching Cloudflare: {e}")

if __name__ == "__main__":
    run_local_diagnostics()
