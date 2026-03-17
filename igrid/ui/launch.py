"""Launch the Streamlit dashboard via moma-ui."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

def main():
    from igrid.cli.config import load_config, hub_url as _hub_url
    cfg = load_config()
    ui = cfg.get("moma_ui", {})

    app_path = Path(__file__).parent / "streamlit" / "app.py"
    resolved_hub = os.environ.get("IGRID_HUB_URL") or _hub_url(cfg)
    port = str(ui.get("port", 8501))

    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path),
           "--server.port", port,
           "--server.headless", "true",
           "--", "--hub-url", resolved_hub]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
