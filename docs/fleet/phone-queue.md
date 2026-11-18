# Phone queue (k3s, groot): one front door for the S22+ and S25 Ultra

Agents that want to use a phone send a job to one service, and that service does the rest:
it waits for a free phone, checks whether the owner allows it, runs the UI scripting and the
Luna agent loop, and writes a receipt. Two agents never drive the same phone at once. k3s
(Kueue) does the queueing.

- **Endpoint:** `http://100.113.138.100:8792`. groot `:8790` is taken by garden_room, so
  this service uses 8792. Both groot loopback and the tailnet IP listen.
- **CLI:** `phoneq` (in `~/.local/bin` on groot and mbp). Override the endpoint with
  `$PHONEQ_URL`.
- **Auth:** submit and cancel need `Authorization: Bearer <token>` (see [Auth](#auth)).
  `phoneq` reads `$PHONEQ_TOKEN` or `~/.config/phoneq/token`.
- **Code:** `services/phone-queue/`.
- **Manifests:** `config/k3s/manifests/60-phone-queue*.yaml`, plus the Kueue objects in
  `config/k3s/kueue/phones.yaml`.

## API

| Call | Result |
|---|---|
| `POST /v1/jobs` | `202 {id, state}`. A replay with the same `submitter`+`idempotency_key` and the same body returns `200` with the existing id (`idempotent_replay: true`); the same key with a different body is `409`. |
| `GET /v1/jobs/{id}` | `{id, kind, device, state, submitter, model, created_at, started_at, finished_at, result?, error?}` |
| `GET /v1/jobs?submitter=&state=&device=&limit=` | `{jobs: [...]}`, newest first |
| `POST /v1/jobs/{id}/cancel` | Body `{submitter}`. Only the job's own submitter (same token principal) or an admin token may cancel (`403` otherwise). Deletes the k8s Job; a running runner gets SIGTERM and still restores the foreground app and releases both locks. |
| `GET /v1/devices` | Per phone: `{id, serial, online, gate:{allowed, reason}, lock_holder?, foreground?, battery?, queue_depth}` |
| `GET /healthz` | Status of the DB, k8s, `z0.dev/phone` capacity and the model shim |

Without a valid token, `GET` still works (Dash's read-only queue view uses it) but a job's
`result` is cut to `{steps, oracle_pass, ms, cold_ms, error_code, device, attempt}` and the
job carries `result_redacted: true`: no screen text, reply or transcript path. `error` is
shown only when the service itself wrote it (gate, UI lock, pacing, infra, model,
cancellation); anything else, such as fx agent output or a pod log tail, becomes
`"<error_code> (details need a token)"`. `info` is likewise cut to Kueue/k8s status.

**Job body:**

```
{kind: "chat"|"goal", device: "s22"|"s25"|"any", submitter,
 app?, prompt? (chat; optional typed-by-reference attachment for goal), goal? (goal),
 model? (default openai-codex/gpt-6-luna),
 harness? ("script" for chat, "fx" for goal),
 max_steps?, idempotency_key?, priority?, reset?: "home"|"none",
 oracle?: {type: "tree_text", must_contain?, must_not_contain?, final_must_contain?, package?}}
```

**States:** `queued` → `admitted` (Kueue reserved the phone) → `running` → `succeeded` |
`failed` | `cancelled`.

**`blocked`** means one of these is closed: the phone's gate, the ChatGPT quota pause or
pace budget, a UI lock, or infrastructure (`infra: ...`: the model shim or a model backend
is down or groot lacks memory to load the model). The job is retried every 30 s.
- A closed **gate** (S25 switch off, owner using the phone, a call) never fails a job: it
  stays `blocked` until the gate opens or the submitter cancels it. This holds for gate
  checks in the front door, in the pod and under the lock.
- Every **other** block (UI lock busy 900 s, pace budget, infra) counts as an attempt; after
  50 counted attempts the job is `failed` (`error_code` `infra_unavailable` for infra,
  otherwise the last block reason in `error`).
- Pacing never burns a ChatGPT send slot on a blocked attempt: the runner waits for budget
  without reserving it (pace.py in peek mode), and reserves the slot only after it holds both
  UI locks and the gate/owner re-check passed. Goals aimed at the ChatGPT/DeepSeek apps
  reserve a slot too (they may send).

**What `succeeded` means.**
- goal / fx jobs: fx finished and the oracle (if any) passed. An fx **chat** also needs a
  non-empty reply in `final_output` (else `reply_not_harvested`).
- ChatGPT chat (script): the message was sent AND a finished reply was harvested; it is in
  `final_output` and `result.chat.reply`. Sent but no reply is `failed` with
  `error_code` `reply_timeout` (still generating after 240 s) or `reply_not_harvested`.
  A reply is finished when ChatGPT shows its Copy button, or (for a reply taller than the
  screen, whose Copy button is below the fold) when no Stop button is shown and the reply
  text is unchanged over three polls (~6 s; `chat.finished_by: stable_text`);
  `result.chat.send_status` stays `sent`, so do **not** resend.
- DeepSeek chat (script): dispatch only (no harvester exists): sent and verified, with
  `chat.reply_harvested: false` and `final_output` saying so.
- Other `error_code`s: `model_unavailable`, `infra_unavailable`, `send_failed`,
  `rate_limited`, `step_limit` (fx hit `max_steps`).

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
   preflight -> gate -> pace -> flock ~/tmp/<dev>-ui.lock + /tmp/<dev>-ui.lock -> re-gate
   -> record foreground
   -> harness -> oracle on a fresh hierarchy -> restore foreground -> result.json
```

**Kueue design.** groot advertises the extended resource `z0.dev/phone = 2` by running
`services/phone-queue/advertise-phones`, which is the documented node-status patch
(`scripts/setup-k3s.sh apply` runs it). Every phone Job requests `z0.dev/phone: 1`. Its
`activeDeadlineSeconds` is the sum of the runner's phase bounds (lock 900 + pace 600 +
reply 240 + fx 900 + 360 slack = 3000 s), so a job that legitimately waits out every phase
is never killed by its deadline.

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
- **Pacing applies to every harness.** Any chat job (script or fx) and any goal with
  `app: chatgpt|deepseek` takes a `pace.py` send slot and honours the shared quota pauses
  before it takes the phone. After an fx chat the runner stamps
  `/tmp/chatgpt-last-dispatch-<dev>`, checks the screen for the driver's rate-limit words
  (same 3 h pause) and logs to `dispatches.jsonl`.
- **goal (and chat with harness=fx).** Runs vercel-labs fx with
  `fx ask --json --no-save --auto --model <id>`. Each job gets its own HOME
  (`<job>/fxhome`, `~/.fx` 0700) and `FX_MAX_AGENT_STEPS=max_steps`.
  - `FX_GATEWAY_BASE_URL` and `FX_GATEWAY_CHAT_URL` point fx at the model shim. The bearer
    is `phoneq-job-<id>-<attempt>.<hmac>` (HMAC-SHA256 with `shim-key`), valid only while
    that attempt runs; the shim writes the per-job `model.jsonl`.
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
  - Availability preflight: `GET 127.0.0.1:8795/phoneq/available?model=`: `200` routable,
    `404` `model_unavailable` (fails the job without a phone slot), `503` `infra_unavailable`
    (backend down, or not enough memory: blocks and retries). The front door runs it before
    creating each k8s Job, the runner again in the pod.
  - Memory guard: an `ollama/*` model that is not already resident is loaded only when
    groot's `MemAvailable` covers its size plus 3 GiB (`PHONEQ_MEM_HEADROOM_MB`). A load on
    a memory-starved groot once triggered a global OOM. The llama router manages its own
    loads and is not guarded here.
- **Oracle.** `tree_text`, case-insensitive substrings, run after the harness on a fresh
  redacted hierarchy (`text` and `content-desc`), independent of the agent's own "done":
  - `must_contain`: on the screen for goals; for **chat** jobs, in the reply only (the screen
    also shows our own prompt bubble, so a string from the prompt would pass trivially);
  - `must_not_contain`: nowhere on the screen or in `final_output`;
  - `final_must_contain`: in `final_output`, i.e. the value the agent reported (a label on
    screen proves the page, not the answer; use both);
  - `package`: the foreground package at the end.
  If the oracle fails, the job is `failed`.

## Phone safety (enforced in code)

- **Nothing is ever installed, uninstalled or reset.** `adbutils` install/uninstall, u2
  `_setup_ime`, `send_keys`, `app_install`/`app_uninstall`/`app_clear` and the IME setters
  are patched to raise in every process (the `ds_burst` rule). `launch` refuses stores,
  installers, shells and packages that are not installed.
- **No setting is changed.** Every tap is judged by the element that receives it (the
  smallest clickable node under the point) and that element's own label (its subtree's text
  and content-desc; Settings rows are text-less clickable layouts around a title).
  - Anywhere: toggles (Switch, CheckBox, Toggle, Radio and similar; a toggle under the point;
    a toggle inside the receiving row), sliders (SeekBar/Slider), anything in System UI
    (status bar, quick settings, notifications), and labels matching install, uninstall,
    reset, erase, delete, remove, turn on/off, power off, restart, reboot, start now, allow,
    grant, enable, disable, sign out, pay, buy, subscribe and similar are refused.
  - **Settings screens are navigation only** (`phone_tools.settings_context`: Settings,
    Device care, System UI, and DeX/desktop-mode panels, which One UI serves from the
    launcher/dexservice). Allowed: the Navigate up / Back / Search chrome, and list rows that
    are not buttons, contain no button and whose title does not start with an action verb
    (start, connect, scan, download, update, apply, OK, done, add, set, ...). Refused: every
    button (Apply, OK, Done, Start now, Connect, ...), action rows ("Connect wirelessly",
    "Download and install"), unlabelled controls, and every tap while a dialog is open.
  - Swipes whose finger path crosses a slider are refused everywhere; sideways swipes are
    refused on settings screens.
  - `set_text` is refused on settings screens.
  - There is no shell, settings or clipboard verb. The system prompt is not a safety layer.
  - Offline tests: `python3 -m unittest discover -s services/phone-queue/tests`
    (`test_round3.SettingsTapGuard` replays the review's button list and real row shapes).
- **Typing goes through accessibility only.** That means `set_text`, with no IME and no
  keyevents, up to 20000 chars. `set_text(from_job_prompt=true)` types the job's own
  `prompt` exactly as submitted (chat prompt, or a goal's optional `prompt` attachment), so
  a model never recopies long frozen text.
- **Every screen read is redacted.** The tool layer and the oracle use
  `phone-screen-safe`'s `redact_xml` / `sensitive_package`, so a sensitive app gives an
  empty tree. One narrow exception: in Settings, the value of a row titled Build number,
  Baseband/Kernel/Software/Service provider software version, One UI/Android version and
  similar public firmware ids is restored when the high-entropy rule was its only hit
  (`phone_tools.restore_firmware_ids`). IMEI, serial, phone number and every other value
  stay redacted.
- **UI locks.** The runner holds both host flocks for the whole UI phase, in
  `tern-01/launch_queue.py`'s order: `~/tmp/<dev>-ui.lock` (held by Dash e2e/native test
  workers while they drive the screen) then `/tmp/<dev>-ui.lock` (shared with
  `tern-queue-loop@s22`, `phone-worker ui` and the overnight drivers). Both waits share one
  900 s bound. `/v1/devices` `lock_holder` names whichever is held (`lock` = its path). The
  MCP server refuses to start unless an ancestor holds the lock (`burst.require_ui_lock`).
- **Gates.** These come from phone-worker's `gate()`: the S25 switch
  (`~/.local/state/s25-worker-off`, `S25_UNTIL`), call state and owner idle. They are
  checked three times: at k8s-Job creation, in the pod, and again under the lock, together
  with the ChatGPT driver's `owner_busy`. S25 jobs stay `blocked` with the gate reason until
  the gate opens.
- **Foreground restore.** The runner records the foreground app and restores it after
  every job (launchers via Home), the same way `phone-worker ui` does it.
- ChatGPT jobs only use the ordinary Chat composer ("Ask ChatGPT"). They never use
  Work/Codex cloud.

## Auth

The API is on the tailnet IP, so writes are authenticated:

- `services/phone-queue/issue-tokens --ensure` (run by `scripts/setup-k3s.sh apply`) creates
  Secret `phones/phone-queue-auth`: `tokens.json` maps the sha256 of each bearer token to
  `{principal, admin}`, and `shim-key` signs per-job model-shim tokens. Plain tokens are
  written once, 0600: `~/.config/phoneq/token` (principal `agents`, for every local agent)
  and `~/.config/phoneq/admin-token` (principal `owner`, admin). Nothing is in git.
- Copy `~/.config/phoneq/token` (0600) to each host that submits jobs. Raw HTTP clients send
  `Authorization: Bearer $(cat ~/.config/phoneq/token)`.
- More principals: `issue-tokens add NAME [--admin]`; `issue-tokens revoke NAME`. The API
  rereads `tokens.json` when kubelet syncs the Secret (about a minute).
- Without the Secret the API refuses every write (`503`) and the shim every model call
  (fail closed).
- The model shim (`127.0.0.1:8795`) answers model calls only for a valid, still-running job
  attempt, so it is not an open proxy to the ChatGPT subscription for other processes on
  groot. Its `GET`s (catalog, preflight, health) spend nothing upstream and stay open.
- Residual trust: anyone who can read `~/.config/phoneq/token` (kvn on groot or mbp) or run
  `kubectl` against the cluster can queue jobs; the token principal `agents` is shared, so
  cancel additionally checks `submitter`.

## Operate

```
# deploy / update (from a .files checkout on groot)
services/phone-queue/render-configmap            # regenerate 60-phone-queue-code.yaml
scripts/setup-k3s.sh check                       # parse, configmap freshness, server dry-run
kubectl apply -f config/k3s/manifests/00-namespaces.yaml -f config/k3s/kueue/phones.yaml \
              -f config/k3s/manifests/60-phone-queue-code.yaml -f config/k3s/manifests/60-phone-queue.yaml
services/phone-queue/advertise-phones            # after a node re-registration (apply runs it too)
services/phone-queue/issue-tokens --ensure       # auth Secret + ~/.config/phoneq tokens (apply runs it too)
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
- The DeepSeek script harness has no reply harvester (dispatch only; stated in the result).
- While a ChatGPT job waits for a `pace.py` slot it holds that phone's Kueue slot (not the
  UI locks).
- ChatGPT reply harvest reads the rendered text after the tagged bubble. When a long reply
  pushes that bubble off screen after scroll-to-bottom, the job fails with
  `reply_not_harvested`: the send receipt still stands, and the conversation is in the
  ChatGPT app.
- API and shim run in one Guaranteed-QoS pod (requests = limits), the OOM killer's last
  choice, and exit on SIGTERM (a rollout is about 3 s of downtime). Runner pods stay
  burstable.
