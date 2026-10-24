# Proposal: scoped credentials for Boat harness workers

Status: **For Kevin's approval. No keys were created.** The current fleet adapter
runs public verification without model credentials. Its secret allowlist remains
empty. Do not put keys into `--src`, `--input`, arguments, logs or fetched outputs.

## Minimum credentials

Approve only the provider needed for a selected harness job. Do not provision all
providers by default. Suggested initial authorization: one OpenRouter project
key, one approved model, $2 daily spend and $10 total spend, expiring October 30.
The limits below are proposals, not claims of provider-supported controls.

| Harness route | Dedicated credential | Required restrictions |
| --- | --- | --- |
| pi/omp/fx through OpenRouter | Separate Boat-only API key | Credit limit, approved model list where supported, no account administration, trial-end revocation |
| Direct Anthropic | Separate workspace inference key | Workspace spend/rate limits, no admin key, model access restricted where supported |
| Direct OpenAI | Separate project service-account key | Restricted inference endpoint permissions, model restrictions, project budget/rate limits |
| Direct Gemini | Separate project API key | Restrict to the Generative Language API, low quotas, billing budget alerts, no service-account admin credentials |
| Direct Groq, Cerebras or other provider | Separate inference-only project key | Lowest usable quota, fixed approved model, no administrative privileges |

A provider budget alert is not a hard spend cap. If the provider lacks enforceable
per-key limits or expiration, Kevin must approve that limitation explicitly.
Use a controller-enforced request/token cap and revoke the key at expiry.
Never copy desktop subscription OAuth sessions, personal API keys, GitHub tokens,
BWS access tokens, the Boat account key or production credentials into a VM.
Public repositories need no GitHub credential. A later authenticated read-only
checkout requires a separate proposal and explicit repository scope.

## Approved delivery flow

1. Kevin chooses one provider, model, spend cap, expiry and reviewed harness revision.
2. Kevin creates the dedicated inference key in that provider's console.
3. Store the key in BWS under a new Boat-specific secret name and UUID.
4. Review the UUID-to-name allowlist change separately. Keep all unrelated names denied.
5. The trusted host obtains only that secret through its existing BWS flow.
6. Use `omp-boat run --secret NAME JOB -- COMMAND` after the harness job is reviewed.
7. The existing lease disables snapshots, monitoring and inherited environment.
8. The host encrypts the selected secret to a fresh per-VM age public key.
9. The guest decrypts it into a 0600 tmpfs file for one unprivileged process.
10. The process reads the file directly. It must not export the key or log it.
11. Suppress secret-job output. Return only reviewed, credential-free result metadata.
12. Remove tmpfs material and delete the VM on completion or error. Revoke at expiry.

The current `fleet-build --node boat` path deliberately does not accept `--secret`.
Do not combine its general source/output transfer path with real credentials.
A harness-specific integration requires review of the CLI's credential-file support
and output handling first. Most CLIs expect environment keys. Do not weaken the
file-only policy to make those CLIs work. Use a reviewed file-reading inference
adapter or a dedicated provider client with native credential-file support.

Provider or guest root can read live RAM. Encryption does not protect a running
key against the cloud operator or a compromised guest. Use only reviewed public
code with an approved dedicated key. Never pair unreviewed PR code with secrets.

The same 3-hour rolling-24h compute guard, 90,000-second total trial cap, provider
concurrency limit and 600-second lease apply. No approval in this proposal changes
billing, creates credentials, or enrolls secrets automatically.
