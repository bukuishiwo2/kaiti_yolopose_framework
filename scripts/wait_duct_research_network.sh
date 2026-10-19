#!/usr/bin/env bash
# Wait for the NIC used by the deployed Cyclone config; exit nonzero for retry.
set -euo pipefail
network_iface="${DUCT_DDS_INTERFACE:-wlp4s0}"
wait_seconds="${DUCT_NETWORK_WAIT_SEC:-60}"
if [[ ! "$wait_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo 'DUCT_NETWORK_WAIT_SEC must be a positive integer' >&2
  exit 2
fi
for ((attempt=0; attempt<wait_seconds; attempt++)); do
  if ip -4 -o addr show dev "$network_iface" scope global 2>/dev/null | grep -q ' inet '; then
    echo "DDS interface $network_iface has IPv4; starting RTSP"
    exit 0
  fi
  sleep 1
done
echo "DDS interface $network_iface not ready after ${wait_seconds}s; retry required" >&2
exit 1
