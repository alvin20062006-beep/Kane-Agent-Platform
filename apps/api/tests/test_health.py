import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class HealthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("tasks_total", body)
        self.assertIn("local_bridge_reachable", body)


if __name__ == "__main__":
    unittest.main()
