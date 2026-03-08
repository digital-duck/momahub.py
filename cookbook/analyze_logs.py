#!/usr/bin/env python3
import os
import re
import glob
import datetime

# Configuration
COOKBOOK_DIR = os.path.dirname(os.path.abspath(__file__))

# Unified Metrics Regex: [model=... tokens=... latency=...ms]
METRICS_RE = re.compile(r"\[model=(?P<model>\S+)\s+tokens=(?P<tokens>\S+)\s+latency=(?P<latency>\S+)\]")

# Specific Regex for varied formats
TRANSLATE_RE = re.compile(r"(?P<complete>\d+)/(?P<total>\d+)\s+translations complete\s+wall=(?P<latency>\S+)")
STRESS_RE = re.compile(r"Grid throughput:\s+(?P<tps>\S+)\s+tokens/s")
BENCHMARK_RE = re.compile(r"(?P<model>\S+)\s+COMPLETE\s+(?P<tokens>\d+)\s+(?P<latency>[\d\.]+)\s+(?P<tps>[\d\.]+)")
ARXIV_RE = re.compile(r"polling\.\.\.\s+done\s+\((?P<tokens>[\d,]+)\s+tokens\)")
PIPELINE_RE = re.compile(r"Summarizing on grid \((?P<model>\S+)\)\.\.\.\s+(?P<tokens>[\d,]+)\s+tokens\s+(?P<latency>\d+ms)")

