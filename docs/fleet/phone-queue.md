# Phone queue (k3s, groot): one front door for the S22+ and S25 Ultra

Agents that want to use a phone send a job to one service, and that service does the rest:
it waits for a free phone, checks whether the owner allows it, runs the UI scripting and the
Luna agent loop, and writes a receipt. Two agents never drive the same phone at once. k3s
(Kueue) does the queueing.

- **Endpoint:** `http://100.113.138.100:8792`. groot `:8790` is taken by garden_room, so
  this service uses 8792. Both groot loopback and the tailnet IP listen.
- **CLI:** `phoneq` (in `~/.local/bin` on groot and mbp). Override the endpoint with
  `$PHONEQ_URL`.
- **Code:** `services/phone-queue/`.
- **Manifests:** `config/k3s/manifests/60-phone-queue*.yaml`, plus the Kueue objects in
  `config/k3s/kueue/phones.yaml`.

## API

| Call | Result |
|---|---|
| `POST /v1/jobs` | `202 {id, state}`. A replay with the same `submitter`+`idempotency_key` returns `200` with the existing id. |
| `GET /v1/jobs/{id}` | `{id, kind, device, state, submitter, model, created_at, started_at, finished_at, result?, error?}` |
| `GET /v1/jobs?submitter=&state=&device=&limit=` | `{jobs: [...]}`, newest first |
| `POST /v1/jobs/{id}/cancel` | Deletes the k8s Job. A running runner gets SIGTERM and still restores the foreground app and releases the lock. |
| `GET /v1/devices` | Per phone: `{id, serial, online, gate:{allowed, reason}, lock_holder?, foreground?, battery?, queue_depth}` |
| `GET /healthz` | Status of the DB, k8s, `z0.dev/phone` capacity and the model shim |

**Job body:**

```
{kind: "chat"|"goal", device: "s22"|"s25"|"any", submitter,
 app?, prompt? (chat), goal? (goal),
 model? (default openai-codex/gpt-6-luna),
 harness? ("script" for chat, "fx" for goal),
 max_steps?, idempotency_key?, priority?, reset?: "home"|"none",
 oracle?: {type: "tree_text", must_contain?, must_not_contain?, package?}}
```

**States:** `queued` → `admitted` (Kueue reserved the phone) → `running` → `succeeded` |
`failed` | `cancelled`.

**`blocked`** means one of these is closed: the phone's gate, the ChatGPT quota pause or
pace budget, or the UI lock. The job stays queued and is retried every 30 s. It never fails
because of a closed gate.

**`result`** carries:
- `final_output`, `steps`, `oracle_pass`, `oracle` (the details);
- `transcript_path` (`<state>/jobs/<id>/transcript.jsonl`; each row has `type`
  decision|action|model_error|oracle, plus `choose_ms` per model decision and `tool_ms` per
  phone action);
- `transcript_dir`, `tokens_in`, `tokens_out`, `ms`, `cold_ms` (u2 connect + health);
- `lock_wait_ms`, `pace_wait_ms`;
- `foreground_before`, `foreground_after_job`, `restored`;
- `chat` (for chat jobs) and `fx` (for fx jobs);
- `error_code`.

A model that no route can serve fails at once, without taking a phone slot. Its error is
`"model_unavailable: ..."` and its result carries `error_code: "model_unavailable"`.

```
phoneq submit goal --device s22 --goal "Open Settings > About phone and report the Android version" \
       --must-contain 16 --wait
phoneq submit chat --device s22 --app chatgpt --prompt "..." --wait
phoneq devices | phoneq list --state queued | phoneq status ID | phoneq wait ID | phoneq cancel ID
```

## How it works

