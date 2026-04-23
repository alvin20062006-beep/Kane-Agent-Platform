import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class EverydayFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_conversation_message_and_promote(self) -> None:
        conversation = self.client.post(
            "/conversations",
            json={"agent_id": "octopus_builtin", "title": "Daily check-in"},
        )
        self.assertEqual(conversation.status_code, 200)
        conversation_id = conversation.json()["data"]["conversation_id"]

        message = self.client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "content": "remember: summarize the current beta health",
                "kind": "chat",
                "create_memory_candidate": True,
            },
        )
        self.assertEqual(message.status_code, 200)
        self.assertEqual(message.json()["assistant_message"]["role"], "assistant")
        self.assertIsNotNone(message.json()["memory_candidate"])

        detail = self.client.get(f"/conversations/{conversation_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(len(detail.json()["messages"]), 3)

        promoted = self.client.post(
            f"/conversations/{conversation_id}/promote",
            json={"execution_mode": "commander", "assign_agent": True},
        )
        self.assertEqual(promoted.status_code, 200)
        task_id = promoted.json()["task"]["task_id"]

        task = self.client.get(f"/tasks/{task_id}")
        self.assertEqual(task.status_code, 200)
        self.assertEqual(task.json()["data"]["assigned_agent_id"], "octopus_builtin")

    def test_file_read_and_memory_candidate_governance(self) -> None:
        conversation = self.client.post(
            "/conversations",
            json={"agent_id": "octopus_builtin"},
        )
        conversation_id = conversation.json()["data"]["conversation_id"]

        file_read = self.client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "content": "Read the PRD intro",
                "kind": "file_read",
                "file_path": "docs/PRD.md",
            },
        )
        self.assertEqual(file_read.status_code, 200)
        self.assertIn("Excerpt", file_read.json()["assistant_message"]["content"])

        candidate_message = self.client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "content": "remember: I prefer lightweight conversations before formal tasks",
                "kind": "chat",
                "create_memory_candidate": True,
            },
        )
        memory_id = candidate_message.json()["memory_candidate"]["memory_id"]

        candidates = self.client.get("/memory/candidates")
        self.assertEqual(candidates.status_code, 200)
        self.assertTrue(any(item["memory_id"] == memory_id for item in candidates.json()["items"]))

        approve = self.client.post(f"/memory/candidates/{memory_id}/approve")
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.json()["data"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
