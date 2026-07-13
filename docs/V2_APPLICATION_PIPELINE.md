# Version 2 Application Pipeline

An Application belongs to one user and one owned Job. By default, a user can have one unarchived Application per Job. An optional Resume Version must belong to the same user and an unarchived Resume; a draft can be linked only with an explicit warning and is never modified.

The stable stages are:

```text
saved -> shortlisted/preparing/closed
shortlisted -> preparing/rejected/closed
preparing -> ready_to_apply/withdrawn/closed
ready_to_apply -> applied/withdrawn/closed
applied -> assessment/interview/rejected/withdrawn/closed
assessment -> interview/rejected/withdrawn
interview -> final_interview/offer/rejected/withdrawn
final_interview -> offer/rejected/withdrawn
offer -> accepted/rejected/withdrawn
accepted/rejected/withdrawn/closed -> terminal
```

The client cannot PATCH `current_stage`. `POST /transition` obtains a row lock, checks the expected revision and transition matrix, updates timestamps/outcome, increments the revision, and appends Stage History in the same transaction. Invalid or stale transitions return 409 and list allowed next stages.

Terminal Applications require `POST /reopen`, a reason, expected revision, and exact confirmation. Reopen returns to `saved` and appends history; it is never silent. Archive is non-destructive and does not remove history, Notes, or Tasks.

Stage History is append-only. ORM update/delete hooks reject mutation, and no history mutation API exists. Notes are plain-text private data with ownership, optimistic revisions, soft deletion, and content-free audit events.

The board provides drag/drop plus an accessible stage menu. The UI validates the matrix before optimistic movement, asks for confirmation on important states, rolls back API failures, and reloads after 409. Legacy Version 1 integer Application history remains available through compatibility dispatch.
