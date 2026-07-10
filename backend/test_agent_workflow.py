import unittest

from agent_workflow import AgentWorkflow, safe_message


class AgentWorkflowTest(unittest.TestCase):
    def test_completed_step_has_duration(self):
        workflow = AgentWorkflow("test-workflow")
        workflow.start_step("parse_resume", "Parse Resume")
        workflow.complete_step("parse_resume", "Resume text extracted successfully.")
        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "completed")
        self.assertIsInstance(step["duration_ms"], int)
        self.assertGreaterEqual(step["duration_ms"], 0)

    def test_skipped_step_status(self):
        workflow = AgentWorkflow("test-workflow")
        workflow.skip_step("retrieve_project_evidence", "Retrieve Project Knowledge", "RAG is off.")
        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "skipped")
        self.assertEqual(workflow.status(), "completed")

    def test_failed_step_status(self):
        workflow = AgentWorkflow("test-workflow")
        workflow.start_step("run_llm_analysis", "Run LLM Analysis")
        workflow.fail_step("run_llm_analysis", "LLM analysis failed.")
        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "failed")
        self.assertEqual(workflow.status(), "failed")

    def test_message_is_truncated(self):
        long_message = "A" * 1000
        self.assertLessEqual(len(safe_message(long_message)), 240)


if __name__ == "__main__":
    unittest.main()
