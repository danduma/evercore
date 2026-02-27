import unittest
import time

from fastapi.testclient import TestClient

from _test_support import reset_database
from evercore import api
from evercore.executors.registry import ExecutorRegistry, NoopExecutor, WaitForEventExecutor
from evercore.services import WorkerService


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api.worker_service = WorkerService(
            ExecutorRegistry(
                executors={
                    "noop": NoopExecutor(),
                    "wait_for_event": WaitForEventExecutor(),
                }
            )
        )
        cls.client = TestClient(api.app)

    def setUp(self):
        reset_database()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "evercore")

    def test_ticket_task_and_worker_flow(self):
        create_ticket_response = self.client.post(
            "/tickets",
            json={"title": "api ticket", "workflow_key": "default_ticket"},
        )
        self.assertEqual(create_ticket_response.status_code, 201)
        ticket_id = create_ticket_response.json()["ticket_id"]

        create_task_response = self.client.post(
            f"/tickets/{ticket_id}/tasks",
            json={"task_key": "noop", "payload": {"note": "api"}},
        )
        self.assertEqual(create_task_response.status_code, 201)

        worker_response = self.client.post("/workers/run-once")
        self.assertEqual(worker_response.status_code, 200)
        self.assertTrue(worker_response.json()["processed"])

        ticket_response = self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(ticket_response.status_code, 200)
        body = ticket_response.json()
        self.assertEqual(body["stage"], "finished")
        self.assertEqual(body["status"], "completed")
        self.assertEqual(len(body["tasks"]), 1)
        self.assertEqual(body["tasks"][0]["state"], "completed")

    def test_pause_resume_and_approval_endpoints(self):
        create_ticket_response = self.client.post(
            "/tickets",
            json={"title": "approval ticket", "workflow_key": "default_ticket"},
        )
        self.assertEqual(create_ticket_response.status_code, 201)
        ticket_id = create_ticket_response.json()["ticket_id"]

        create_task_response = self.client.post(
            f"/tickets/{ticket_id}/tasks",
            json={"task_key": "noop"},
        )
        self.assertEqual(create_task_response.status_code, 201)

        pause_response = self.client.post(f"/tickets/{ticket_id}/pause")
        self.assertEqual(pause_response.status_code, 200)
        self.assertTrue(pause_response.json()["paused"])
        self.assertEqual(pause_response.json()["status"], "paused")

        approval_request_response = self.client.post(
            f"/tickets/{ticket_id}/approval/request",
            json={"notes": "please review"},
        )
        self.assertEqual(approval_request_response.status_code, 200)
        self.assertEqual(approval_request_response.json()["approval_status"], "pending")
        self.assertEqual(approval_request_response.json()["stage"], "pending_approval")

        resume_response = self.client.post(f"/tickets/{ticket_id}/resume")
        self.assertEqual(resume_response.status_code, 200)
        self.assertFalse(resume_response.json()["paused"])
        self.assertEqual(resume_response.json()["status"], "waiting_approval")

        approve_response = self.client.post(
            f"/tickets/{ticket_id}/approval/approve",
            json={"notes": "ship it"},
        )
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["approval_status"], "approved")

    def test_event_inbox_and_wait_for_event_executor(self):
        create_ticket_response = self.client.post(
            "/tickets",
            json={"title": "event ticket", "workflow_key": "default_ticket"},
        )
        self.assertEqual(create_ticket_response.status_code, 201)
        ticket_id = create_ticket_response.json()["ticket_id"]

        create_task_response = self.client.post(
            f"/tickets/{ticket_id}/tasks",
            json={
                "task_key": "wait_for_event",
                "payload": {"event_type": "go", "poll_interval_seconds": 1},
            },
        )
        self.assertEqual(create_task_response.status_code, 201)
        task_id = create_task_response.json()["tasks"][0]["id"]

        first_run = self.client.post("/workers/run-once")
        self.assertEqual(first_run.status_code, 200)
        self.assertTrue(first_run.json()["processed"])

        ticket_after_first = self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(ticket_after_first.status_code, 200)
        state_after_first = ticket_after_first.json()["tasks"][0]["state"]
        self.assertEqual(state_after_first, "retrying")

        publish_event = self.client.post(
            f"/tickets/{ticket_id}/events",
            json={"event_type": "go", "payload": {"ok": True}},
        )
        self.assertEqual(publish_event.status_code, 201)

        time.sleep(1.5)
        second_run = self.client.post("/workers/run-once")
        self.assertEqual(second_run.status_code, 200)
        self.assertTrue(second_run.json()["processed"])

        ticket_after_second = self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(ticket_after_second.status_code, 200)
        self.assertEqual(ticket_after_second.json()["tasks"][0]["id"], task_id)
        self.assertEqual(ticket_after_second.json()["tasks"][0]["state"], "completed")

    def test_schedule_endpoints_and_trigger(self):
        create_schedule = self.client.post(
            "/schedules",
            json={
                "schedule_key": "every-minute-noop",
                "interval_seconds": 60,
                "task_key": "noop",
            },
        )
        self.assertEqual(create_schedule.status_code, 201)
        schedule_id = create_schedule.json()["id"]

        list_response = self.client.get("/schedules")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        trigger_response = self.client.post(f"/schedules/{schedule_id}/trigger")
        self.assertEqual(trigger_response.status_code, 200)
        triggered_ticket_id = trigger_response.json()["triggered_ticket_id"]
        self.assertTrue(triggered_ticket_id.startswith("tkt-"))

        pause_response = self.client.post(f"/schedules/{schedule_id}/pause")
        self.assertEqual(pause_response.status_code, 200)
        self.assertFalse(pause_response.json()["active"])

        resume_response = self.client.post(f"/schedules/{schedule_id}/resume")
        self.assertEqual(resume_response.status_code, 200)
        self.assertTrue(resume_response.json()["active"])


if __name__ == "__main__":
    unittest.main()
