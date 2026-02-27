import unittest

from _test_support import WORKFLOW_DIR, reset_database
from evercore.db import session_scope
from evercore.repositories import get_ticket_by_ticket_id, list_dependencies
from evercore.schemas import TaskCreateRequest, TicketCreateRequest
from evercore.services import TicketService
from evercore.workflow import WorkflowLoader


class TicketServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticket_service = TicketService(WorkflowLoader(WORKFLOW_DIR))

    def setUp(self):
        reset_database()

    def test_create_ticket_uses_default_workflow(self):
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="hello"))
            persisted = get_ticket_by_ticket_id(session, ticket.ticket_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.workflow_key, "default_ticket")
            self.assertEqual(persisted.stage, "queued")

    def test_create_ticket_with_missing_workflow_raises(self):
        with session_scope() as session:
            with self.assertRaises(FileNotFoundError):
                self.ticket_service.create_ticket(
                    session,
                    TicketCreateRequest(title="x", workflow_key="does-not-exist"),
                )

    def test_create_task_requires_existing_ticket(self):
        with session_scope() as session:
            with self.assertRaises(ValueError):
                self.ticket_service.create_task(
                    session,
                    "missing-ticket",
                    TaskCreateRequest(task_key="noop"),
                )

    def test_create_task_adds_dependencies_and_sets_running_stage(self):
        with session_scope() as session:
            ticket = self.ticket_service.create_ticket(session, TicketCreateRequest(title="ticket"))
            dep_task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="dep"),
            )
            dep_task_id = dep_task.id
            target_task = self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(task_key="target", depends_on_task_ids=[dep_task_id, 0, -1]),
            )
            target_task_id = target_task.id
            ticket_id = ticket.ticket_id
        with session_scope() as session:
            dependencies = list_dependencies(session, target_task_id)
            summary = self.ticket_service.get_ticket_summary(session, ticket_id)
            dependency_target_ids = [dep.depends_on_task_id for dep in dependencies]

        self.assertEqual(len(dependency_target_ids), 1)
        self.assertEqual(dependency_target_ids[0], dep_task_id)
        self.assertEqual(summary.stage, "running")
        self.assertEqual(len(summary.tasks), 2)


if __name__ == "__main__":
    unittest.main()
