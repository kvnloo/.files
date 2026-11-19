#!/usr/bin/env bash
# hre_slm_server.sh SERIAL PORT MODEL_FILE [extra llama-server args...]
# (Re)start the HRE labelling llama-server on a phone, natively (adb shell, no UI, no installs).
# Separate from the shadow-<dev> server on :8080 (kevin-phones native_server_restart.py owns that one).
# State: /data/local/tmp/hre-slm/{sup-PORT.pid,server-PORT.log,server-PORT.exits}; runtime llama-b12527.
#
# A small on-phone supervisor (hre-sup.sh) restarts the server only after a CRASH
# (SIGABRT/SIGSEGV/SIGBUS/SIGILL: e.g. the S25 HTP "dspqueue_read failed 0x68" abort), at most
# 30 times in a row. Any other exit ends the supervisor, which is the important case:
# `phone-worker off` winds the S25 down with `kill $(pidof llama-server)` (SIGTERM, rc 143),
# so the owner's off switch stops this server for good. Android's lmkd (SIGKILL, rc 137) also ends it.
set -euo pipefail
serial=$1; port=$2; model=$3; shift 3
root=/data/local/tmp/hre-slm
key=$HOME/.local/state/phone-native-inference/api-key
adb -s "$serial" shell "umask 077; cat > $root/api-key" < "$key"
adb -s "$serial" shell "cat > $root/hre-sup.sh; chmod 755 $root/hre-sup.sh" <<'SUP'
#!/system/bin/sh
# hre-sup.sh PORT BIN LOG -- llama-server args : restart on crash only (see hre_slm_server.sh)
port=$1; bin=$2; log=$3; shift 4
root=/data/local/tmp/hre-slm; n=0
while :; do
  t0=$(date +%s)
  "$bin" "$@" </dev/null >>"$log" 2>&1 &
  c=$!; echo "$c" > "$root/server-$port.child"
  trap 'kill -TERM $c 2>/dev/null; exit 0' TERM INT
  wait "$c"; rc=$?
  echo "$(date +%s) rc=$rc ran=$(( $(date +%s) - t0 ))s" >> "$root/server-$port.exits"
  [ $(( $(date +%s) - t0 )) -gt 600 ] && n=0
  case $rc in
    132|134|135|139) n=$((n + 1)); [ "$n" -gt 30 ] && exit 1; sleep 5 ;;
    *) exit 0 ;;
  esac
done
SUP
extra=$(printf ' %q' "$@")
adb -s "$serial" shell sh <<EOF
set -eu
cd $root
for pf in $root/sup-$port.pid $root/server-$port.pid; do
  [ -s "\$pf" ] || continue
  read pid start < "\$pf"
  if kill -0 "\$pid" 2>/dev/null && [ "\$(awk '{print \$22}' /proc/\$pid/stat)" = "\$start" ]; then
    kill -TERM "\$pid"; for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "\$pid" 2>/dev/null || break; sleep 1; done
  fi
  rm -f "\$pf"
done
if [ -s server-$port.child ]; then
  c=\$(cat server-$port.child)
  tr '\\000' ' ' < /proc/\$c/cmdline 2>/dev/null | grep -q "llama-server.*--port $port" && kill -TERM \$c || true
fi
rt=$root/llama-b12527
if [ -d \$rt/lib ]; then lib=\$rt/lib; bin=\$rt/bin; else lib=\$rt; bin=\$rt; fi
export LD_LIBRARY_PATH=\$lib:/system/lib64:/vendor/lib64 ADSP_LIBRARY_PATH=\$lib
: > $root/server-$port.log
nohup $root/hre-sup.sh $port \$bin/llama-server $root/server-$port.log -- \
   -m $root/models/$model --host 0.0.0.0 --port $port --api-key-file $root/api-key \
   -np 1 --no-webui $extra </dev/null >/dev/null 2>&1 &
pid=\$!; sleep 1
echo "\$pid \$(awk '{print \$22}' /proc/\$pid/stat)" > $root/sup-$port.pid
echo started supervisor \$pid
EOF
ip=${serial%%:*}
for i in $(seq 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://$ip:$port/health" || true)
  [ "$code" = 200 ] && { echo "health 200 http://$ip:$port ($model)"; exit 0; }
  sleep 2
done
echo "not healthy after 180s; tail of log:"; adb -s "$serial" shell "tail -20 $root/server-$port.log"; exit 1
