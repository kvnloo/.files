# Local network responsiveness tests

The test uses Ookla's native Linux client to record latency while the line is
idle, downloading, and uploading. Added working latency is the useful
bufferbloat signal; throughput by itself is not an optimization target.

```bash
python -m venv .venv/network
.venv/network/bin/pip install -r network/requirements.txt
.venv/network/bin/python network/bufferbloat.py --json
```

The native client is kept at `.local/network-tools/speedtest`. It is Ookla
Speedtest 1.2.0 for Linux x86_64 and is subject to Ookla's personal-use terms.

For repeated A/B measurements, run this command several times before and
after changing exactly one router setting. Do not run it continuously in the
background: every pass intentionally saturates the Internet connection and
can transfer hundreds of megabytes.

Suggested experiment order:

1. Record three runs with the current two-router topology.
2. Put the Xfinity gateway in bridge mode and reboot both gateways.
3. Record three more runs with NETGEAR Dynamic QoS disabled.
4. Enable Dynamic QoS, enter measured bandwidth manually if offered, and
   record another three runs.
5. Keep the setting with the lowest loaded p95 latency that does not cause an
   unacceptable throughput reduction.
