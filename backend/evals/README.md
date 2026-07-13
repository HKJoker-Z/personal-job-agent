# Behavioral Evaluation Suite

Version 1.8 uses these local evaluation cases for deterministic behavioral and regression checks.

- The suite runs offline.
- It does not call DeepSeek or any external LLM.
- Cases use fictitious, sanitized test data only.
- TEST ONLY fake secret strings exist solely to exercise deterministic redaction and blocking rules.
- Evaluation results store check summaries, not full case inputs, prompts, resumes, job descriptions, model outputs, or secrets.

`v203_cases.json` adds the fixed Alpha 3 matching and fact-grounding regression set. It covers exact, synonym and related matches; unknown versus failed hard filters; absent confirmed facts; prompt injection; unsupported metrics and leadership; unknown salary; and immutable revision selection. The corresponding tests execute deterministic code only and never call an external model.
