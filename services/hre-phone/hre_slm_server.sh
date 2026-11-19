#!/usr/bin/env bash
# hre_slm_server.sh SERIAL PORT MODEL_FILE [extra llama-server args...]
# (Re)start the HRE labelling llama-server on a phone, natively (adb shell, no UI, no installs).
# Separate from the shadow-<dev> server on :8080 (kevin-phones native_server_restart.py owns that one).
# State: /data/local/tmp/hre-slm/{server-PORT.pid,server-PORT.log}; runtime llama-b12527; API key required.
set -euo pipefail
serial=$1; port=$2; model=$3; shift 3
root=/data/local/tmp/hre-slm
key=$HOME/.local/state/phone-native-inference/api-key
adb -s "$serial" shell "umask 077; cat > $root/api-key" < "$key"
extra=$(printf ' %q' "$@")
adb -s "$serial" shell sh <<EOF
set -eu
cd $root
pf=$root/server-$port.pid
if [ -s "\$pf" ]; then
  read pid start < "\$pf"
  if kill -0 "\$pid" 2>/dev/null && [ "\$(awk '{print \$22}' /proc/\$pid/stat)" = "\$start" ] \
     && tr '\\000' ' ' < /proc/\$pid/cmdline | grep -q "llama-b12527/.*llama-server.*--port $port"; then
    kill -TERM "\$pid"; for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "\$pid" 2>/dev/null || break; sleep 1; done
  fi
fi
rt=$root/llama-b12527
if [ -d \$rt/lib ]; then lib=\$rt/lib; bin=\$rt/bin; else lib=\$rt; bin=\$rt; fi
export LD_LIBRARY_PATH=\$lib:/system/lib64:/vendor/lib64 ADSP_LIBRARY_PATH=\$lib
nohup \$bin/llama-server -m $root/models/$model --host 0.0.0.0 --port $port --api-key-file $root/api-key \
   -np 1 --no-webui $extra </dev/null > $root/server-$port.log 2>&1 &
pid=\$!; sleep 1
echo "\$pid \$(awk '{print \$22}' /proc/\$pid/stat)" > \$pf
echo started \$pid
EOF
ip=${serial%%:*}
for i in $(seq 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://$ip:$port/health" || true)
  [ "$code" = 200 ] && { echo "health 200 http://$ip:$port ($model)"; exit 0; }
  sleep 2
done
echo "not healthy after 180s; tail of log:"; adb -s "$serial" shell "tail -20 $root/server-$port.log"; exit 1
