import unittest

from recommendation_engine import (
    generate_next_action,
    identify_critical_missing_skills,
)


def base_result(match_score, missing_skills=None, missing_keywords=None, rag_sources=None):
    return {
        "match_score": match_score,
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": missing_skills or [],
        "resume_suggestions": ["Make the RAG project bullet easier to find."],
        "ats_analysis": {
            "important_keywords": ["RAG", "FastAPI", "LLM applications"],
            "matched_keywords": ["Python", "FastAPI"],
            "missing_keywords": missing_keywords or [],
            "keyword_suggestions": [],
        },
        "rag_sources": rag_sources or [],
    }


class RecommendationEngineTest(unittest.TestCase):
    def test_apply_now_for_high_score_without_critical_missing(self):
        action = generate_next_action(base_result(90))
        self.assertEqual(action["action"], "apply_now")

    def test_improve_resume_first_for_good_score_with_small_gap(self):
        action = generate_next_action(base_result(75, missing_skills=["Docker"]))
        self.assertEqual(action["action"], "improve_resume_first")

    def test_upskill_first_for_medium_score_with_technical_gap(self):
        action = generate_next_action(base_result(60, missing_skills=["Kubernetes"]))
        self.assertEqual(action["action"], "upskill_first")

    def test_save_for_later_for_low_mid_score(self):
        action = generate_next_action(base_result(45))
        self.assertEqual(action["action"], "save_for_later")

    def test_skip_for_low_score(self):
        action = generate_next_action(base_result(30))
        self.assertEqual(action["action"], "skip")

    def test_rag_supported_skill_is_not_critical_missing(self):
        result = base_result(
            75,
            missing_skills=["RAG"],
            missing_keywords=["Retrieval-Augmented Generation"],
            rag_sources=[
                {
                    "content_preview": (
                        "Project Knowledge RAG uses Retrieval-Augmented Generation, "
                        "document chunking, SQLite FTS5 retrieval, and top-k evidence injection."
                    )
                }
            ],
        )
        self.assertEqual(identify_critical_missing_skills(result), [])


if __name__ == "__main__":
    unittest.main()
