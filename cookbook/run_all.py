#!/usr/bin/env python3
import subprocess
import datetime
import os
import sys

# Recipe metadata: id, display name, command, directory for log, log filename base
RECIPES = [
    {"id": "01", "name": "Hello SPL", "cmd": "moma run ./01_single_node_hello/hello.spl", "dir": "01_single_node_hello", "log": "hello"},
    {"id": "02", "name": "Multi-CTE Parallel", "cmd": "moma run ./02_multi_cte_parallel/multi_cte.spl", "dir": "02_multi_cte_parallel", "log": "multi_cte"},
    {"id": "03", "name": "Batch Translate", "cmd": "python ./03_batch_translate/translate.py 'Hello Momahub'", "dir": "03_batch_translate", "log": "translate"},
    {"id": "04", "name": "Benchmark Models", "cmd": "python ./04_benchmark_models/benchmark.py", "dir": "04_benchmark_models", "log": "benchmark"},
    {"id": "05", "name": "RAG on Grid", "cmd": "moma run ./05_rag_on_grid/rag_query.spl", "dir": "05_rag_on_grid", "log": "rag_query"},
    {"id": "06", "name": "Arxiv Paper Digest", "cmd": "python ./06_arxiv_paper_digest/digest.py 2312.00752", "dir": "06_arxiv_paper_digest", "log": "digest"},
    {"id": "07", "name": "Stress Test", "cmd": "python ./07_stress_test/stress.py -n 5", "dir": "07_stress_test", "log": "stress"},
    {"id": "08", "name": "Model Arena", "cmd": "python ./08_model_arena/arena.py --prompt 'Explain factorials'", "dir": "08_model_arena", "log": "arena"},
    {"id": "09", "name": "Doc Pipeline", "cmd": "python ./09_doc_pipeline/pipeline.py ../docs/spl-paper-v3.0.pdf", "dir": "09_doc_pipeline", "log": "pipeline"},
    {"id": "10", "name": "Chain Relay", "cmd": "python ./10_chain_relay/chain.py 'quantum computing'", "dir": "10_chain_relay", "log": "chain"},
    {"id": "13", "name": "Throughput Scaling", "cmd": "python ./13_multi_agent_throughput/throughput.py", "dir": "13_multi_agent_throughput", "log": "throughput"},
    {"id": "18", "name": "Smart Router", "cmd": "python ./18_smart_router/smart_router.py", "dir": "18_smart_router", "log": "smart_router"},
    {"id": "19", "name": "Privacy Chunk Demo", "cmd": "python ./19_privacy_chunk_demo/privacy_demo.py", "dir": "19_privacy_chunk_demo", "log": "privacy_demo"},
    {"id": "24", "name": "Compiler Pipeline", "cmd": "python ./24_spl_compiler_pipeline/compiler_demo.py", "dir": "24_spl_compiler_pipeline", "log": "compiler_demo"},
    {"id": "26", "name": "Code Guardian", "cmd": "python ./26_code_guardian/guardian.py ./26_code_guardian/guardian.py", "dir": "26_code_guardian", "log": "guardian"},
]

def run_all():
    start_time = datetime.datetime.now()
    print(f"=== Momahub Cookbook Batch Run Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # Ensure we are in the cookbook directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    for recipe in RECIPES:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(recipe["dir"], f"{recipe['log']}_{ts}.log")
        
        print(f"\n[{recipe['id']}] Running {recipe['name']}...")
        print(f"    Command: {recipe['cmd']}")
        print(f"    Logging to: {log_path}")
        
        # Run process, redirecting stderr to stdout, and capture output
        try:
            with open(log_path, 'w') as log_file:
                # Use subprocess.Popen to stream to both terminal and file (simulating 'tee')
                process = subprocess.Popen(recipe["cmd"], shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                
                for line in process.stdout:
                    sys.stdout.write(line)
                    log_file.write(line)
                
                process.wait()
                if process.returncode == 0:
                    print(f"    Result: SUCCESS")
                else:
                    print(f"    Result: FAILED (Exit Code: {process.returncode})")
                    
        except Exception as e:
            print(f"    Result: ERROR ({str(e)})")

    end_time = datetime.datetime.now()
    print(f"\n=== Batch Run Complete: {end_time.strftime('%Y-%m-%d %H:%M:%S')} (Duration: {end_time - start_time}) ===")

if __name__ == "__main__":
    run_all()
