# Evercore: Orchestration Engine for AI Agents and Complex Workflows

[Python](https://www.python.org/downloads/)
[License](https://opensource.org/licenses/AGPL)

📢 [[Basic Local Deployment](../../examples/01-basic-local)] [[External Postgres Deployment](../../examples/02-external-postgres)] [[Production VPS Deployment](../../examples/03-production-vps)]

**Evercore** is an orchestration engine for managing long-running LLM agents.

It makes it super easy to define an agent as a combination of prompt, memory and tools and it manages ticket lifecycles, task dependencies, and distributed worker loops for you.

By decoupling state management and declarative YAML workflows from your core application logic, Evercore provides a robust, pluggable foundation that simplifies the development and scaling of asynchronous, multi-agent systems.

## How does it compare to useWorkflow, Temporal, Prefect


| Area                   | `evercore`                                                                      | [Temporal](https://temporal.io/)                                    | [UseWorkflow.dev](https://useworkflow.dev)                  | [Prefect](https://www.prefect.io/)                             |
| ---------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Main value             | Embed a workflow engine directly in your app with minimal infrastructure        | Maximum durability and correctness for long-running workflows       | Durable TypeScript workflows with agent-friendly DX         | Fast path to production orchestration for Python/data teams    |
| Workflow functionality | Tickets/tasks, stage transitions, approvals, pause/resume, retries, event inbox | Full workflow model with signals, queries, updates, child workflows | Durable function-style workflows with resume/event patterns | Flows/tasks, retries, state tracking, deployments, automations |
| Scheduling             | Built-in interval/one-shot schedule runner                                      | First-class schedules with advanced policies                        | Code-level timing/sleep primitives                          | Strong deployment scheduling and automation features           |
| Operational complexity | Lowest: lightweight and app-embedded                                            | Highest: most powerful, more platform overhead                      | Medium: modern and fast-moving ecosystem                    | Medium: managed experience with solid operational tooling      |

Evercore is: embeddable, lightweight, fully python and comes with batteries included for AI agent flows.


## Quick start

1. Configure environment:

```bash
cp .env.example .env 2>/dev/null || true
export EVERCORE_DATABASE_URL="sqlite:///./evercore.db"
export EVERCORE_WORKFLOW_DIR="./workflows"
export EVERCORE_DEFAULT_WORKFLOW_KEY="default_ticket"
```

1. Configure lemlem models:

```bash
export LEMLEM_MODELS_CONFIG_PATH="/abs/path/to/models_config.yaml"
```

Or configure a database-backed model config source for dynamic model/preset updates.

1. Install and run API:

```bash
uv sync --project evercore
uv run --project evercore evercore-api
```

1. Run worker in a second terminal:

```bash
uv run --project evercore evercore-worker
```

1. Create a ticket:

```bash
curl -s -X POST http://localhost:8010/tickets \
  -H 'content-type: application/json' \
  -d '{"title":"Hello","workflow_key":"default_ticket"}'
```

1. Enqueue a lemlem task:

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

## LLM Layer (lemlem)

Evercore uses [lemlem](https://github.com/danduma/lemlem) for model routing and LLM calls.

`lemlem` supports two model/preset configuration sources:

- YAML/JSON file (for example via `LEMLEM_MODELS_CONFIG_PATH`)
- database-backed model config service (dynamic runtime loading)