```
agents ──HTTP──> phone-queue Deployment (ns phones, groot, hostNetwork)
                  ├ api: server.py  SQLite at /mnt/zer0models/phone-queue/state/phoneq.db
                  │      reconciler: job row -> batch/v1 Job (suspended by Kueue)
                  └ model-shim: model_shim.py on 127.0.0.1:8795 (fx's model gateway)
Kueue: LocalQueue phones -> ClusterQueue phones
       flavors phone-s22 / phone-s25, z0.dev/phone nominalQuota 1 each
       -> one admitted Job per phone; the rest wait as pending Workloads
Job pod (runner.py, same ConfigMap code, chatgpt-driver venv python):
   gate -> pace -> flock /tmp/<dev>-ui.lock -> re-gate -> record foreground
   -> harness -> oracle on a fresh hierarchy -> restore foreground -> result.json
```

**Kueue design.** groot advertises the extended resource `z0.dev/phone = 2` by running
`services/phone-queue/advertise-phones`, which is the documented node-status patch. Every
phone Job requests `z0.dev/phone: 1`.

The ClusterQueue has two ResourceFlavors, one per phone, each with quota 1. Each flavor
carries a Kueue-only taint `z0.dev/phone=<dev>`. A job for `s22` tolerates only the s22
flavor. A job for `any` tolerates every phone whose gate is open at creation, so Kueue's
flavor fungibility gives it the first free one. The runner reads the assigned flavor from
its Workload.

Why one resource with two flavors and not `z0.dev/phone-s22` + `z0.dev/phone-s25`: a pod
requests fixed resource names, so it cannot express "any phone". Per-phone flavors can.

The queue uses `BestEffortFIFO`, so an S22 backlog never holds back a job the free S25
could run. `withinClusterQueue: Never` means a running phone job is never preempted.
`priority > 0` maps to WorkloadPriorityClass `phone-urgent`, which puts the job ahead in
the queue but never evicts a running one.

**Harnesses.**
- **chat / script.** Reuses the deterministic drivers in place:
  - ChatGPT: `chatgpt-driver/burst.py` `new_chat` + `send`, the `pace.py` budget, the shared
    `/tmp/chatgpt-quota-pause`, and rate-limit detection (sets the same 3 h pause). The
    reply is read from the redacted hierarchy after the tagged user bubble. The clipboard
    is never read.
  - DeepSeek: `deepseek_burst.dispatch` on the S22 only. It records a launch receipt and has
    no reply harvester.
  - Dispatches are appended to `chatgpt-driver/phoneq-01/dispatches.jsonl`.
- **goal (and chat with harness=fx).** Runs vercel-labs fx with
  `fx ask --json --no-save --auto --model <id>`. Each job gets its own HOME
  (`<job>/fxhome`, `~/.fx` 0700) and `FX_MAX_AGENT_STEPS=max_steps`.
  - `FX_GATEWAY_BASE_URL` and `FX_GATEWAY_CHAT_URL` point fx at the model shim. The bearer
    token is `phoneq-job-<id>`, so the shim writes a per-job `model.jsonl`.
  - The shim exposes only the phone MCP server: `phone_tools.py mcp` (stdio). Its verbs are
    observe, tap, set_text, swipe, back, home, launch and wait.
- **Model routes (shim):**
  - `openai-codex/<slug>` uses the ChatGPT subscription through Hermes, the same way
    `dash-log-watch-model.py` does it: `resolve_provider_client("openai-codex", model=slug,
    raw_codex=True)` with `HERMES_HOME=~/.hermes/profiles/clean`. Slugs are gpt-6-luna,
    gpt-6-terra, gpt-6-sol, gpt-6.1-luna, gpt-6.1-terra, gpt-6.1-sol and gpt-5.6-*.
  - `groot-router/<id>` uses the llama router at `100.113.138.100:11530`.
  - `ollama/<id>` uses `127.0.0.1:11434`.
  - `local/<id>` uses the router first, then ollama.
  - `gateway/<id>` uses the real Vercel AI Gateway, only when the shim has
    `AI_GATEWAY_API_KEY`. None is configured, so it returns `model_unavailable`.
  - Availability preflight: `GET 127.0.0.1:8795/phoneq/available?model=`.
