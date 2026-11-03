#!/system/bin/sh
# phone-harness fast tree supervisor (pushed to /data/local/tmp/ph-u2/run.sh).
# Runs the openatx uiautomator2 jar server (no APK, no root) and stops it
# after IDLE seconds without a client touching last_use.
#   sh run.sh [IDLE_SECONDS] [DEVICE_PORT]
D=/data/local/tmp/ph-u2
IDLE=${1:-1800}
PORT=${2:-9118}
cd "$D" || exit 1
echo $$ > supervisor.pid
touch last_use
CLASSPATH="$D/u2.jar" app_process / com.wetest.uia2.Main -p "$PORT" > server.log 2>&1 &
SP=$!
echo $SP > server.pid
while kill -0 $SP 2>/dev/null; do
  sleep 20
  now=$(date +%s)
  last=$(stat -c %Y last_use 2>/dev/null || echo 0)
  if [ $((now - last)) -gt "$IDLE" ]; then
    echo "idle ${IDLE}s: stopping" >> server.log
    kill $SP
    break
  fi
done
rm -f server.pid supervisor.pid
