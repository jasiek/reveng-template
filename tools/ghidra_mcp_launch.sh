#!/usr/bin/env bash
# Launcher for the ghidra-mcp stdio bridge, used by .mcp.json.
#
# Exists so that a fork works without editing .mcp.json: it resolves the bridge
# script from $GHIDRA_MCP_BRIDGE, then from the usual checkout locations, and
# fails with an actionable message instead of a silent MCP connection error.
set -euo pipefail

CANDIDATES=(
  "${GHIDRA_MCP_BRIDGE:-}"
  "${HOME}/github/ghidra-mcp/bridge_mcp_ghidra.py"
  "${HOME}/src/ghidra-mcp/bridge_mcp_ghidra.py"
  "${HOME}/ghidra-mcp/bridge_mcp_ghidra.py"
  "/opt/ghidra-mcp/bridge_mcp_ghidra.py"
)

for c in "${CANDIDATES[@]}"; do
  if [[ -n "${c}" && -f "${c}" ]]; then
    exec "${PYTHON:-python3}" "${c}" --transport stdio
  fi
done

cat >&2 <<'MSG'
ghidra-mcp bridge not found.

Install it from https://github.com/bethington/ghidra-mcp, then either put the
checkout at ~/github/ghidra-mcp, or point this repo at it:

    export GHIDRA_MCP_BRIDGE=/path/to/ghidra-mcp/bridge_mcp_ghidra.py

The bridge also needs the GhidraMCP plugin running inside the Ghidra GUI
(default http://127.0.0.1:8089, override with GHIDRA_MCP_URL).
MSG
exit 1
