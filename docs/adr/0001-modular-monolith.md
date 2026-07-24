# ADR 0001: Use a modular monolith

## Status

Accepted

## Context

Personal Job Agent Version 2.0.3 has one FastAPI application that composes the
legacy analysis workspace with Version 2 authentication, Profile, Resume,
Dashboard, and retained Agent Run modules. These modules share application
configuration, authentication middleware, SQLAlchemy models, PostgreSQL
transactions, and a release lifecycle.

The production runtime also contains a static React frontend, Nginx, PostgreSQL,
Redis, Dramatiq workers, and an Outbox dispatcher. Separate processes and
containers alone do not create independently owned services or microservice
boundaries.

## Decision

Describe and operate the product as a modular monolith. FastAPI is the single
backend product deployment and owns the HTTP boundary and application modules.
The frontend and operational data/worker processes support that backend.

Modules use explicit service and repository layers where implemented, while
sharing one versioned application, relational schema, authentication boundary,
and deployment release.

## Consequences

- Product behavior, authorization, and transactions remain consistent across
  modules.
- Releases and local development do not require distributed service discovery
  or cross-service API contracts.
- PostgreSQL, Redis, workers, Nginx, and the frontend can still be scaled or
  operated as separate processes without being described as microservices.
- Module coupling and the transitional legacy/Version 2 composition must be
  managed inside one codebase and one backend release.
