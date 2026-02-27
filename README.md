# evergreen-core (Standalone)

A fully standalone, generic engine for:
- ticket lifecycle management
- task orchestration and dependency handling
- worker claiming/execution loops
- workflow definitions via YAML
- pluggable task executors (including `lemlem`)

This codebase is intentionally separate from Evergreen app internals.
It does not import `backend/`, `workers/`, or `libs/shared`.

## Why this is separate
- Independent `pyproject.toml`
- Independent models/storage/services/API
- Independent worker loop and executor registry
- No runtime dependency on Evergreen backend schemas

## Quick start

1. Configure environment:
```bash
cp .env.example .env 2>/dev/null || true
export EVERGREEN_CORE_DATABASE_URL="sqlite:///./evergreen_core.db"
export EVERGREEN_CORE_WORKFLOW_DIR="./workflows"
export EVERGREEN_CORE_DEFAULT_WORKFLOW_KEY="default_ticket"
```

2. Configure lemlem models:
```bash
export LEMLEM_MODELS_CONFIG_PATH="/abs/path/to/models_config.yaml"
```

3. Install and run API:
```bash
uv sync --project evergreen-core
uv run --project evergreen-core evergreen-core-api
```

4. Run worker in a second terminal:
```bash
uv run --project evergreen-core evergreen-core-worker
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

## Extending for a new project
1. Add a workflow YAML in `workflows/`
2. Define your own task keys in your app layer
3. Register custom executors in `evergreen_core/executors/registry.py`
4. Create tickets/tasks through the API

## Notes
- All datetimes are timezone-aware using `pytz.UTC`.
- No DB enums are used (plain text states for flexibility).
