# Component Spec: moma CLI (Interface v1)
**Objective:** A Python-based CLI that makes i-grid participation as simple as `git` or `docker`.

## 1. Core Commands

| Command | Logic / Action |
| :--- | :--- |
| `moma join <url>` | Handshake with Hub, detect hardware, and register identity. |
| `moma up` | Load identity, start the background `pulse` loop, and enter "Listen" state for tasks. |
| `moma down` | Gracefully sign off the grid and stop the heartbeat/pulse loop. |
| `moma status` | Query the Hub for current session stats, grid rank, and reward points. |
| `moma reward` | Manage "moma rewards" (points). View balance, history, or redeem points. |
| `moma benchmark` | Run a local speed test (tokens/sec) via Ollama to determine Contribution Tier. |
| `moma config` | Manage local settings (YAML-based) using `dd-config`. |
| `moma models` | List local Ollama models and set "serving preferences" for the grid. |
| `moma logs` | Stream real-time agent activity and task processing logs. |
| `moma check` | Diagnostic: Verify connectivity to both Hub and local Ollama service. |

## 2. Configuration & Identity
- **Format:** YAML
- **Library:** `dd-config` (https://github.com/digital-duck/dd-config)
- **Path:** `~/.moma/config.yaml`
- **Identity:** Persistent `node_id` and `secret_key` stored securely in the config.

## 3. Reward System (moma reward)
- **Concept:** Points-based system similar to credit card rewards.
- **Earning:** Points earned per successful token processed + uptime bonuses.
- **Redemption:** Points can be redeemed for "Priority Inference" on the grid or cashed out.
