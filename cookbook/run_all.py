#!/usr/bin/env python3
"""run_all.py — Momahub Cookbook batch runner.

Recipes are defined in cookbook/cookbook_catalog.json — edit that file to
add, remove, or update recipes without touching Python code.

Usage:
    python cookbook/run_all.py                           # run all active recipes
    python cookbook/run_all.py --hub http://host:8000    # custom hub
    python cookbook/run_all.py --ids 04,08,13            # run specific recipes by ID
    python cookbook/run_all.py --list                    # brief recipe list
    python cookbook/run_all.py --catalog                 # full catalog table
    python cookbook/run_all.py --catalog --category performance
    python cookbook/run_all.py --catalog --status new
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

COOKBOOK_DIR = Path(__file__).resolve().parent

# Approval status values
STATUS_APPROVED = "approved"
STATUS_NEW      = "new"
STATUS_WIP      = "wip"
STATUS_DISABLED = "disabled"
STATUS_REJECTED = "rejected"

# Status markers (visual indicators)
MARKERS = {
    "active":         "✅",
    STATUS_NEW:       "🆕",
    STATUS_WIP:       "🔧",
    STATUS_DISABLED:  "⏸ ",
    STATUS_REJECTED:  "❌",
}


def load_catalog() -> list[dict]:
    path = COOKBOOK_DIR / "cookbook_catalog.json"
    with open(path) as f:
        data = json.load(f)
    return data["recipes"]


def default_hub_url() -> str:
    config_path = Path.home() / ".igrid" / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            hub = cfg.get("hub", {})
            urls = hub.get("urls", [])
            if urls:
                return urls[0].rstrip("/")
            port = hub.get("port")
            if port:
                return f"http://localhost:{port}"
        except Exception:
            pass
    return "http://localhost:8000"


def apply_filters(recipes: list[dict], cat_filter: str, status_filter: str) -> list[dict]:
    out = []
    for r in recipes:
        if cat_filter and r.get("category") != cat_filter:
            continue
        if status_filter and r.get("approval_status") != status_filter:
            continue
        out.append(r)
    return out


def status_marker(r: dict) -> str:
    if r.get("is_active"):
        return MARKERS["active"]
    return MARKERS.get(r.get("approval_status", ""), "  ")


def print_list(recipes: list[dict], cat_filter: str, status_filter: str) -> None:
    filtered = apply_filters(recipes, cat_filter, status_filter)
    label = f" (category={cat_filter!r} status={status_filter!r})" if (cat_filter or status_filter) else ""
    print(f"Momahub Cookbook — {len(filtered)} recipes{label}")
    for r in filtered:
        print(f"  {r['id']:<4}  {status_marker(r)}  {r['name']:<28}  {r.get('approval_status',''):<12}  {r.get('category',''):<14}  {r.get('description','')}")


def print_catalog(recipes: list[dict], cat_filter: str, status_filter: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filtered = apply_filters(recipes, cat_filter, status_filter)

    counts: dict[str, int] = {}
    for r in recipes:
        if r.get("is_active"):
            counts["active"] = counts.get("active", 0) + 1
        status = r.get("approval_status", "")
        counts[status] = counts.get(status, 0) + 1

    print(f"=== Momahub Cookbook Catalog — {now} ===")
    if cat_filter or status_filter:
        print(f"    Filter: category={cat_filter!r}  status={status_filter!r}  → {len(filtered)}/{len(recipes)} recipes\n")
    else:
        print(f"    Total: {len(recipes)} recipes  |  {counts.get('active', 0)} active  |  {counts.get(STATUS_NEW, 0)} new  |  {counts.get(STATUS_DISABLED, 0)} disabled\n")

    print(f"{'ID':<4}  {'':2}  {'Name':<28}  {'Category':<14}  {'Status':<12}  Description")
    print("-" * 100)
    for r in filtered:
        print(f"{r['id']:<4}  {status_marker(r)}  {r['name']:<28}  {r.get('category',''):<14}  {r.get('approval_status',''):<12}  {r.get('description','')}")

    print()
    print("Markers: ✅ active  🆕 new  🔧 wip  ⏸  disabled  ❌ rejected\n")
    print("Run active recipes:           python cookbook/run_all.py")
    print("Run specific recipe:          python cookbook/run_all.py --ids 04,13")
    print("Run any (incl. inactive):     python cookbook/run_all.py --ids 29")
    print("Filter catalog by category:   python cookbook/run_all.py --catalog --category performance")
    print("Filter catalog by status:     python cookbook/run_all.py --catalog --status new")

    cat_counts: dict[str, int] = {}
    for r in recipes:
        c = r.get("category", "")
        cat_counts[c] = cat_counts.get(c, 0) + 1
    parts = [f"{c}({n})" for c, n in sorted(cat_counts.items())]
    print(f"\nCategories: {'  '.join(parts)}")


def run_recipe(args: list[str], log_path: Path, cwd: Path) -> tuple[bool, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now()
    try:
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(cwd),
            )
            for line in (process.stdout or []):
                sys.stdout.write(f"     | {line}")
                log_file.write(line)
            process.wait()
            ok = process.returncode == 0
    except Exception as e:
        print(f"     | ERROR: {e}")
        ok = False
    elapsed = (datetime.now() - start).total_seconds()
    return ok, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Momahub Cookbook batch runner")
    parser.add_argument("--hub", default=None, help="Hub URL (default: from ~/.igrid/config.yaml)")
    parser.add_argument("--ids", default="", help="Comma-separated recipe IDs to run")
    parser.add_argument("--list", action="store_true", dest="list_recipes", help="List recipes and exit")
    parser.add_argument("--catalog", action="store_true", help="Print full catalog table and exit")
    parser.add_argument("--category", default="", help="Filter by category (use with --catalog or --list)")
    parser.add_argument("--status", default="", help="Filter by approval_status (use with --catalog or --list)")
    args = parser.parse_args()

    hub_url = (args.hub or default_hub_url()).rstrip("/")
    recipes = load_catalog()

    if args.catalog:
        print_catalog(recipes, args.category, args.status)
        return

    if args.list_recipes:
        print_list(recipes, args.category, args.status)
        return

    # Build ID filter set
    id_filter: set[str] = set()
    if args.ids:
        id_filter = {i.strip() for i in args.ids.split(",")}

    start_all = datetime.now()
    print(f"=== Momahub Cookbook Batch Run — {start_all.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"    Hub: {hub_url}\n")

    os.chdir(COOKBOOK_DIR)

    results: list[dict] = []

    for recipe in recipes:
        rid = recipe["id"]

        if id_filter:
            if rid not in id_filter:
                continue
        elif not recipe.get("is_active"):
            print(f"[{rid}] {recipe['name']}  (skipping — {recipe.get('approval_status','').upper()})\n")
            continue

        # Substitute {hub} placeholder in args
        cmd_args = [a.replace("{hub}", hub_url) for a in recipe["args"]]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = COOKBOOK_DIR / recipe["dir"] / f"{recipe['log']}_{ts}.log"

        print(f"[{rid}] {recipe['name']}")
        print(f"     cmd : {' '.join(cmd_args)}")
        print(f"     log : {log_path}")

        ok, elapsed = run_recipe(cmd_args, log_path, COOKBOOK_DIR)
        status = "SUCCESS" if ok else "FAILED"
        print(f"     result: {status}  ({elapsed:.1f}s)\n")

        results.append({"id": rid, "name": recipe["name"], "ok": ok, "elapsed": elapsed})

    # Summary table
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    total_elapsed = (datetime.now() - start_all).total_seconds()
    print(f"=== Summary: {passed}/{total} Success  (total {total_elapsed:.1f}s) ===\n")

    print(f"{'ID':<4}  {'Recipe':<28}  {'Status':<8}  {'Elapsed':>8}")
    print("-" * 56)
    for r in results:
        status = "OK" if r["ok"] else "FAILED"
        print(f"{r['id']:<4}  {r['name']:<28}  {status:<8}  {r['elapsed']:>7.1f}s")
    print()


if __name__ == "__main__":
    main()
