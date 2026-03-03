"""Launch the Streamlit dashboard via moma-ui."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

def main():
    app_path = Path(__file__).parent / "streamlit" / "app.py"
    hub_url = os.environ.get("IGRID_HUB_URL", "http://localhost:8000")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path),
           "--server.headless", "true", "--", "--hub-url", hub_url]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
