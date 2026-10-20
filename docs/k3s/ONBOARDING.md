# K3s fleet onboarding

One K3s cluster for the whole fleet. The desktop (groot) is the server and GPU
node; other Linux machines join as agents over Tailscale; phones and laptops
can also be read-only clients. Setup is opt-in and never runs from
`./scripts/onboard`.

## Start here

| Device | Role | Command (run on that device) |
| --- | --- | --- |
| Desktop, RTX 3080 Ti | server + GPU worker | `sudo scripts/setup-k3s.sh server`, then `sudo scripts/setup-k3s.sh gpu`, then `scripts/setup-k3s.sh apply` |
| mbp (CachyOS) | CPU agent for API-bound work (free-model relay jobs, tests). Joined 2026-10-19. | copy the token (below), then `sudo scripts/setup-k3s.sh agent <desktop-tailnet-ip>`, then `scripts/setup-k3s.sh admit mbp` from the desktop |
| RTX 2080 Super PC | GPU agent, when it is back online | as mbp, then `sudo scripts/setup-k3s.sh gpu` after labelling it `z0.dev/gpu=rtx2080s` |
| S25 Ultra, omarchy-phone | client only | `ssh 0 'KUBECONFIG=~/.kube/k3s.yaml kubectl get pods -A'` |

## Changes from the original plan (issue #23)

Issue #23 ships a single CPU-only node and keeps every other device as a client.
That is safe but it does not scale work across devices, which is the reason to
use K3s over the existing `kind` lab. This setup keeps all of #23's safety rules
(pinned version, idempotent script, no secrets in Git, restricted untrusted
pods, six-pod ceiling, no public 6443, `kind` kept for disposable tests) and
changes three things:

1. **mbp joins as an agent.** Its CPU is weak, but most fan-out work now waits
   on network calls to free model APIs, not on local compute. A 2015 laptop can
   run many of those relay pods.
2. **GPU is enabled on the desktop from day one, with exclusive scheduling.**
   unsloth training and the shadow-network model server are the workloads that
   need the cluster most, and both need the GPU. There is no GPU sharing,
   KAI or vCluster.
3. **Namespaces split by trust:** `factory` (untrusted OSS code, restricted,
   a 24-pod ceiling above Kueue's per-node quotas; it was six pods on one node), `z0` (our own services and GPU jobs), and `lanes` (free-model
   relays, restricted, CPU only).

## Joining an agent

The join token stays out of Git and off the clipboard:

```sh
# on the agent, as root
install -d -m 0755 /etc/rancher/k3s
ssh kvn@0 'sudo cat /workspace/k3s-data/server/node-token' | install -m 0600 /dev/stdin /etc/rancher/k3s/join-token
sudo scripts/setup-k3s.sh agent 100.113.138.100
```

## Verify

```sh
export KUBECONFIG=$HOME/.kube/k3s.yaml
scripts/setup-k3s.sh status
kubectl create -f config/k3s/smoke/cpu-job.yaml   # expect SMOKE_OK in the logs
kubectl create -f config/k3s/smoke/gpu-job.yaml   # expect GPU_SMOKE_OK
kubectl -n factory logs job/<name>
```

```sh
kubectl create -f config/k3s/smoke/isolation-job.yaml  # expect ISOLATION_OK: DNS and internet open; host, tailnet, LAN blocked
kubectl create -f config/k3s/smoke/gateway-job.yaml    # expect GATEWAY_OK: only the token-gated factory gateway is reachable
```

Finished smoke Jobs delete themselves after 10 minutes.

## Untrusted pods start only after their network policy is live

K3s installs a pod's firewall rules a moment after the pod starts. On a fresh agent
(mbp) an untrusted pod could reach the K8s API in its first second (3/3 probes).
So every `factory`/`lanes` pod must start with the `netpol-ready` init container
(copy it from `config/k3s/smoke/cpu-job.yaml`); it waits until the API is
unreachable before any untrusted container runs. `manifests/40-netpol-ready-gate.yaml`
refuses pods without it. With the gate, 5/5 probes at main-container start were blocked.

## Factory gateway (the one host door for untrusted pods)

Factory jobs sometimes need GitHub data or a model call, and both need the owner's
credentials. The credentials stay on groot, in the oss-factory `ghcache` service
(`tools/factory/install-user-units.sh`): a caching, budgeted GitHub read proxy
whose *pod listener* binds groot's `cni0` address `10.42.0.1:18091`.
`manifests/50-factory-gateway.yaml` adds a small TCP forwarder in `z0`
(`factory-gateway.z0.svc:8080`, pinned to groot) and the two network policies that
let pods labelled `z0.dev/gateway-client=true` reach that forwarder and nothing
else. Pods on mbp cannot reach `10.42.0.1` directly (the host drops it), but
pod-to-pod traffic works, which is why the forwarder exists. The pod listener
refuses requests without a live per-job token, serves only GET reads of public
repos, and meters model-relay calls per job. `smoke/gateway-job.yaml` proves it
(`GATEWAY_OK`, run it pinned to each node).

## Adding a node

New agents join with the taint `z0.dev/onboarding=true:NoSchedule` and take no work.
From the desktop, `scripts/setup-k3s.sh admit <node>` runs the isolation smoke on that
node and removes the taint only on `ISOLATION_OK`. Then
`kubectl create -f config/k3s/smoke/agent-job.yaml` should print `AGENT_SMOKE_OK`.
Root over Tailscale SSH (`ssh root@<node>`) is enough to run the agent install; the
join token goes `sudo cat <data-dir>/server/node-token | ssh root@<node> 'install -m 0600 /dev/stdin /etc/rancher/k3s/join-token'`.

## Queues (Kueue)

`scripts/setup-k3s.sh kueue` installs the pinned Kueue release (hash-checked) and
`config/k3s/kueue/queues.yaml`: one queue per namespace (`factory`, `lanes`, `z0`),
with the single GPU behind the `z0` queue. A Job opts in with the label
`kueue.x-k8s.io/queue-name: <namespace>` and `suspend: true`; Jobs without the label
are untouched. The `factory` queue has one ResourceFlavor per node (`node-mbp`,
then `node-groot`): Kueue fills mbp's share first and spills to a small groot share,
and writes the flavor's node label into the admitted pod, so quota decides
placement. `pods` is a covered resource (16 on mbp, 4 on groot) because measured
factory jobs are network-bound and small; the namespace ResourceQuota (24 pods)
stays as the outer ceiling. When a node joins, add a flavor for it. Proof that GPU
work queues instead of failing:

```sh
kubectl create -f config/k3s/smoke/gpu-queue-job.yaml
kubectl create -f config/k3s/smoke/gpu-queue-job.yaml
kubectl -n z0 get workloads   # one Admitted, one waiting; the second starts when the first ends
```

## Remote read-only access

`kubectl -n kube-system create token fleet-viewer --duration=24h` mints a
read-only token. Put it in a kubeconfig outside Git on the client. Never copy
`~/.kube/k3s.yaml` (cluster admin) to another device.

## Rollback

- Config change: the previous `/etc/rancher/k3s/config.yaml` is kept as
  `config.yaml.bak.<timestamp>`; restore it and `sudo systemctl restart k3s`.
- Remove a node: `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`,
  `kubectl delete node <node>`, then `sudo scripts/setup-k3s.sh uninstall --yes` on it.
- Whole cluster: `sudo scripts/setup-k3s.sh uninstall --yes` on the server.
  This deletes cluster state. The `kind` lab is not touched.
