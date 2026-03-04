# MoMa Hub Deployment & Operations Guide

**Date:** March 2026
**Status:** Pre-PoC — to be updated after LAN weekend test

---

## Operational Model

MoMa Hub follows the **Signal / Docker Hub model**:

- **Code is open source** (Apache 2.0) — anyone can read, audit, and fork
- **One authoritative hub** operated by the project maintainer
- **Clients default to the official hub** — `moma join` without arguments connects to `hub.momahub.org`
- **Anyone can run a private hub** for their own LAN or organization
- **The network effect is the moat**, not the code

This is how Docker Hub works: `docker pull nginx` defaults to Docker's
registry. The software is open source, anyone can run a private registry,
but the public default is operated by Docker Inc.

### Why not hide the server code?

1. **Trust** — Node operators can audit the reward ledger logic, dispatch
   fairness, and credit calculations. Transparency builds participation.
2. **The hub is not the moat** — The hub is ~500 lines of FastAPI + SQLite.
   The value is the protocol design, SPL integration, community, and
   network effect.
3. **Private hubs are a feature** — Universities, companies, and research
   groups should be able to run internal hubs. This expands the ecosystem.

### Access control layers

| Layer | Mechanism | Status |
|-------|-----------|--------|
| **API key** | Hub requires `X-API-Key` header for agent registration | Implemented |
| **Agent allowlist** | Hub operator approves agents before they receive tasks | Implemented |
| **Operator identity** | Each agent declares an `operator_id`; hub can restrict by operator | Implemented |
| **Rate limiting** | Per-agent task dispatch limits | Implemented |
| **TLS** | HTTPS via reverse proxy (Caddy/nginx) | Deploy-time config |

---

## Domain Name

**Decision:** `momahub.org`

- `.org` signals community / open-source project (like `python.org`, `apache.org`, `kernel.org`)
- `.net` is acceptable but carries less open-source connotation
- `.ai` is overpriced and trendy — avoid
- `.com` — likely taken or expensive

**Subdomains:**

| Subdomain | Purpose |
|-----------|---------|
| `hub.momahub.org` | Official hub API endpoint (FastAPI) |
| `momahub.org` | Project homepage / docs (static site or redirect to GitHub) |
| `ui.momahub.org` | Streamlit dashboard (optional) |

Default client config:
```yaml
# ~/.igrid/config.yaml
hub_urls:
  - https://hub.momahub.org
```

---

## Hosting Options

The hub is a lightweight FastAPI + SQLite application. Resource requirements
are minimal: 1 vCPU, 1 GB RAM, 10 GB disk handles hundreds of agents.

### Recommended: Oracle Cloud Free Tier

**Cost:** $0 (always free)
**Specs:** ARM Ampere A1 — up to 4 OCPUs, 24 GB RAM (free tier)
**Why:** Overkill for MoMa Hub, but free is free. Runs indefinitely.

```bash
# On Oracle Cloud ARM instance (Ubuntu 22.04)
sudo apt update && sudo apt install -y python3-pip
pip install momahub

# Start hub with systemd (see service file below)
moma hub up --host 0.0.0.0 --port 8000 --api-key "$MOMAHUB_API_KEY"
```

### Alternative: Hetzner Cloud

**Cost:** ~$4/month (CX22: 2 vCPU, 4 GB RAM)
**Why:** Best price/performance VPS. EU and US locations.

### Alternative: DigitalOcean

**Cost:** ~$6/month (Basic Droplet: 1 vCPU, 1 GB RAM)
**Why:** Simple setup, good documentation.

### Alternative: Home Server + Cloudflare Tunnel

**Cost:** $0 (if you have a machine running)
**Why:** Full control, no cloud dependency.

```bash
# Expose local hub to the internet without port forwarding
cloudflared tunnel --url http://localhost:8000
```

---

## Production Deployment

### Reverse proxy (Caddy — auto-TLS)

```
# /etc/caddy/Caddyfile
hub.momahub.org {
    reverse_proxy localhost:8000
}
```

Caddy automatically provisions Let's Encrypt TLS certificates.

### Systemd service

```ini
# /etc/systemd/system/momahub.service
[Unit]
Description=MoMa Hub
After=network.target

[Service]
Type=simple
User=momahub
WorkingDirectory=/home/momahub
Environment=MOMAHUB_API_KEY=changeme
ExecStart=/usr/local/bin/moma hub up --host 127.0.0.1 --port 8000 --api-key %E{MOMAHUB_API_KEY}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable momahub
sudo systemctl start momahub
```

### SQLite backup

The hub database is a single file (`.igrid/hub.db`). Back up with:

```bash
# Daily cron — safe online backup via SQLite .backup command
sqlite3 /home/momahub/.igrid/hub.db ".backup /backups/hub-$(date +%Y%m%d).db"
```

---

## Deployment Checklist

### Pre-launch (after LAN PoC)

- [ ] Register `momahub.org` domain
- [ ] Provision Oracle Cloud free tier instance (or Hetzner)
- [ ] Install momahub, configure API key
- [ ] Set up Caddy reverse proxy with TLS
- [ ] Configure systemd service
- [ ] Set up SQLite daily backup cron
- [ ] Test `moma join https://hub.momahub.org` from a remote machine
- [ ] Verify SSE pull mode works through the internet (NAT traversal)

### Post-launch

- [ ] Monitor with `moma status` and Streamlit dashboard
- [ ] Set up uptime monitoring (UptimeRobot free tier or similar)
- [ ] Document the quick-start in GitHub README:
      `pip install momahub && moma join https://hub.momahub.org --pull`
- [ ] Implement agent allowlist for controlled onboarding

---

## Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Unauthorized agents | API key required for `/join`; allowlist (to implement) |
| DDoS on hub | Caddy rate limiting; Cloudflare free tier as CDN/shield |
| Data privacy | Hub only sees task prompts/results — node operators should understand this |
| Reward manipulation | Append-only ledger; Sybil detection via reliability weighting (to implement) |
| SQLite corruption | WAL mode (already enabled); daily backups |

---

## Comparison: Operational Models

| Project | Code | Who operates | Client default |
|---------|------|-------------|----------------|
| **Signal** | Open source (server + client) | Signal Foundation | Signal's servers |
| **Docker Hub** | Open source (Docker engine) | Docker Inc. | registry.hub.docker.com |
| **Matrix/Element** | Open source (Synapse server) | Element (matrix.org) | matrix.org homeserver |
| **Mastodon** | Open source | Anyone (federated) | No default — pick a server |
| **MoMa Hub** | Open source (Apache 2.0) | Project maintainer | hub.momahub.org |

MoMa Hub sits closest to the **Signal/Docker Hub model**: open source code,
single authoritative default, anyone can run their own instance for private use.

Future evolution toward the **Matrix model** (federated hubs with cross-hub
task forwarding) is already architecturally supported — `moma peer add`
enables hub-to-hub peering today.
