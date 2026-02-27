# evercore (Standalone)

A fully standalone, generic engine for:
- ticket lifecycle management
- task orchestration and dependency handling
- worker claiming/execution loops
- workflow definitions via YAML
- pluggable task executors (including `lemlem`)

This codebase is intentionally separate from Evergreen app internals.
It does not import `backend/`, `workers/`, or `libs/shared`.

## LLM Layer (lemlem)

Evercore uses [lemlem](https://github.com/danduma/lemlem) for model routing and LLM calls.

`lemlem` supports two model/preset configuration sources:
- YAML/JSON file (for example via `LEMLEM_MODELS_CONFIG_PATH`)
- database-backed model config service (dynamic runtime loading)

## Why this is separate
- Independent `pyproject.toml`
- Independent models/storage/services/API
- Independent worker loop and executor registry
- No runtime dependency on Evergreen backend schemas

## Quick start

1. Configure environment:
```bash
cp .env.example .env 2>/dev/null || true
export EVERCORE_DATABASE_URL="sqlite:///./evercore.db"
export EVERCORE_WORKFLOW_DIR="./workflows"
export EVERCORE_DEFAULT_WORKFLOW_KEY="default_ticket"
```

2. Configure lemlem models:
```bash
export LEMLEM_MODELS_CONFIG_PATH="/abs/path/to/models_config.yaml"
```

Or configure a database-backed model config source for dynamic model/preset updates.

3. Install and run API:
```bash
uv sync --project evercore
uv run --project evercore evercore-api
```

4. Run worker in a second terminal:
```bash
uv run --project evercore evercore-worker
```

5. Create a ticket:
```bash
curl -s -X POST http://localhost:8010/tickets \
  -H 'content-type: application/json' \
  -d '{"title":"Hello","workflow_key":"default_ticket"}'
```

6. Enqueue a lemlem task:
```bash
curl -s -X POST http://localhost:8010/tickets/<ticket_id>/tasks \
  -H 'content-type: application/json' \
  -d '{
    "task_key":"lemlem_prompt",
    "payload":{
      "model":"openrouter:gemini-2.5-flash",
      "prompt":"Write a short test summary for this ticket"
    }
  }'
```

## Tests (evercore library only)

Run the full standalone Evercore library suite:

```bash
uv run --project libs/evercore evercore-test
```

Run a subset by pattern:

```bash
uv run --project libs/evercore evercore-test --pattern "test_worker*.py"
```

## Extending for a new project
1. Add a workflow YAML in `workflows/`
2. Define your own task keys in your app layer
3. Register custom executors in `evercore/executors/registry.py`
4. Create tickets/tasks through the API

## Notes
- All datetimes are timezone-aware using `pytz.UTC`.
- No DB enums are used (plain text states for flexibility).
