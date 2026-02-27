import unittest

from sqlmodel import select

from _test_support import WORKFLOW_DIR, reset_database
from evercore.db import session_scope
from evercore.models import WorkerHeartbeat
from evercore.repositories import (
    add_task_log,
    list_tickets,
    update_heartbeat,
)
from evercore.schemas import TaskCreateRequest, TicketCreateRequest
from evercore.services import TicketService
from evercore.workflow import WorkflowLoader


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticket_service = TicketService(WorkflowLoader(WORKFLOW_DIR))

    def setUp(self):
        reset_database()

    def test_list_tickets_respects_limit_and_order(self):
        with session_scope() as session:
            self.ticket_service.create_ticket(session, TicketCreateRequest(title="first"))
            self.ticket_service.create_ticket(session, TicketCreateRequest(title="second"))
            tickets = list_tickets(session, limit=1)
            self.assertEqual(len(tickets), 1)
            self.assertEqual(tickets[0].title, "second")

    def test_update_heartbeat_creates_then_updates_row(self):
        with session_scope() as session:
            update_heartbeat(session, worker_id="w1", state="idle", current_task_id=None)
            update_heartbeat(session, worker_id="w1", state="working", current_task_id=99)
            rows = list(
                session.exec(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == "w1")).all()
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].state, "working")
            self.assertEqual(rows[0].current_task_id, 99)

    def test_add_task_log_defaults_details(self):
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="log"))
            task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="noop", payload={}),
            )
            log = add_task_log(session, task_id=task.id, message="hello")
            self.assertEqual(log.details, {})
            self.assertEqual(log.log_type, "info")


if __name__ == "__main__":
    unittest.main()
