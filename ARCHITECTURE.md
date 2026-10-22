# J Regulator — Architecture and Implementation Status

## Product vision

J Regulator is intended to be a provider-neutral service and CLI between AI
applications and model providers. It selects models by capability and policy, performs
bounded retries and automatic failover, and records why routes were selected. Its
continuity layer is intended to preserve explicit task state, checkpoints, and verified
tool outcomes so work can recover safely after interruptions. It cannot transfer a
model's hidden reasoning; a replacement model must use application state that was
explicitly saved and checked.

All executable provider integrations in this repository are mocks. Real provider
integrations remain deferred until mock routing and recovery foundations are reliable.

## Current implementation (Gate B)

- **CLI:** `jreg init`, `jreg status`, `jreg providers list`, `jreg models list`,
  `jreg models simulate`, and `jreg routing show`. The original flat
  `providers-list` and `models-list` commands remain as compatibility aliases.
- **Mock registry:** built-in OpenAI and Anthropic mock adapters and three in-code mock
  models. This is static demo data, not a persistent or configurable registry.
- **Routing:** filters disabled models and missing capabilities, then sorts by priority
  with stable input order for ties. It classifies quota, rate-limit, timeout, provider,
  and unexpected adapter errors. Retryable errors receive at most `max_retries`
  additional attempts per model (validated from 0 through 10). When enabled, fallback
  proceeds to later candidates. Missing adapters are recorded as skipped outcomes.
- **Attempt traces:** routing exposes each call/skip and its outcome. The existing task
  manager persists each observed model outcome, but only supports one request/response;
  it is not resumable task continuity.
- **Persistence:** SQLAlchemy table definitions and SQLite `create_all` initialization
  exist for tasks, attempts, and tool actions. There are no versioned migrations.
- **Verification:** Gate B routing, CLI, mock error, and attempt-recording tests are in
  `tests/`. Run the focused test commands and full suite listed in `PROGRESS.md`.

## Planned architecture (not implemented unless listed above)

- **Service/API:** a versioned FastAPI API for stable client integration and task
  management.
- **Registry/policy:** configurable applications, providers, models, capabilities,
  routing profiles, allowlists, health, budgets, and retry deadlines.
- **Adapters/failover:** provider-specific request/response normalization, shared
  cooldowns, circuit breaking, and policy-aware backoff. The current mock router does
  not implement these operational controls.
- **Continuity:** durable task checkpoints, context reconstruction, resumability, and
  safe reconciliation of uncertain tool side effects. These features are not present.
- **Operations/security:** migrations, authentication, secrets management, audit
  controls, observability, deployment, and backups.

## CLI reference

```text
jreg init
jreg status
jreg providers list
jreg models list
jreg models simulate [--failure success|quota_exhausted|rate_limit|timeout|error]
jreg routing show
```

Simulation injects the selected behavior into the highest-priority eligible mock model
and prints every attempt and the selected fallback. No credentials or network calls are
used. Task commands, an HTTP API, and real provider commands are deferred.

## Next milestone

Gate C should harden the durable task record path: introduce versioned migrations,
exercise persistence across process restarts, and keep attempt records consistent under
failure. Gate D should then add explicit checkpoints, resumption, and tool-action
reconciliation, with failure-injection tests proving confirmed side effects are not
replayed. Only after mock recovery works should real provider adapters be considered.
