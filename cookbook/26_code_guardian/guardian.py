#!/usr/bin/env python3
"""Recipe 26: Momahub Code Guardian.
Specialized multi-model code review across Security, Performance, Docs, and Refactoring.
"""
import asyncio
import click
import os
import sys
from datetime import datetime

# Add root to sys.path for igrid imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from igrid.spl.runner import run_spl_file
from igrid.cli.config import load_config, hub_url as _hub_url

@click.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--hub", help="Momahub Hub URL")
def main(file_path, hub):
    config = load_config()
    hub_url = hub or _hub_url(config)
    
    with open(file_path, 'r') as f:
        code_content = f.read()
    
    click.echo(f"🛡️  Guardian: Analyzing {file_path}...")
    click.echo(f"📍 Hub: {hub_url}")
    
    spl_path = os.path.join(os.path.dirname(__file__), "code_guardian.spl")
    
    # Run the SPL program on the grid
    asyncio.run(run_spl_file(spl_path, hub_url, params={"source_code": code_content}))
    
    click.echo("\n✅ Analysis Complete. [See console logs for breakdown]")

if __name__ == "__main__":
    main()
