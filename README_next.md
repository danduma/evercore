# Evercore

An orchestration engine for long-running AI agent workflows. Define agents, wire them into tasks, and let Evercore handle the rest: task dependencies, retries, pauses, approvals, distributed workers, and persistent state.

## The problem

A single agent call is easy. What breaks at scale:

- **Tasks depend on each other.** A writer agent needs the researcher to finish first. Coordinating this by hand is brittle.
- **Long-running work needs to survive failures.** A task that runs for 20 minutes can't just crash and disappear. You need retries, timeouts, and resumability.
- **Multiple workers need to coordinate.** When you scale to many concurrent agent tasks, you need distributed claiming, heartbeats, and dead-letter handling — not a cron job.

Evercore gives you all of this with minimal setup, embedded directly in your Python application.

## Quickstart: one agent, one task

```python
import os
from lemlem import Agent
import evercore

# Define the agent (what it is)
summarizer = Agent(
    system_prompt="You produce clear, concise technical summaries.",
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
)

# Wire it to a task key (what it does in a workflow)
@evercore.executor("summarize")
def summarize_task(ticket, task):
    session = summarizer.spawn(session_id=ticket.ticket_id)
    result = session.send(task.payload["text"])
    return evercore.ok(result.text)

# Run it
ticket = evercore.Ticket(
    title="Summarize release notes",
    tasks=[
        evercore.Task("summarize", payload={"text": open("CHANGELOG.md").read()}),
    ]
)

output = evercore.run(ticket)
print(output["summarize"].text)
```

`evercore.run()` is in-process — no server, no worker process, no setup. It runs tasks in dependency order and returns when they're all done.

## Multi-agent workflows

Tasks can depend on each other. Evercore executes them in the right order, passing outputs forward automatically.

```python
from lemlem import Agent
import evercore

researcher = Agent(
    system_prompt="You research topics and produce structured, citable summaries.",
    model="gemini-2.5-flash",
)

writer = Agent(
    system_prompt="You turn research notes into polished, well-structured articles.",
    model="gemini-2.5-flash",
)

@evercore.executor("research")
def research_task(ticket, task):
    session = researcher.spawn(session_id=ticket.ticket_id)
    result = session.send(task.payload["prompt"])
    return evercore.ok(result.text)

@evercore.executor("write")
def write_task(ticket, task):
    # The research output is available in task.upstream["research"]
    notes = task.upstream["research"].text
    session = writer.spawn(session_id=ticket.ticket_id)
    result = session.send(
        f"Write a 600-word article based on these research notes:\n\n{notes}"
    )
    return evercore.ok(result.text)

ticket = evercore.Ticket(
    title="Write article: The future of protein folding",
    tasks=[
        evercore.Task("research",
            prompt="Research recent breakthroughs in protein folding: AlphaFold, RoseTTAFold, practical applications."),
        evercore.Task("write",
            depends_on=["research"]),  # won't start until research completes
    ]
)

output = evercore.run(ticket)
print(output["write"].text)
```

## Agents with tools and skills

Agents bring their capabilities into executors. A DevOps agent with shell access and Git skills:

```python
from lemlem import Agent, Tool
from lemlem.skills import SkillRuntimeConfig, SkillRef
import subprocess

devops = Agent(
    system_prompt="You are a DevOps engineer. Diagnose and fix infrastructure issues.",
    model="gemini-2.5-flash",
    tools=[
        Tool("run_command", "Execute a shell command",
             params={"cmd": str},
             handler=lambda args: subprocess.check_output(args["cmd"], shell=True, text=True)),
    ],
    skills=SkillRuntimeConfig(
        skill_dirs=["/app/skills"],
        skills=[SkillRef(id="acme/git-tools")],
    ),
)

@evercore.executor("diagnose")
def diagnose(ticket, task):
    session = devops.spawn(session_id=ticket.ticket_id)
    result = session.send(task.payload["issue_description"])
    return evercore.ok(result.text, tool_calls=result.tool_calls)
```

## Production: distributed workers

