import subprocess
import json
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("production-test")

# Get absolute path of the current directory at the start
CWD = Path(__file__).parent.absolute()

def run_command_with_output(cmd):
    """Runs a command and streams output to stdout."""
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    full_output = []
    for line in process.stdout:
        print(line, end="", flush=True)
        full_output.append(line)
    process.wait()
    return process.returncode, "".join(full_output)

def parse_scout_output(stdout):
    """Extracts Scout result data from the full output stream."""
    scout_results = []
    worker_inputs = []
    lines = stdout.splitlines()
    
    capturing_scout = False
    capturing_worker = False
    current_json = ""
    
    for line in lines:
        if "--- SCOUT RESULT ---" in line:
            capturing_scout = True
            current_json = ""
            continue
        if "--- WORKER INPUT ---" in line:
            if capturing_scout:
                try:
                    scout_results.append(json.loads(current_json))
                except: pass
                capturing_scout = False
            capturing_worker = True
            current_json = ""
            continue
        if "--------------------" in line:
            if capturing_worker:
                try:
                    worker_inputs.append(json.loads(current_json))
                except: pass
                capturing_worker = False
            continue
        
        if capturing_scout or capturing_worker:
            current_json += line

    final_data = []
    for sr, wi in zip(scout_results, worker_inputs):
        sr["files"] = wi["files"]
        final_data.append(sr)
        
    return final_data

def run_test():
    # Step 1: Scout
    logger.info(">>> Step 1: Running Scout (Limit 3)...")
    cmd_scout = [
        "docker-compose", "run", "--rm", 
        "-e", "PYTHONPATH=/app/src", 
        "scout", "uv", "run", "-m", "scout.main", "--limit", "3"
    ]
    rc, stdout = run_command_with_output(cmd_scout)
    if rc != 0:
        logger.error("Scout failed.")
        return

    scout_data = parse_scout_output(stdout)
    if not scout_data:
        logger.error("Could not parse Scout output.")
        return

    # Step 2: Prefect Flow
    logger.info(f">>> Step 2: Triggering Prefect Flow for {len(scout_data)} albums...")
    input_path = CWD / "scout_test_output.json"
    with open(input_path, "w") as f:
        json.dump(scout_data, f)

    cmd_core = [
        "docker-compose", "run", "--rm",
        "-e", "PYTHONPATH=/app/src",
        "-v", f"{input_path}:/app/input.json:ro",
        "core", "uv", "run", "python", "-c",
        "import json; from core.main import sst_main_flow; data=json.load(open('/app/input.json')); sst_main_flow(data)"
    ]
    run_command_with_output(cmd_core)
    
    if input_path.exists():
        input_path.unlink()

if __name__ == "__main__":
    run_test()
