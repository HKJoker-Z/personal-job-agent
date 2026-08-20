# Phase 4A — History and Application Route Ownership

## Scope and baseline

This report evaluates only production code and test code relative to the
`origin/main` state after the ordinary merge of PR #70 at
`b41f4770ea18438bdbc500bee7cc072cf55ec4bc`. Markdown and this report are not
included in the line-count metrics.

## Route ownership

| Boundary | Before | After |
| --- | --- | --- |
| `/api/history` list | Combined handler in `legacy_application.py`, selected by `request.url.path` | Explicit legacy History list endpoint in `legacy_application.py` |
| `/api/history/{integer_id}` | Combined UUID/int handler in `legacy_application.py` | Explicit legacy History GET/PATCH/DELETE endpoints with an integer path converter |
| `/api/history/{integer_id}` exports and next action | Combined with `/api/applications`, selected by URL path | Explicit legacy History endpoints with shared direct export/update helpers |
| `/api/applications` with `status/search/limit/offset` | Legacy branch in the combined handler | Explicit legacy compatibility list endpoint remains the owner |
| `/api/applications` without legacy query parameters | Local `ApplicationService` import and setup inside the combined handler | The same legacy endpoint delegates directly to the existing `ApplicationService` |
| `/api/applications/{integer_id}` and legacy exports/next action | Combined UUID/int or path-dispatched handler | Explicit legacy compatibility endpoints |
| `/api/applications/{UUID}` and v2 subroutes | Existing Applications router was not included by application composition; legacy handler also attempted UUID dispatch | Existing Applications router owns UUID routes, with explicit UUID path converters and the existing `ApplicationService` |

The composed application's `FeatureRetirementMiddleware` was not changed.
Its existing public retirement behavior remains outside this route-ownership
refactor.

## Removed dispatch and duplication

- Removed `request.url.path` branching from the History/Application route block.
- Removed per-request UUID-versus-integer parsing from the combined legacy
  item, update, and delete handlers.
- Removed route-local `ApplicationService` import and repeated v2 user/database
  setup; the small `application_service_for` helper now expresses that scope
  once.
- Centralized legacy History owner ID and administrator `include_unowned`
  scope in `history_owner_scope`; Application compatibility endpoints retain
  their prior unscoped behavior.
- Kept invalid-ID responses as explicit route-contract handlers rather than
  introducing a generic dispatcher or exception fallback.

The refactor uses no new service layer, adapter, registry, repository wrapper,
ID framework, dependency container, or production test callback.

## Code metrics

Production diff relative to the post-PR #70 `origin/main`:

| File | Added | Removed | Net |
| --- | ---: | ---: | ---: |
| `backend/legacy_application.py` | 155 | 169 | -14 |
| `backend/app/application.py` | 2 | 1 | +1 |
| `backend/app/api/routers/applications.py` | 19 | 14 | +5 |
| `backend/app/applications/schemas.py` | 0 | 0 | 0 |
| `backend/app/applications/service.py` | 0 | 0 | 0 |
| **Total** | **176** | **184** | **-8** |

Test code changed by **+345 / -0 / +345**: one synthetic, isolated route
characterization module was added; no existing test was deleted or weakened.

## Contract evidence

The characterization tests cover and pass for:

- History list status/search/limit/offset, ordinary-user ownership, and
  administrator unowned-record visibility.
- Integer History GET/PATCH/DELETE and next-action behavior.
- `/api/applications` v2 list behavior without legacy parameters and existing
  legacy query compatibility with those parameters.
- UUID Application GET/PATCH/DELETE/archive behavior, including stale revision
  `409` handling.
- Invalid integer/UUID identifiers and the existing `404` error details.
- Validation `422`, authentication `401`, and not-found behavior.
- DOCX/PDF GET and HEAD response media types, download headers, and filenames on
  both legacy paths.

The following synthetic test runs passed:

- Route characterization: **7 tests**.
- Complete backend suite: **583 tests, 12 skipped, OK**.
- PostgreSQL integration suite in an isolated temporary PostgreSQL database:
  **12 tests, OK**.
- Existing Application service/router, authentication/ownership, export,
  feature-retirement, and v2 regression suites: all passed as part of the
  focused and complete runs.

`git diff --check` and Python `compileall` also pass.

## Compatibility retained

The change retains route paths and methods, response shapes, pagination fields,
status codes, error details, integer/UUID recognition, legacy query behavior,
ownership and administrator scope, archive/delete semantics, next-action
behavior, and DOCX/PDF media types and download headers. The integer History
compatibility route remains explicitly legacy-owned; UUID Application behavior
uses the existing v2 router/service.

## Recommendation on further History work

Do not continue extracting History persistence or transaction helpers in this
phase. The route boundary is now explicit while the legacy persistence contract
remains intact. Any further History change should start a separate
characterization phase with a new compatibility objective.