def parse_log(file_path):
    """Extract metrics from a single log file with multiple format support."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    metrics = {}
    is_success = False
    
    # Identify source file (.spl or .py)
    recipe_dir = os.path.dirname(file_path)
    source_file = None
    for ext in ['*.spl', '*.py']:
        sources = glob.glob(os.path.join(recipe_dir, ext))
        # Filter out common utility files
        sources = [s for s in sources if not os.path.basename(s) in ['analyze_logs.py', 'run_all.py']]
        if sources:
            source_file = os.path.basename(sources[0])
            break
    
    rel_source_path = os.path.join(os.path.basename(recipe_dir), source_file) if source_file else None

    # Check for metrics tag (standard or custom added to logs)
    # Note: Search for all occurrences to handle multi-step scripts (like chain relay)
    metrics_matches = list(METRICS_RE.finditer(content))
    if metrics_matches:
        # For the summary, we'll use the last one found (usually the final synthesis)
        m = metrics_matches[-1].groupdict()
        metrics["model"] = m["model"]
        metrics["tokens"] = m["tokens"]
        metrics["latency"] = m["latency"]
        is_success = True
    
    # format-specific parsers if not captured by standard tag
    if not metrics:
        # Try Batch Translate format
        match = TRANSLATE_RE.search(content)
        if match:
            d = match.groupdict()
            metrics["model"] = "batch"
            metrics["tokens"] = "multiple"
            metrics["latency"] = d["latency"]
            if d["complete"] == d["total"]:
                is_success = True
                
        # Try Stress Test format
        match = STRESS_RE.search(content)
        if match:
            metrics["model"] = "stress"
            metrics["tokens"] = "high-volume"
            metrics["latency"] = f"{match.group('tps')} tps"
            is_success = "Failed: 0" in content

        # Try Arxiv Digest format
        match = ARXIV_RE.search(content)
        if match:
            metrics["model"] = "digest"
            metrics["tokens"] = match.group('tokens')
            metrics["latency"] = "polling"
            if "papers analysed" in content:
                is_success = True

        # Try Document Pipeline format
        match = PIPELINE_RE.search(content)
        if match:
            metrics = match.groupdict()
            if "Done!" in content:
                is_success = True

        # Try Benchmark Models format (tabular)
        if not is_success and "MODEL" in content and "TPS" in content:
            matches = list(BENCHMARK_RE.finditer(content))
            if matches:
                m = matches[0].groupdict()
                metrics["model"] = f"{m['model']} (+{len(matches)-1})"
                metrics["tokens"] = m["tokens"]
                metrics["latency"] = f"{m['latency']}s"
                is_success = True
        
    # Fallback Success Check
    if not is_success:
        completion_markers = ["COMPLETE", "SUCCESS", "Results:", "Report:", "======", "Done!", "Document Pipeline"]
        if any(m in content for m in completion_markers) and "Traceback" not in content:
            is_success = True

    return {
        "file": os.path.basename(file_path),
        "rel_path": os.path.join(os.path.basename(os.path.dirname(file_path)), os.path.basename(file_path)),
        "source_path": rel_source_path,
        "metrics": metrics,
        "success": is_success,
        "timestamp": os.path.getmtime(file_path)
    }

def get_latest_logs():
    """Find the most recent log file in each subdirectory."""
    latest_logs = []
    subdirs = [d for d in os.listdir(COOKBOOK_DIR) if os.path.isdir(os.path.join(COOKBOOK_DIR, d))]
    
    for subdir in sorted(subdirs):
        log_files = glob.glob(os.path.join(COOKBOOK_DIR, subdir, "*.log"))
        if not log_files:
            continue
        
        # Sort by mtime descending
        latest = sorted(log_files, key=os.path.getmtime, reverse=True)[0]
        latest_logs.append((subdir, parse_log(latest)))
        
    return latest_logs

def generate_html(results):
    ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"cookbook-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    file_path = os.path.join(COOKBOOK_DIR, filename)
    
    total = len(results)
    successes = sum(1 for r in results if r[1]["success"])
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Momahub Cookbook Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0e1117; color: #fafafa; margin: 40px; }}
            h1 {{ color: #4f8ef7; border-bottom: 2px solid #1e293b; padding-bottom: 10px; }}
            .summary {{ color: #888; margin-bottom: 30px; font-size: 1.1em; }}
            .summary span {{ color: #3fb950; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #30363d; }}
            th {{ background-color: #21262d; color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: 12px; }}
            tr:hover {{ background-color: #1c2128; }}
            .status-ok {{ color: #3fb950; font-weight: bold; }}
            .status-fail {{ color: #f85149; font-weight: bold; }}
            .metric {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 13px; color: #c9d1d9; }}
            .footer {{ margin-top: 40px; font-size: 12px; color: #8b949e; text-align: center; }}
            code {{ background: #21262d; padding: 2px 4px; border-radius: 4px; }}
            a {{ color: #58a6ff; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>Momahub Cookbook Batch Run Report</h1>
        <div class="summary">Generated on {ts_str} | Status: <span>{successes}/{total} Success</span></div>
        
        <table>
            <thead>
                <tr>
                    <th>Recipe</th>
                    <th>Status</th>
                    <th>Engine/Model</th>
                    <th>Context/Tokens</th>
                    <th>Perf/Latency</th>
                    <th>View Log</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for subdir, res in results:
        status_class = "status-ok" if res["success"] else "status-fail"
        status_text = "SUCCESS" if res["success"] else "FAILED"
        
        m = res["metrics"]
        model = m.get("model", "-")
        tokens = m.get("tokens", "-")
        latency = m.get("latency", "-")
        
        recipe_link = f'<a href="{res["source_path"]}" target="_blank">{subdir}</a>' if res["source_path"] else subdir
        
        html += f"""
                <tr>
                    <td><strong>{recipe_link}</strong></td>
                    <td class="{status_class}">{status_text}</td>
                    <td class="metric">{model}</td>
                    <td class="metric">{tokens}</td>
                    <td class="metric">{latency}</td>
                    <td style="font-size: 11px;"><a href="{res["rel_path"]}" target="_blank">{res["file"]}</a></td>
                </tr>
        """
        
    html += """
            </tbody>
        </table>
        
        <div class="footer">
            Momahub - Decentralized Inference Network &copy; 2026 | Digital Duck & Dog Team
        </div>
    </body>
    </html>
    """
    
    with open(file_path, 'w') as f:
        f.write(html)
    return file_path

if __name__ == "__main__":
    print("Analyzing cookbook logs...")
    results = get_latest_logs()
    if not results:
        print("No log files found.")
    else:
        report_path = generate_html(results)
        print(f"Report generated: {report_path}")
