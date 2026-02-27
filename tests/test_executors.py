import unittest

from evercore.agent_runtime import AgentRuntimeResult
from evercore.executors.registry import (
    ExecutorRegistry,
    LemlemAgentJsonExecutor,
    LemlemPromptExecutor,
    NoopExecutor,
)
from evercore.execution import ExecutionResult, TaskExecutor
from evercore.models import Task, Ticket


class _FakeRuntime:
    def run_prompt(self, *, prompt, model=None, system_prompt=None, temperature=None):
        del model, system_prompt, temperature
        return AgentRuntimeResult(
            success=True,
            text=f"echo: {prompt}",
            usage={"total_tokens": 10},
            provider="test",
            model_used="test-model",
        )

    def run_agent_json(
        self,
        *,
        model,
        system_prompt,
        payload,
        temperature=None,
        max_tool_iterations=6,
    ):
        del model, system_prompt, payload, temperature, max_tool_iterations
        return AgentRuntimeResult(
            success=True,
            text="json-result",
            usage={"total_tokens": 5},
            model_used="test-model",
            raw={"ok": True},
        )


class _DummyExecutor(TaskExecutor):
    def execute(self, ticket, task):
        del ticket, task
        return ExecutionResult(success=True)


class ExecutorsTests(unittest.TestCase):
    def test_noop_executor_succeeds(self):
        executor = NoopExecutor()
        result = executor.execute(Ticket(ticket_id="t"), Task(ticket_id="t", task_key="noop"))
        self.assertTrue(result.success)
        self.assertEqual(result.message, "noop task completed")

    def test_lemlem_prompt_executor_requires_prompt(self):
        executor = LemlemPromptExecutor(_FakeRuntime())
        ticket = Ticket(ticket_id="t")
        task = Task(ticket_id="t", task_key="lemlem_prompt", payload={})
        result = executor.execute(ticket, task)
        self.assertFalse(result.success)
        self.assertIn("payload.prompt", result.message)

    def test_lemlem_prompt_executor_success(self):
        executor = LemlemPromptExecutor(_FakeRuntime())
        ticket = Ticket(ticket_id="t")
        task = Task(
            ticket_id="t",
            task_key="lemlem_prompt",
            payload={"prompt": "hello"},
        )
        result = executor.execute(ticket, task)
        self.assertTrue(result.success)
        self.assertEqual(result.output["text"], "echo: hello")
        self.assertEqual(result.output["model_used"], "test-model")

    def test_lemlem_agent_json_executor_validates_inputs(self):
        executor = LemlemAgentJsonExecutor(_FakeRuntime())
        ticket = Ticket(ticket_id="t")
        missing_prompt = Task(ticket_id="t", task_key="lemlem_agent_json", payload={})
        bad_payload = Task(
            ticket_id="t",
            task_key="lemlem_agent_json",
            payload={"system_prompt": "x", "user_payload": "not-a-dict"},
        )

        result_missing = executor.execute(ticket, missing_prompt)
        result_bad_payload = executor.execute(ticket, bad_payload)

        self.assertFalse(result_missing.success)
        self.assertFalse(result_bad_payload.success)

    def test_registry_register_and_get(self):
        registry = ExecutorRegistry(executors={})
        dummy = _DummyExecutor()
        registry.register("dummy", dummy)
        self.assertIs(registry.get("dummy"), dummy)
        self.assertIsNone(registry.get("missing"))


if __name__ == "__main__":
    unittest.main()

