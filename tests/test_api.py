import unittest

from fastapi.testclient import TestClient

from _test_support import reset_database
from evercore import api
from evercore.executors.registry import ExecutorRegistry, NoopExecutor
from evercore.services import WorkerService


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api.worker_service = WorkerService(ExecutorRegistry(executors={"noop": NoopExecutor()}))
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


if __name__ == "__main__":
    unittest.main()
