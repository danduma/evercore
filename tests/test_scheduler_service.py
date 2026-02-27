import unittest

from _test_support import WORKFLOW_DIR, reset_database
from evercore.db import session_scope
from evercore.schemas import ScheduleCreateRequest
from evercore.services import SchedulerService, TicketService
from evercore.time_utils import now_utc
from evercore.workflow import WorkflowLoader


class SchedulerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticket_service = TicketService(WorkflowLoader(WORKFLOW_DIR))
        cls.scheduler = SchedulerService(cls.ticket_service)

    def setUp(self):
        reset_database()

    def test_process_due_schedule_creates_ticket_and_task(self):
        with session_scope() as session:
            self.scheduler.create_schedule(
                session,
                ScheduleCreateRequest(
                    schedule_key="s1",
                    interval_seconds=60,
                    task_key="noop",
                ),
            )
            processed = self.scheduler.process_due_schedules(session, limit=10)
            self.assertEqual(processed, 1)
            tickets = self.ticket_service.list_ticket_summaries(session, limit=10)
            self.assertEqual(len(tickets), 1)
            self.assertEqual(len(tickets[0].tasks), 1)
            self.assertEqual(tickets[0].tasks[0].task_key, "noop")

    def test_non_repeating_schedule_deactivates_after_run(self):
        with session_scope() as session:
            row = self.scheduler.create_schedule(
                session,
                ScheduleCreateRequest(
                    schedule_key="one-shot",
                    first_run_at=now_utc(),
                ),
            )
            ticket_id = self.scheduler.trigger_schedule_once(session, row.id)
            self.assertTrue(ticket_id.startswith("tkt-"))
            summary = self.scheduler.list_schedules(session, limit=10)[0]
            self.assertFalse(summary.active)
            self.assertIsNone(summary.next_run_at)


if __name__ == "__main__":
    unittest.main()