- **Oracle.** `tree_text` checks the case-insensitive substrings `must_contain` and
  `must_not_contain`, and optionally the foreground `package`. It runs against a fresh
  redacted hierarchy and matches both `text` and `content-desc`. It runs after the
  harness, independent of the agent's own "done". If the oracle fails, the job is `failed`.

## Phone safety (enforced in code)

- **Nothing is ever installed, uninstalled or reset.** `adbutils` install/uninstall, u2
  `_setup_ime`, `send_keys`, `app_install`/`app_uninstall`/`app_clear` and the IME setters
  are patched to raise in every process (the `ds_burst` rule). `launch` refuses stores,
  installers, shells and packages that are not installed.
- **No setting is changed.**
  - A tap is refused when the target is a checkable control (Switch, CheckBox, Toggle,
    Radio and similar), when a toggle's bounds contain the tap point, or when the smallest
    clickable element that receives the tap contains a toggle (a Settings row whose whole
    surface flips its switch).
  - Labels like install, reset, erase, allow, enable, disable and sign out are refused.
  - `set_text` is refused inside Settings and SystemUI.
  - There is no shell, settings or clipboard verb.
  - Offline tests: `python3 -m unittest discover -s services/phone-queue/tests`.
- **Typing goes through accessibility only.** That means `set_text`, with no IME and no
  keyevents.
- **Every screen read is redacted.** The tool layer and the oracle use
  `phone-screen-safe`'s `redact_xml` / `sensitive_package`, so a sensitive app gives an
  empty tree.
- **UI lock.** The runner holds the host flock `/tmp/<dev>-ui.lock` for the whole UI phase.
  It is shared with `tern-queue-loop@s22`, `phone-worker ui` and the overnight drivers, so
  they coexist. The MCP server refuses to start unless an ancestor holds the lock
  (`burst.require_ui_lock`).
- **Gates.** These come from phone-worker's `gate()`: the S25 switch
  (`~/.local/state/s25-worker-off`, `S25_UNTIL`), call state and owner idle. They are
  checked three times: at k8s-Job creation, in the pod, and again under the lock, together
  with the ChatGPT driver's `owner_busy`. S25 jobs stay `blocked` with the gate reason until
  the gate opens.
- **Foreground restore.** The runner records the foreground app and restores it after
  every job (launchers via Home), the same way `phone-worker ui` does it.
- ChatGPT jobs only use the ordinary Chat composer ("Ask ChatGPT"). They never use
  Work/Codex cloud.

## Operate

```
# deploy / update (from a .files checkout on groot)
services/phone-queue/render-configmap            # regenerate 60-phone-queue-code.yaml
scripts/setup-k3s.sh check                       # parse, configmap freshness, server dry-run
kubectl apply -f config/k3s/manifests/00-namespaces.yaml -f config/k3s/kueue/phones.yaml \
              -f config/k3s/manifests/60-phone-queue-code.yaml -f config/k3s/manifests/60-phone-queue.yaml
services/phone-queue/advertise-phones            # after a node re-registration (healthz says so)
kubectl -n phones rollout restart deploy/phone-queue   # server/shim code; Job pods read the ConfigMap fresh
install -m0755 services/phone-queue/phoneq ~/.local/bin/phoneq
kubectl get all -n phones; kubectl get workloads -n phones; kubectl get clusterqueue phones
```

State, transcripts and receipts live under `/mnt/zer0models/phone-queue/` on groot (a
hostPath).

## Known limits

- fx is driven through the shim's Vercel-gateway protocol emulation (AI SDK v3 stream parts).
  If a later fx changes that protocol, goal jobs fail with `fx exit ...`; chat/script jobs
  are unaffected.
- The DeepSeek script harness has no reply harvester (launch receipt only).
- ChatGPT reply harvest reads the rendered text after the tagged bubble. When a long reply
  pushes that bubble off screen after scroll-to-bottom, `chat.reply` is null: the send
  receipt still stands, and the conversation is in the ChatGPT app.
