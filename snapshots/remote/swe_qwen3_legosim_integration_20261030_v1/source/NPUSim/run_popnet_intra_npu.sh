#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIMULATOR_ROOT="${SIMULATOR_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

POPNET_BIN="$SIMULATOR_ROOT/popnet_chiplet/build/popnet"
BENCH_FILE="${BENCH_FILE:-$SCRIPT_DIR/bench.txt}"
DELAY_FILE="${DELAY_FILE:-$SCRIPT_DIR/delayInfo_npu_intra.txt}"
CONFIG_FILE="${NPUSIM_CONFIG:-$SCRIPT_DIR/npu_config.json}"
CONFIG_NODE_COUNT=""
CONFIG_MAC_COUNT=""
PYTHON_BIN="${PYTHON:-python3}"
if [[ -f "$CONFIG_FILE" ]] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  set +e
  CONFIG_VALUES="$("$PYTHON_BIN" -c "import json, sys; p=sys.argv[1]; root=json.load(open(p, encoding='utf-8')); npu=root.get('npu', {}); topo=npu.get('topology', {}); mac=int(npu.get('mac_unit_count', 0)); mac_nodes=topo.get('mac_nodes'); assert isinstance(mac_nodes, list) and mac_nodes; mac_nodes=[int(x) for x in mac_nodes]; assert mac <= 0 or len(mac_nodes) == mac; assert 'controller_node' in topo or 'controller_local_id' in topo; ctrl=int(topo['controller_node'] if 'controller_node' in topo else topo['controller_local_id']); node_count=int(topo.get('node_count', max([ctrl]+mac_nodes)+1)); print(node_count); print(len(mac_nodes))" "$CONFIG_FILE" 2>/dev/null)"
  CONFIG_STATUS=$?
  set -e
  if [[ "$CONFIG_STATUS" -eq 0 ]]; then
  CONFIG_NODE_COUNT="$(printf '%s\n' "$CONFIG_VALUES" | sed -n '1p')"
  CONFIG_MAC_COUNT="$(printf '%s\n' "$CONFIG_VALUES" | sed -n '2p')"
  fi
fi
MAC_COUNT="${MAC_COUNT:-${CONFIG_MAC_COUNT:-}}"
NODE_COUNT="${NODE_COUNT:-${CONFIG_NODE_COUNT:-}}"
if [[ -z "$NODE_COUNT" ]]; then
  echo "[run_popnet_intra_npu] ERROR: NODE_COUNT is required when it cannot be read from npu_config.json."
  echo "[run_popnet_intra_npu] Provide npu.topology.node_count/mac_nodes/controller_node in NPUSIM_CONFIG or pass NODE_COUNT explicitly."
  exit 1
fi
TOPO_FILE="${TOPO_FILE:-}"
if [[ -z "$TOPO_FILE" ]]; then
  echo "[run_popnet_intra_npu] ERROR: TOPO_FILE is required. Pass TOPO_FILE=path/to/topology.gv from the benchmark script/yml."
  exit 1
fi
if [[ ! -f "$TOPO_FILE" ]]; then
  echo "[run_popnet_intra_npu] ERROR: topology file not found: $TOPO_FILE"
  exit 1
fi
POPNET_LOG_FILE="${POPNET_LOG_FILE:-$SCRIPT_DIR/run_popnet_intra_npu.log}"

if [[ ! -x "$POPNET_BIN" ]]; then
  echo "[run_popnet_intra_npu] ERROR: popnet binary not found: $POPNET_BIN"
  echo "[run_popnet_intra_npu] Build it first: (cd $SIMULATOR_ROOT/popnet_chiplet && make)"
  exit 1
fi

if [[ ! -f "$BENCH_FILE" ]]; then
  echo "[run_popnet_intra_npu] ERROR: bench file not found: $BENCH_FILE"
  echo "[run_popnet_intra_npu] Generate it first: (cd $SCRIPT_DIR && make bench ONNX_MODEL=your_model.onnx)"
  exit 1
fi

"$POPNET_BIN" \
  -A "$NODE_COUNT" \
  -c 1 \
  -V 3 \
  -B 12 \
  -O 12 \
  -F 4 \
  -L 1000 \
  -T 1000000000 \
  -r 1 \
  -I "$BENCH_FILE" \
  -G "$TOPO_FILE" \
  -R 4 \
  -D "$DELAY_FILE" \
  -P >"$POPNET_LOG_FILE" 2>&1

echo "[run_popnet_intra_npu] Done. Delay file: $DELAY_FILE"
