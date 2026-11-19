#!/usr/bin/env bash
# calib_lane.sh PORT THREADS MODEL.gguf:MODE... : serve each candidate on MBP CPU, label calib-200, stop.
set -u
port=$1; thr=$2; shift 2
B=$HOME/phone-slm-20261118/ubuntu/llama-b12527
cd "$HOME/hre-phone"
for spec in "$@"; do
  m=${spec%%:*}; mode=${spec##*:}
  tag=$(basename "$m" .gguf)
  LD_LIBRARY_PATH=$B "$B/llama-server" -m "$HOME/phone-slm-20261118/$m" -c 4096 -b 4096 -ub 4096 -np 1 -t "$thr" \
     --host 127.0.0.1 --port "$port" --reasoning off --no-webui >"srv-$tag.log" 2>&1 &
  pid=$!
  for i in $(seq 120); do curl -fs "http://127.0.0.1:$port/health" >/dev/null && break; sleep 2; done
  start=$(date +%s)
  python3 phone_label.py --url "http://127.0.0.1:$port" --in calib-200.jsonl --mode "$mode" \
     --out "calib-$tag.jsonl" --model-tag "$tag" --worker mbp-cpu >"run-$tag.log" 2>&1
  echo "$tag $mode wall=$(( $(date +%s) - start ))s" >>"run-$tag.log"
  kill "$pid"; wait "$pid" 2>/dev/null
done
echo lane-done
