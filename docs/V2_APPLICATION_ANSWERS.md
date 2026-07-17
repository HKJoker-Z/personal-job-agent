# Application Answer Drafts

The answers endpoint accepts up to 20 bounded questions. Every question is untrusted text: instruction-like Prompt Injection content is not executed and yields `needs_user_input`.

Work authorization and sponsorship answers use only explicit Profile Preferences. Salary answers use only the confirmed minimum/currency preference. If the value is absent, the system returns `needs_user_input`; it does not guess. General answers reference confirmed Match Evidence only.

Each question creates its own `application_answer` Material and Version so review history is independent. Answers are Drafts, can be edited as new Versions, and are never submitted automatically.
