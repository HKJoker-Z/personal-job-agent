# Behavioral Evaluation Suite

Version 1.8 uses these local evaluation cases for deterministic behavioral and regression checks.

- The suite runs offline.
- It does not call DeepSeek or any external LLM.
- Cases use fictitious, sanitized test data only.
- TEST ONLY fake secret strings exist solely to exercise deterministic redaction and blocking rules.
- Evaluation results store check summaries, not full case inputs, prompts, resumes, job descriptions, model outputs, or secrets.
