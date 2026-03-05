#!/usr/bin/env bash
# Recipe 03: Two-hub cluster
HUB_A_URL="http://192.168.1.10:8000"
HUB_B_URL="http://192.168.1.20:8000"
echo "Step 1: moma hub up --hub-url $HUB_A_URL  (on Machine A)"
echo "Step 2: moma hub up --hub-url $HUB_B_URL  (on Machine B)"
echo "Step 3: moma join $HUB_B_URL --host 192.168.1.20 --port 8100  (on Machine B)"
echo "Step 4: moma peer add $HUB_B_URL --hub-url $HUB_A_URL"
echo "Step 5: moma submit 'Hello from hub A' --model llama3 --hub-url $HUB_A_URL"
echo "Step 6: moma peer list --hub-url $HUB_A_URL"
