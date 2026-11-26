# android-u2-driver-models-v0 runner

This suite measures how well LLMs and local SLMs drive the S22+ through uiautomator2. It goes through the phone queue: the runner sends `goal` jobs to the phone-queue API and does not touch the phone UI itself. The queue service owns the UI flock, the owner-activity gate, uiautomator2 (with installs and the IME patched off), the driver harness and the oracle check. The results feed the z0evals study `studies/android-u2-driver-models-v0`.

| File | What it is |
|---|---|
| `tasks.json` | 18 read-only goals on the S22+ (15 multi-step). Each has an independent `tree_text` oracle, `reset: "home"` and `consequential: false`. |
| `models.json` | The models in the matrix, the exact `model` string each job sends, and an availability probe. |
| `run_suite.py` | `plan`, `probe` and `run`. It sends one job per model × task × rep and writes `rows.jsonl`. |
| `summarize.py` | Turns `rows.jsonl` into `summary.json`: per-model rates, latency and a task matrix. |
| `check_oracles.py` | Checks every oracle against redacted hierarchy dumps. An oracle must pass on its evidence screen and fail on the home screen. |
| `oracle-check-20261028.json` | Result of that check: 18/18 verified on 37 redacted S22+ screens. |
| `tests/test_runner.py` | Offline test of the contract. The real runner and summarizer run against a fake API. |

## Running it (on groot)

```sh
cd services/phone-queue/evals
export PHONEQ_URL=http://100.113.138.100:<port>   # default :8790; check the ledger for the real port
./run_suite.py probe                               # queue health, devices, model availability
./run_suite.py plan --reps 3                       # 11 default models x 18 tasks x 3 = 594 jobs
./run_suite.py run --out /mnt/zer0models/tmp/phoneq-evals/run1 --reps 3
./summarize.py /mnt/zer0models/tmp/phoneq-evals/run1/rows.jsonl --out /mnt/zer0models/tmp/phoneq-evals/run1/summary.json
python3 -m unittest discover -s tests
```

- **Order:** jobs run one at a time, model-major. Each model's first job pays its cold load and the jobs after it run warm.
- **Resume:** a rerun skips rows whose status is already `ok` or `unavailable`. Every job carries `idempotency_key = suite:run_id:model:task:rep`.
- **Settings check:** before and after each job the runner takes a read-only `adb shell settings list system|secure|global` snapshot. Keys that change on their own are ignored. This includes `secure/accessibility_enabled`, which flipped during a 45 s idle sample because UiAutomation sessions toggle it. If a non-volatile setting changed, the row gets `side_effect_keys`, the run stops (`--continue-on-side-effect` overrides this) and the change is reported, not reverted. Reverting would itself be changing a phone setting.

## Row statuses

These are kept apart, and only `ok` rows are scored:

| Status | Meaning |
|---|---|
| `ok` | The driver ran and the oracle decided the outcome. |
| `unavailable` | The preflight probe failed, or the job failed with an auth, unknown-model or connection error. |
| `timeout` | The runner timed out waiting and cancelled the job, or the job timed out before any step. |
| `blocked` | The device gate refused the job. |
| `cancelled` | The job was cancelled. |
| `error` | Anything else. |

A model with no scored rows is reported as `unavailable` or `no_scored_rows` with null metrics, never as 0.

## Metrics

These follow z0evals research-focus item 5 and the per-model rows of PR #103.

- **Oracle success:** the share of scored rows where `result.oracle_pass` is true, with a Wilson 95% CI. The oracle is checked by the queue against the final hierarchy. It is not the driver's own "done".
- **Steps:** the median steps, and step efficiency, which is steps ÷ `min_steps_from_home` on successful rows.
- **Wrong act:** a false done (the job succeeded but the oracle failed and the driver did not abstain), or a settings side effect.
- **Abstain:** the final output contains `ABSTAIN` (the safety suffix asks for this when the driver is unsure), or the job error is abstained, needs_confirmation, uncertain or escalated.
- **Choose latency p50/p95:** per decision, pooled over steps. It comes from `transcript_path` when the transcript records `choose_ms`, `decision_ms`, `llm_ms` or `model_ms` per step.
- **Total ms:** `result.ms`, warm rows only.
- **Cold load:** `cold_ms` is reported separately. For groot-router models, the runner also sets `cold_expected` when the router showed the model unloaded before its first job.
- **Tokens and cost:** `tokens_in`, `tokens_out` and `cost_usd` when the queue reports them. Codex-subscription models have no per-token price, and Luna/Terra are on a free promo per the owner.

## Models (`models.json`)

| Group | Models |
|---|---|
| LLM, `openai-codex/*` through the queue's fx harness | `gpt-6-luna` (default driver), `gpt-6.1-terra`, `gpt-6.1-sol` (ceiling) |
| SLM, groot router `:11530` | `qwen3-0.6b-q8`, `qwen3-1.7b-q4km`, `qwen3-4b-q4km`, `qwen3-8b-q4km`, `qwen3-14b-q4km`, `nemotron-orchestrator-8b-q4km` |
| SLM, groot ollama `:11434` | `qwen2.5vl:3b`, `qwen3:4b-instruct-2507-q4_K_M` |
| Gateway small model (`gateway/meta/llama-3.1-8b`) | Off by default: there is no `AI_GATEWAY_API_KEY` on groot or mbp, and fx gateway auth is expired. Pass `--models gateway-small` once a key exists. |

**Open contract question:** fx's providers are gateway, codex and grok only. So `groot-router/*` and `ollama/*` need the queue to either point fx at an OpenAI-compatible base URL or run them through `harness: "script"`. The ledger has a NOTE asking the queue owner. Until it is answered, those jobs are expected to come back as `unavailable`, and they are recorded that way.

## Task safety

The tasks were derived on 2026-10-28 from read-only, redacted (`phone-screen-safe dump`) hierarchy dumps of the S22+:
- every dump was taken under `/tmp/s22-ui.lock` with the owner idle;
- only intents and taps on navigation labels were used;
- the foreground app (DeepSeek) was restored afterwards.

`tasks.json` lists what was left out and why: there is no calculator app, World clock fails closed in the redactor, alarm labels are personal, the Display/Sounds/Battery/Device care pages have one-tap setting changes, and some pages show PII. `toggle_risk` marks the goals whose arrival screen has switches; the settings check covers them. No raw dumps are committed.
