#!/usr/bin/env python3
import subprocess
import time
import json
import http.client
import sys
import os

def log(msg):
    print(f"[*] {msg}", flush=True)

def run_cmd(cmd, cwd=None):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        return result.stdout
    except Exception as e:
        print(f"Exception: {e}")
        return None

def check_api(path):
    try:
        conn = http.client.HTTPConnection("localhost", 8000)
        conn.request("GET", path)
        res = conn.getresponse()
        if res.status == 200:
            return json.loads(res.read().decode())
    except:
        pass
    return None

def main():
    log("Starting S.S.T Automated Verification with Visual Analysis...")

    # Phase 1: Deploy UI
    log("Deploying UI container...")
    run_cmd("docker compose up -d")
    time.sleep(3) 

    # Phase 2: Health Check
    log("Checking API health...")
    stats = check_api("/api/stats")
    if stats is None:
        log("FAILED: API is not responding.")
        sys.exit(1)
    log(f"API is UP. Current Stats: {stats}")

    # Phase 3: Visual Verification (Playwright)
    log("Running Playwright Visual Capture...")
    # Get skill script path
    script_path = os.path.join(os.path.dirname(__file__), "capture_ui.cjs")
    capture_result = run_cmd(f"node {script_path}")
    if capture_result:
        print(capture_result)
        log("SUCCESS: UI Screenshots captured in ui_verification/")
    else:
        log("WARNING: Playwright capture failed.")

    # Phase 4: Data Integrity
    log("Verifying final data integrity...")
    albums = check_api("/api/albums?status=archive")
    if albums and len(albums) > 0:
        latest = albums[0]
        log(f"SUCCESS: Album '{latest['name']}' found in Archive.")
        if len(latest.get('tracks', [])) > 0:
            log("SUCCESS: Metadata Inspector has track data.")
        else:
            log("WARNING: Metadata Inspector data is EMPTY.")
    else:
        log("INFO: No albums in Archive. (Expected if just started)")

    log("S.S.T Verification Finished Successfully.")

if __name__ == "__main__":
    main()
