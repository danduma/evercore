import unittest
from datetime import timedelta

from sqlmodel import select

from _test_support import WORKFLOW_DIR, reset_database
from evercore.db import session_scope
from evercore.execution import ExecutionResult, TaskExecutor
from evercore.executors.registry import ExecutorRegistry
from evercore.models import Task, TaskLog, WorkerHeartbeat
from evercore.schemas import TaskCreateRequest, TicketCreateRequest
from evercore.services import TicketService, WorkerService
from evercore.time_utils import coerce_utc, now_utc
from evercore.workflow import WorkflowLoader


class _SuccessExecutor(TaskExecutor):
    def execute(self, ticket, task):
        del ticket, task
        return ExecutionResult(success=True, message="ok", output={"done": True})


class _FailExecutor(TaskExecutor):
    def execute(self, ticket, task):
        del ticket, task
        return ExecutionResult(success=False, message="boom", output={"ok": False})


class _DeferExecutor(TaskExecutor):
    def execute(self, ticket, task):
        del ticket, task
        return ExecutionResult(
            success=False,
            defer=True,
            defer_seconds=1,
            message="waiting for external signal",
        )


class WorkerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticket_service = TicketService(WorkflowLoader(WORKFLOW_DIR))

    def setUp(self):
        reset_database()

    def test_process_once_no_tasks_updates_idle_heartbeat(self):
        service = WorkerService(ExecutorRegistry(executors={}))
        with session_scope() as session:
            result = service.process_once(session, worker_id="worker-empty")
            heartbeat = session.exec(
                select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == "worker-empty")
            ).first()
            self.assertFalse(result.processed)
            self.assertIsNotNone(heartbeat)
            self.assertEqual(heartbeat.state, "idle")
            self.assertIsNone(heartbeat.current_task_id)

    def test_process_once_unknown_task_key_fails_and_logs(self):
        service = WorkerService(ExecutorRegistry(executors={}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="t"))
            task = self.ticket_service.create_task(
                session, ticket.ticket_id, TaskCreateRequest(task_key="unknown-key")
            )
            task_id = task.id

        with session_scope() as session:
            result = service.process_once(session, worker_id="worker-unknown")
            task_row = session.exec(select(Task).where(Task.id == task_id)).first()
            log_rows = session.exec(select(TaskLog).where(TaskLog.task_id == task_id)).all()
            task_state = task_row.state
            task_error = task_row.error_message
            log_count = len(log_rows)

        self.assertTrue(result.processed)
        self.assertEqual(task_state, "failed")
        self.assertIn("unknown task_key", task_error)
        self.assertGreaterEqual(log_count, 1)

    def test_dependencies_gate_execution_order(self):
        service = WorkerService(ExecutorRegistry(executors={"simple": _SuccessExecutor()}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="deps"))
            first = self.ticket_service.create_task(
                session, ticket.ticket_id, TaskCreateRequest(task_key="simple")
            )
            second = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="simple", depends_on_task_ids=[first.id]),
            )
            first_id = first.id
            second_id = second.id
            ticket_id = ticket.ticket_id

        with session_scope() as session:
            first_run = service.process_once(session, worker_id="worker-deps")
            self.assertTrue(first_run.processed)

        with session_scope() as session:
            second_run = service.process_once(session, worker_id="worker-deps")
            self.assertTrue(second_run.processed)
            first_row = session.exec(select(Task).where(Task.id == first_id)).first()
            second_row = session.exec(select(Task).where(Task.id == second_id)).first()
            summary = self.ticket_service.get_ticket_summary(session, ticket_id)
            first_state = first_row.state
            second_state = second_row.state

        self.assertEqual(first_state, "completed")
        self.assertEqual(second_state, "completed")
        self.assertEqual(summary.stage, "finished")
        self.assertEqual(summary.status, "completed")

    def test_failed_task_enters_retry_then_dead_letter(self):
        service = WorkerService(ExecutorRegistry(executors={"always_fail": _FailExecutor()}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="retry"))
            task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="always_fail", max_attempts=2),
            )
            task_id = task.id

        with session_scope() as session:
            first = service.process_once(session, worker_id="worker-retry")
            self.assertTrue(first.processed)
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            self.assertEqual(row.state, "retrying")
            self.assertIsNotNone(row.next_run_at)

        with session_scope() as session:
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            row.next_run_at = now_utc() - timedelta(seconds=1)
            session.add(row)

        with session_scope() as session:
            second = service.process_once(session, worker_id="worker-retry")
            self.assertTrue(second.processed)
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            self.assertEqual(row.state, "dead_letter")

    def test_cancel_request_cancels_before_execution(self):
        service = WorkerService(ExecutorRegistry(executors={"simple": _SuccessExecutor()}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="cancel"))
            task = self.ticket_service.create_task(
                session, ticket.ticket_id, TaskCreateRequest(task_key="simple")
            )
            task.cancel_requested = True
            task.cancel_requested_at = now_utc()
            session.add(task)
            task_id = task.id

        with session_scope() as session:
            result = service.process_once(session, worker_id="worker-cancel")
            self.assertTrue(result.processed)
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            self.assertEqual(row.state, "cancelled")

    def test_deferred_result_requeues_without_consuming_attempts(self):
        service = WorkerService(ExecutorRegistry(executors={"defer": _DeferExecutor()}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="defer"))
            task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="defer", max_attempts=2),
            )
            task_id = task.id

        with session_scope() as session:
            result = service.process_once(session, worker_id="worker-defer")
            self.assertTrue(result.processed)
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            self.assertEqual(row.state, "retrying")
            self.assertEqual(row.attempt_count, 0)
            self.assertIsNotNone(row.next_run_at)

    def test_retry_policy_uses_task_overrides(self):
        service = WorkerService(ExecutorRegistry(executors={"always_fail": _FailExecutor()}))
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="retry-override"))
            task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(
                    task_key="always_fail",
                    max_attempts=5,
                    retry_base_seconds=1,
                    retry_max_seconds=2,
                ),
            )
            task_id = task.id

        with session_scope() as session:
            result = service.process_once(session, worker_id="worker-retry-override")
            self.assertTrue(result.processed)
            row = session.exec(select(Task).where(Task.id == task_id)).first()
            self.assertEqual(row.state, "retrying")
            delta = coerce_utc(row.next_run_at) - now_utc()
            self.assertLessEqual(delta.total_seconds(), 2.5)


if __name__ == "__main__":
    unittest.main()
