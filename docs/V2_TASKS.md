# Version 2 Tasks

Tasks are owned resources that may link to an Application, a Job, both consistently, or neither. Linking an Application derives and validates its owned Job; cross-user and mismatched relations are rejected.

Task types cover review, resume selection/preparation, submission, follow-up, assessment, interview preparation/interview, document request, and other. Status is `pending`, `in_progress`, `completed`, or `cancelled`; priority is `low`, `normal`, `high`, or `urgent`.

Completing a Task sets `completed_at`. Reopening clears it. Update, complete, reopen, and archive require the expected revision. Delete/archive is non-destructive. Lists support status, priority, due range, overdue, Application, Job, type, archive state, and allowlisted sort.

`reminder_at` is storage only. It must not be after `due_at` when both exist and cannot be placed outside the supported ten-year horizon. Version 2.0.2 has no Scheduler, Worker, notification, browser notification, or email sender.

Suggested Tasks are deterministic mappings from the current Application stage. The GET endpoint never writes to the database and never calls an LLM. The user must explicitly create any suggestion.
