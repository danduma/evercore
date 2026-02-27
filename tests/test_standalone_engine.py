import os
import unittest
from pathlib import Path

from _test_support import reset_database

os.environ["EVERCORE_WORKFLOW_DIR"] = str((Path(__file__).resolve().parents[1] / "workflows").resolve())

from evercore.db import create_db_and_tables, session_scope  # noqa: E402
from evercore.executors import ExecutorRegistry  # noqa: E402
from evercore.schemas import TaskCreateRequest, TicketCreateRequest  # noqa: E402
from evercore.services import TicketService, WorkerService  # noqa: E402
from evercore.workflow import WorkflowLoader  # noqa: E402


class StandaloneEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create_db_and_tables()
        workflow_loader = WorkflowLoader(Path(os.environ["EVERCORE_WORKFLOW_DIR"]))
        cls.ticket_service = TicketService(workflow_loader)
        cls.worker_service = WorkerService(ExecutorRegistry.default())

    def setUp(self):
        reset_database()

    def test_ticket_task_worker_flow_with_noop(self):
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(
                session,
                TicketCreateRequest(title="engine test", workflow_key="default_ticket"),
            )
            ticket_id = ticket.ticket_id
            self.ticket_service.create_task(
                session,
                ticket_id,
                TaskCreateRequest(task_key="noop", payload={"note": "test"}),
            )

        with session_scope() as session:
            result = self.worker_service.process_once(session, worker_id="test-worker")
            self.assertTrue(result.processed)

        with session_scope() as session:
            summary = self.ticket_service.get_ticket_summary(session, ticket_id)
            self.assertIsNotNone(summary)
            self.assertEqual(len(summary.tasks), 1)
            self.assertEqual(summary.tasks[0].state, "completed")
            self.assertEqual(summary.stage, "finished")


if __name__ == "__main__":
    unittest.main()