For production use, run the Evercore API server and worker loop separately. Submit tickets from anywhere — a webhook, a cron job, another service.

```python
# worker.py — runs as a separate process, polls for work
import evercore

# Register all your executors
@evercore.executor("research")
def research_task(ticket, task): ...

@evercore.executor("write")
def write_task(ticket, task): ...

if __name__ == "__main__":
    evercore.Worker(
        database_url=os.getenv("DATABASE_URL"),
    ).run()  # polls DB, claims tasks, executes, retries on failure
```

```python
# submit.py — from a webhook handler, cron job, or other service
import evercore

client = evercore.Client("http://localhost:8010")

ticket = client.submit(
    title="Weekly digest: protein folding",
    tasks=[
        evercore.Task("research", prompt="Latest protein folding papers this week"),
        evercore.Task("write", depends_on=["research"]),
    ]
)

print(f"Submitted: {ticket.id} — check status at /tickets/{ticket.id}")
```

Start the infrastructure:

```bash
# Terminal 1: API server
evercore-api

# Terminal 2: Worker
evercore-worker
```

Workers handle: task claiming with distributed locking, heartbeats and stale task reaping, configurable retries with backoff, pause/resume, approval gates, and event-driven waiting.

## How it works

```
Agent (lemlem)         — defines what an agent is: prompt, model, tools, skills, memory
  └── AgentSession     — one live execution context for a specific ticket or conversation
        └── AgentResult — rich output: text, structured data, images, tool calls, usage

Executor (evercore)    — wires an Agent to a task key; contains the business logic
Ticket                 — a workflow instance: has a title, a stage, and a list of tasks
Task                   — one unit of work: a key, a payload, and optional dependencies
Worker                 — claims tasks from the database, runs executors, handles retries
```

A `Ticket` moves through stages (`queued` → `running` → `review` → `finished`). Within each stage, its `Tasks` execute in dependency order. Workers pick up ready tasks from the database, run them, and write back results.

## Built-in executors

| Key | What it does |
|-----|-------------|
| `lemlem_prompt` | Simple LLM prompt, no tools |
| `lemlem_agent_json` | Agent call with tool support, returns structured JSON |
| `wait_for_event` | Pauses until an external event arrives (webhook, approval, etc.) |
| `noop` | No-op, completes immediately (useful for testing or placeholder stages) |

Register your own by decorating a function with `@evercore.executor("your_key")`.

## Evercore vs alternatives

| | **Evercore** | [Temporal](https://temporal.io/) | [Prefect](https://www.prefect.io/) | [UseWorkflow](https://useworkflow.dev) |
|---|---|---|---|---|
| **Setup** | Embed in your app, SQLite or Postgres | Separate platform infra | Managed or self-hosted | Managed service |
| **Language** | Python-first | Go server, multi-lang SDKs | Python | TypeScript |
| **Agent-native** | Yes — lemlem Agent built in | Bring your own | Bring your own | Partial |
| **Retries & timeouts** | Yes | Yes (superior) | Yes | Yes |
| **Approval gates** | Yes | Via signals/queries | No | Partial |
| **Event inbox** | Yes | Yes | No | Yes |
| **Scheduling** | Built-in | First-class | First-class | Basic |
| **Operational complexity** | Lowest | Highest | Medium | Medium |

Evercore is the right choice when you want something lightweight, embeddable, and built for AI agent workflows without standing up a separate platform.

## Install

```bash
uv add git+https://github.com/danduma/evergreen.git#subdirectory=libs/evercore
```

Or run directly from the monorepo:

```bash
export EVERCORE_DATABASE_URL="sqlite:///./evercore.db"
uv run --project libs/evercore evercore-api     # API on :8010
uv run --project libs/evercore evercore-worker  # Worker loop
```

## Examples

- [01 — Basic local](../../examples/01-basic-local): SQLite + single worker, everything on one machine
- [02 — External Postgres](../../examples/02-external-postgres): Production database, multiple workers
- [03 — Production VPS](../../examples/03-production-vps): Full deployment on a Linux VPS
