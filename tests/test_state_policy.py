import unittest

from evercore.models import Task, Ticket
from evercore.services import DefaultTicketStatePolicy


class StatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = DefaultTicketStatePolicy()
        self.ticket = Ticket(ticket_id="tkt-test")

    def test_no_tasks_stays_queued(self):
        update = self.policy.resolve(self.ticket, [])
        self.assertEqual(update.stage, "queued")
        self.assertEqual(update.status, "active")
        self.assertIsNone(update.completed_at)

    def test_any_failed_moves_to_review(self):
        tasks = [Task(ticket_id="t", task_key="a", state="failed")]
        update = self.policy.resolve(self.ticket, tasks)
        self.assertEqual(update.stage, "review")
        self.assertEqual(update.status, "attention")
        self.assertIsNone(update.completed_at)

    def test_all_completed_finishes_ticket(self):
        tasks = [
            Task(ticket_id="t", task_key="a", state="completed"),
            Task(ticket_id="t", task_key="b", state="completed"),
        ]
        update = self.policy.resolve(self.ticket, tasks)
        self.assertEqual(update.stage, "finished")
        self.assertEqual(update.status, "completed")
        self.assertIsNotNone(update.completed_at)

    def test_running_or_queued_keeps_ticket_running(self):
        tasks = [Task(ticket_id="t", task_key="a", state="running")]
        running_update = self.policy.resolve(self.ticket, tasks)
        self.assertEqual(running_update.stage, "running")

        tasks = [Task(ticket_id="t", task_key="a", state="queued")]
        queued_update = self.policy.resolve(self.ticket, tasks)
        self.assertEqual(queued_update.stage, "running")


if __name__ == "__main__":
    unittest.main()

