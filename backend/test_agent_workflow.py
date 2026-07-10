import unittest
from unittest.mock import patch

from agent_workflow import AgentWorkflow, safe_message


class AgentWorkflowTest(unittest.TestCase):
    def test_sub_millisecond_completed_step_keeps_precision(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[0, 1_000_000_000, 1_000_450_000],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.start_step("parse_resume", "Parse Resume")
            workflow.complete_step("parse_resume", "Resume text extracted successfully.")

        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "completed")
        self.assertEqual(step["duration_us"], 450)
        self.assertEqual(step["duration_ms"], 0.45)
        self.assertNotEqual(step["duration_ms"], 0)

    def test_multi_millisecond_completed_step_keeps_decimal_duration(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[0, 1_000_000_000, 1_012_500_000],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.start_step("parse_resume", "Parse Resume")
            workflow.complete_step("parse_resume", "Resume text extracted successfully.")

        step = workflow.to_list()[0]
        self.assertEqual(step["duration_us"], 12_500)
        self.assertEqual(step["duration_ms"], 12.5)

    def test_skipped_step_status(self):
        with patch("agent_workflow.time.perf_counter_ns", return_value=0):
            workflow = AgentWorkflow("test-workflow")
            workflow.skip_step("retrieve_project_evidence", "Retrieve Project Knowledge", "RAG is off.")

        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "skipped")
        self.assertEqual(step["duration_ms"], 0.0)
        self.assertEqual(step["duration_us"], 0)
        self.assertEqual(workflow.status(), "completed")

    def test_failed_step_has_real_duration(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[0, 1_000_000_000, 1_002_250_000],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.start_step("run_llm_analysis", "Run LLM Analysis")
            workflow.fail_step("run_llm_analysis", "LLM analysis failed.")

        step = workflow.to_list()[0]
        self.assertEqual(step["status"], "failed")
        self.assertEqual(step["duration_us"], 2_250)
        self.assertEqual(step["duration_ms"], 2.25)
        self.assertEqual(workflow.status(), "failed")

    def test_duration_never_goes_negative(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[0, 2_000_000_000, 1_999_000_000],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.start_step("validate_input", "Validate Input")
            workflow.complete_step("validate_input", "Input accepted.")

        step = workflow.to_list()[0]
        self.assertEqual(step["duration_ms"], 0.0)
        self.assertEqual(step["duration_us"], 0)

    def test_workflow_total_duration_uses_perf_counter_ns(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[1_000_000_000, 1_012_345_678],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.finish()

        duration = workflow.workflow_duration()
        self.assertEqual(duration["workflow_duration_us"], 12_346)
        self.assertEqual(duration["workflow_duration_ms"], 12.346)

    def test_serialization_does_not_expose_private_timing_fields(self):
        with patch(
            "agent_workflow.time.perf_counter_ns",
            side_effect=[0, 1_000_000_000, 1_000_450_000],
        ):
            workflow = AgentWorkflow("test-workflow")
            workflow.start_step("parse_resume", "Parse Resume")
            workflow.complete_step("parse_resume", "Resume text extracted successfully.")

        step = workflow.to_list()[0]
        self.assertIn("duration_ms", step)
        self.assertIn("duration_us", step)
        self.assertNotIn("_started_perf_ns", step)

    def test_message_is_truncated(self):
        long_message = "A" * 1000
        self.assertLessEqual(len(safe_message(long_message)), 240)


if __name__ == "__main__":
    unittest.main()
