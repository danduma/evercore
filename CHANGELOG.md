# Evercore Changelog

This changelog tracks **library-level** behavior changes in `evercore` and how to adopt them in apps that depend on it.

## 2026-03-04

### Added
- Worker-level hard execution timeout enforcement in `WorkerService`.
  - File: `src/evercore/services/worker_service.py`
  - Executor calls are now wrapped with a timeout guard and will fail fast instead of hanging indefinitely.
- Timeout recovery hook for app-specific fallback policy.
  - `WorkerService(..., timeout_recovery_handler=...)`
  - Signature:
    - `(ticket, task, executor, timeout_seconds) -> ExecutionResult | None`
  - Returning `ExecutionResult` lets the worker complete a timed-out task via app policy instead of retrying/dead-lettering immediately.
- New default timeout setting:
  - `default_task_timeout_seconds` in `src/evercore/settings.py`
  - Environment variable: `EVERCORE_DEFAULT_TASK_TIMEOUT_SECONDS`
  - Default value: `300`
- Additional task log entries:
  - `task claimed by worker`
  - `task execution timed out after <N>s`
- Test coverage for timeout behavior:
  - `tests/test_worker_service.py`
  - Covers both explicit per-task timeout and default timeout fallback.

### Changed
- Effective timeout resolution now uses:
  1. `task.timeout_seconds` (if set)
  2. `settings.default_task_timeout_seconds`
- Timeout-triggered failures flow through normal retry/dead-letter policy.

### Why this matters
- Prevents workers from getting stuck forever on long-running executor calls.
- Makes timeout behavior consistent across all client apps using `evercore`.
- Improves observability with explicit timeout/claim logs.

### How to use in dependent projects
1. Update your project to this `evercore` version/commit.
2. Optionally set `EVERCORE_DEFAULT_TASK_TIMEOUT_SECONDS` for your environment.
3. Keep task-level overrides (`timeout_seconds`) for workflows that need custom limits.
4. For stage-specific timeout fallback logic, pass `timeout_recovery_handler` when constructing `WorkerService`.
5. Check task logs for new timeout and claim entries when debugging.
6. Keep domain-specific fallback behavior in the client app (for example, a stage-specific fallback response), while relying on `evercore` for generic timeout/retry control.

### Agent rollout notes
- If a downstream app already has app-level timeout wrappers, keep them only for stage/domain fallback policy.
- Do not duplicate generic timeout orchestration in app code unless the app has a special requirement.

## Template for future entries

```md
## YYYY-MM-DD
### Added
- ...

### Changed
- ...

### Fixed
- ...

### How to use in dependent projects
1. ...
2. ...
```
