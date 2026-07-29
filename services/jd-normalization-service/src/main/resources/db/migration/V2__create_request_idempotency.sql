CREATE TABLE request_idempotency (
    id uuid PRIMARY KEY,
    operation varchar(64) NOT NULL,
    idempotency_key_hash bytea NOT NULL,
    request_fingerprint bytea NOT NULL,
    status varchar(16) NOT NULL,
    attempt_token uuid NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    response_status integer,
    response_body jsonb,
    response_location varchar(2048),
    response_etag varchar(128),
    job_description_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT uq_request_idempotency_operation_key_hash
        UNIQUE (operation, idempotency_key_hash),
    CONSTRAINT ck_request_idempotency_operation
        CHECK (
            char_length(operation) BETWEEN 1 AND 64
            AND btrim(operation) = operation
            AND operation <> ''
        ),
    CONSTRAINT ck_request_idempotency_key_hash_length
        CHECK (octet_length(idempotency_key_hash) = 32),
    CONSTRAINT ck_request_idempotency_request_fingerprint_length
        CHECK (octet_length(request_fingerprint) = 32),
    CONSTRAINT ck_request_idempotency_status
        CHECK (status IN ('processing', 'completed')),
    CONSTRAINT ck_request_idempotency_processing_state
        CHECK (
            status <> 'processing'
            OR (
                response_status IS NULL
                AND response_body IS NULL
                AND response_location IS NULL
                AND response_etag IS NULL
                AND job_description_id IS NULL
                AND completed_at IS NULL
            )
        ),
    CONSTRAINT ck_request_idempotency_completed_state
        CHECK (
            status <> 'completed'
            OR (
                response_status IS NOT NULL
                AND response_body IS NOT NULL
                AND completed_at IS NOT NULL
            )
        ),
    CONSTRAINT ck_request_idempotency_response_status
        CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599),
    CONSTRAINT ck_request_idempotency_response_body
        CHECK (
            response_body IS NULL
            OR (
                jsonb_typeof(response_body) = 'object'
                AND octet_length(response_body::text) <= 262144
            )
        ),
    CONSTRAINT ck_request_idempotency_timestamps
        CHECK (
            updated_at >= created_at
            AND expires_at > created_at
            AND lease_expires_at > created_at
            AND (
                completed_at IS NULL
                OR (completed_at >= created_at AND completed_at <= updated_at)
            )
        ),
    CONSTRAINT fk_request_idempotency_job_description
        FOREIGN KEY (job_description_id)
        REFERENCES job_descriptions (id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_request_idempotency_completed_expiry
    ON request_idempotency (expires_at, id)
    WHERE status = 'completed';

CREATE INDEX idx_request_idempotency_processing_lease
    ON request_idempotency (lease_expires_at)
    WHERE status = 'processing';
