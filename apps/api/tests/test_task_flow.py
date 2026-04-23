import unittest
import time

from fastapi.testclient import TestClient

from app.main import create_app


class TaskFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_task_create_assign_run_builtin(self) -> None:
        created = self.client.post("/tasks", json={"title": "Beta smoke", "description": "builtin path"})
        self.assertEqual(created.status_code, 200)
        task_id = created.json()["data"]["task_id"]

        assigned = self.client.post(f"/tasks/{task_id}/assign", json={"agent_id": "octopus_builtin"})
        self.assertEqual(assigned.status_code, 200)

        run = self.client.post(f"/tasks/{task_id}/run")
        self.assertEqual(run.status_code, 200)
        self.assertTrue(run.json()["ok"])
        self.assertTrue(run.json().get("queued", False))

        # Worker executes asynchronously; wait for completion.
        deadline = time.time() + 8.0
        status = None
        while time.time() < deadline:
            timeline = self.client.get(f"/tasks/{task_id}/timeline").json()
            status = timeline["task"]["status"]
            if status in ("succeeded", "failed", "waiting_approval"):
                break
            time.sleep(0.2)
        self.assertIn(status, ("succeeded", "failed", "waiting_approval"))

        detail = self.client.get(f"/tasks/{task_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["assignments"])

        timeline = self.client.get(f"/tasks/{task_id}/timeline")
        self.assertEqual(timeline.status_code, 200)
        self.assertTrue(timeline.json()["events"])
        self.assertTrue(timeline.json()["runs"])

        runs = self.client.get("/runs")
        self.assertEqual(runs.status_code, 200)
        self.assertTrue(runs.json()["items"])

    def test_failed_task_retry_and_bridge_result(self) -> None:
        created = self.client.post(
            "/tasks",
            json={"title": "simulate_fail", "description": "simulate_fail to exercise retry"},
        )
        task_id = created.json()["data"]["task_id"]

        self.client.post(f"/tasks/{task_id}/assign", json={"agent_id": "octopus_builtin"})
        failed_run = self.client.post(f"/tasks/{task_id}/run")
        self.assertEqual(failed_run.status_code, 200)
        self.assertTrue(failed_run.json()["ok"])

        # Wait until worker marks failed
        deadline = time.time() + 8.0
        status = None
        while time.time() < deadline:
            status = self.client.get(f"/tasks/{task_id}").json()["data"]["status"]
            if status == "failed":
                break
            time.sleep(0.2)
        self.assertEqual(status, "failed")

        retried = self.client.post(f"/tasks/{task_id}/retry")
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["data"]["status"], "assigned")

        external_task = self.client.post(
            "/tasks",
            json={"title": "Bridge handoff", "description": "Complete via local bridge result"},
        )
        external_task_id = external_task.json()["data"]["task_id"]
        self.client.post(
            "/local-bridge/register",
            json={
                "agent_id": "claude_code_external",
                "display_name": "Claude Code (bridge)",
                "adapter_id": "claude_code",
                "capabilities": {"can_code": True, "supports_structured_task": True},
            },
        )
        self.client.post(
            f"/tasks/{external_task_id}/assign",
            json={"agent_id": "claude_code_external"},
        )
        run = self.client.post(f"/tasks/{external_task_id}/run")
        self.assertEqual(run.status_code, 200)
        run_id = run.json()["run"]["run_id"]

        bridge_result = self.client.post(
            "/local-bridge/result",
            json={
                "task_id": external_task_id,
                "run_id": run_id,
                "agent_id": "claude_code_external",
                "status": "succeeded",
                "output": "bridge completed successfully",
                "integration_path": "manual_claude_code",
            },
        )
        self.assertEqual(bridge_result.status_code, 200)
        self.assertTrue(bridge_result.json()["ok"])

    def test_metrics_and_watchdog(self) -> None:
        metrics = self.client.get("/metrics")
        watchdog = self.client.get("/watchdog")
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(watchdog.status_code, 200)
        self.assertIn("fault_recovery", metrics.json())
        self.assertIn("recovery_hints", watchdog.json()["data"])


if __name__ == "__main__":
    unittest.main()
