#!/usr/bin/env python3
# Recipe 34: Junior Developer Assistant — Code Analysis Pipeline
#
# 3 stages:
#   Stage 1: Code Review  (parallel with Stage 2)
#   Stage 2: Refactoring Analysis  (parallel with Stage 1)
#   Stage 3: Documentation Generation  (sequential, depends on stages 1 & 2)
#
# Usage:
#   python junior_dev_assistant.py
#   python junior_dev_assistant.py --hub http://localhost:8000 --model qwen2.5-coder:7b

import json
import os
import time
import uuid
import click
import httpx
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, wait

SAMPLE_CODE = '''package main

import (
	"fmt"
	"strconv"
	"strings"
)

// UserData stores user information
type UserData struct {
	Name string
	Age  int
	Email string
}

func processUser(name string, age string, email string) *UserData {
	ageInt, err := strconv.Atoi(age)
	if err != nil {
		ageInt = 0
	}

	// Basic validation
	if len(name) == 0 {
		name = "Unknown"
	}

	if !strings.Contains(email, "@") {
		email = ""
	}

	user := &UserData{
		Name: name,
		Age: ageInt,
		Email: email,
	}

	return user
}

func printUserInfo(user *UserData) {
	fmt.Printf("User: %s, Age: %d, Email: %s\\n", user.Name, user.Age, user.Email)
}

func main() {
	users := []string{
		"John,25,john@email.com",
		"Jane,30,jane@email.com",
		"Bob,invalid,bob@email.com",
	}

	for _, userStr := range users {
		parts := strings.Split(userStr, ",")
		if len(parts) != 3 {
			continue
		}

		user := processUser(parts[0], parts[1], parts[2])
		printUserInfo(user)
	}
}'''

CODE_REVIEW_PROMPT = """You are a senior Go developer performing a thorough code review.

Analyze this Go code and provide:
1. **Code Quality Issues**: Identify bugs, inefficiencies, or poor practices
2. **Security Concerns**: Point out potential security vulnerabilities
3. **Go Best Practices**: Suggest improvements following Go idioms
4. **Performance Optimizations**: Identify bottlenecks or optimization opportunities

Be specific and actionable. Focus on critical issues first.

Code to review:
{}"""

REFACTOR_PROMPT = """You are an experienced software architect specializing in code maintainability.

Analyze this Go code and identify refactoring opportunities:

1. **Function Decomposition**: Functions that are too large or do too many things
2. **Code Duplication**: Repeated logic that could be extracted
3. **Naming Improvements**: Better variable/function names for clarity
4. **Structure Optimization**: Better organization of types, interfaces, or packages
5. **Error Handling**: More robust error handling patterns
6. **Testability**: Changes to make code more testable

Provide specific suggestions with brief code examples where helpful.

Code to analyze:
{}"""

DOCUMENTATION_PROMPT = """You are a technical writer creating development documentation.

Based on the code review and refactoring suggestions provided, create a comprehensive summary document:

1. **Executive Summary**: High-level overview of the code analysis
2. **Critical Issues Found**: Priority list of problems that need immediate attention
3. **Refactoring Roadmap**: Step-by-step plan for code improvements
4. **Implementation Notes**: Practical guidance for developers
5. **Quality Metrics**: Measurable improvements expected after changes

Make it clear, actionable, and suitable for both junior and senior developers.

Original Code:
{}

Code Review Results:
{}

Refactoring Suggestions:
{}"""


def default_hub_url():
    config_path = os.path.expanduser("~/.igrid/config.yaml")
    try:
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        hub_urls = cfg.get("hub", {}).get("urls", [])
        if hub_urls:
            return hub_urls[0].rstrip("/")
        port = cfg.get("hub", {}).get("port")
        if port:
            return f"http://localhost:{port}"
    except Exception:
        pass
    return "http://localhost:8000"


def truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= max_len else s[:max_len] + "..."


def submit_task(hub_url: str, model: str, system: str, prompt: str) -> dict:
    task_id = str(uuid.uuid4())
    t0 = time.monotonic()

    with httpx.Client(timeout=60.0) as client:
        client.post(f"{hub_url}/tasks", json={
            "task_id": task_id,
            "model": model,
            "system": system,
            "prompt": prompt,
            "max_tokens": 1500,
            "temperature": 0.1,
        }, timeout=10.0).raise_for_status()

        for _ in range(90):
            time.sleep(2.0)
            try:
                resp = client.get(f"{hub_url}/tasks/{task_id}", timeout=5.0)
                data = resp.json()
                state = data.get("state", "")
                if state == "COMPLETE":
                    res = data.get("result", {})
                    return {
                        "state": "COMPLETE",
                        "model": model,
                        "content": str(res.get("content", "")),
                        "output_tokens": res.get("output_tokens", 0),
                        "latency_ms": (time.monotonic() - t0) * 1000,
                        "agent_id": str(res.get("agent_id", "")),
                    }
                if state == "FAILED":
                    return {
                        "state": "FAILED",
                        "model": model,
                        "error": f"Task failed: {data.get('error', '')}",
                    }
            except Exception:
                pass

    return {
        "state": "TIMEOUT",
        "model": model,
        "error": "Task timeout after 3 minutes",
    }


