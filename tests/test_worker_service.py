import unittest

from sqlmodel import select

from _test_support import WORKFLOW_DIR, reset_database
from evercore.db import session_scope
from evercore.execution import ExecutionResult, TaskExecutor
from evercore.executors.registry import ExecutorRegistry
from evercore.models import Task, TaskLog, WorkerHeartbeat
from evercore.schemas import TaskCreateRequest, TicketCreateRequest
from evercore.services import TicketService, WorkerService
from evercore.workflow import WorkflowLoader


class _SuccessExecutor(TaskExecutor):
    def execute(self, ticket, task):
        del ticket, task
        return ExecutionResult(success=True, message="ok", output={"done": True})


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


if __name__ == "__main__":
    unittest.main()