def run_code_review(hub_url: str, model: str) -> dict:
    print(f"  Running code review with {model}...")
    result = submit_task(
        hub_url, model,
        "You are a senior Go developer and code reviewer. Focus on practical, actionable feedback.",
        CODE_REVIEW_PROMPT.format(SAMPLE_CODE),
    )
    result["stage"] = "code_review"
    lat = int(result.get("latency_ms", 0))
    agent = result.get("agent_id", "")
    print(f"      Code review completed ({lat}ms, {agent})")
    return result


def run_refactoring_analysis(hub_url: str, model: str) -> dict:
    print(f"  Analyzing refactoring opportunities with {model}...")
    result = submit_task(
        hub_url, model,
        "You are a software architect specializing in Go code maintainability and clean architecture.",
        REFACTOR_PROMPT.format(SAMPLE_CODE),
    )
    result["stage"] = "refactoring"
    lat = int(result.get("latency_ms", 0))
    agent = result.get("agent_id", "")
    print(f"      Refactoring analysis completed ({lat}ms, {agent})")
    return result


def run_documentation(hub_url: str, model: str, code_review: dict, refactoring: dict) -> dict:
    print(f"  Generating development documentation with {model}...")
    result = submit_task(
        hub_url, model,
        "You are a technical writer creating clear, actionable development documentation.",
        DOCUMENTATION_PROMPT.format(
            SAMPLE_CODE,
            code_review.get("content", ""),
            refactoring.get("content", ""),
        ),
    )
    result["stage"] = "documentation"
    lat = int(result.get("latency_ms", 0))
    agent = result.get("agent_id", "")
    print(f"      Documentation generated ({lat}ms, {agent})")
    return result


def save_results(out_dir: str, report: dict):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"junior_dev_assistant_{ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Results saved: {path}")


@click.command()
@click.option("--hub", default=None, help="Hub URL (default: from config or http://localhost:8000)")
@click.option("--model", default="qwen2.5-coder:7b", help="Model to use for analysis")
@click.option("--out", "out_dir", default="out", help="Output directory")
def main(hub, model, out_dir):
    """Junior Developer Assistant — code review + refactoring (parallel) + documentation."""
    hub_url = hub or default_hub_url()
    code_lines = len(SAMPLE_CODE.split("\n"))

    print("Junior Developer Assistant — Code Analysis Pipeline")
    print(f"   Hub: {hub_url}")
    print(f"   Model: {model}")
    print(f"   Sample code: {code_lines} lines\n")

    start = time.monotonic()

    # Stages 1 & 2: code review and refactoring analysis in parallel
    code_review = None
    refactoring = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_review = executor.submit(run_code_review, hub_url, model)
        f_refactor = executor.submit(run_refactoring_analysis, hub_url, model)
        wait([f_review, f_refactor])
        code_review = f_review.result()
        refactoring = f_refactor.result()

    if code_review.get("state") != "COMPLETE":
        print(f"Code review failed: {code_review.get('error', 'unknown')}")
        return
    if refactoring.get("state") != "COMPLETE":
        print(f"Refactoring analysis failed: {refactoring.get('error', 'unknown')}")
        return

    # Stage 3: documentation — sequential, depends on stages 1 & 2
    documentation = run_documentation(hub_url, model, code_review, refactoring)

    total_latency = time.monotonic() - start
    total_tokens = int(
        code_review.get("output_tokens", 0)
        + refactoring.get("output_tokens", 0)
        + documentation.get("output_tokens", 0)
    )
    summary = (
        f"Code analysis completed: {model} reviewed {code_lines} lines, "
        f"identified improvement opportunities, generated documentation ({total_tokens} tokens total)"
    )

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code_review": code_review,
        "refactoring": refactoring,
        "documentation": documentation,
        "total_latency_s": total_latency,
        "summary": summary,
    }

    save_results(out_dir, report)

    print("\nAnalysis Complete!")
    print(f"   Code Review: {code_review['state']} ({int(code_review.get('output_tokens', 0))} tokens)")
    print(f"   Refactoring: {refactoring['state']} ({int(refactoring.get('output_tokens', 0))} tokens)")
    print(f"   Documentation: {documentation['state']} ({int(documentation.get('output_tokens', 0))} tokens)")
    print(f"   Total Time: {total_latency:.1f}s")
    print(f"   Summary: {summary}")

    print("\nSample Outputs:")
    print(f"   Code Review: {truncate(code_review.get('content', ''), 100)}...")
    print(f"   Refactoring: {truncate(refactoring.get('content', ''), 100)}...")
    print(f"   Documentation: {truncate(documentation.get('content', ''), 100)}...")


if __name__ == "__main__":
    main()
