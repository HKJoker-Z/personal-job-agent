CREATE TABLE job_descriptions (
    id uuid PRIMARY KEY,
    canonical_url varchar(2048),
    current_version_id uuid NOT NULL,
    current_deduplication_fingerprint bytea NOT NULL,
    optimistic_lock_version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_job_descriptions_current_fingerprint_length
        CHECK (octet_length(current_deduplication_fingerprint) = 32),
    CONSTRAINT ck_job_descriptions_optimistic_lock_version
        CHECK (optimistic_lock_version >= 0),
    CONSTRAINT uq_job_descriptions_current_fingerprint
        UNIQUE (current_deduplication_fingerprint),
    CONSTRAINT uq_job_descriptions_current_identity
        UNIQUE (id, current_version_id, current_deduplication_fingerprint)
);

CREATE UNIQUE INDEX uq_job_descriptions_canonical_url
    ON job_descriptions (canonical_url)
    WHERE canonical_url IS NOT NULL;

CREATE INDEX idx_job_descriptions_created_at_id
    ON job_descriptions (created_at DESC, id DESC);

CREATE TABLE job_description_versions (
    id uuid PRIMARY KEY,
    job_description_id uuid NOT NULL,
    version_number integer NOT NULL,
    title varchar(200),
    company varchar(200),
    location varchar(200),
    normalized_text text NOT NULL,
    content_hash bytea NOT NULL,
    deduplication_fingerprint bytea NOT NULL,
    normalization_policy_version varchar(64) NOT NULL,
    skill_dictionary_version varchar(64) NOT NULL,
    required_skills jsonb NOT NULL,
    preferred_skills jsonb NOT NULL,
    mentioned_skills jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_job_description_versions_version_number
        CHECK (version_number > 0),
    CONSTRAINT ck_job_description_versions_normalized_text
        CHECK (char_length(normalized_text) BETWEEN 1 AND 100000),
    CONSTRAINT ck_job_description_versions_content_hash_length
        CHECK (octet_length(content_hash) = 32),
    CONSTRAINT ck_job_description_versions_deduplication_fingerprint_length
        CHECK (octet_length(deduplication_fingerprint) = 32),
    CONSTRAINT ck_job_description_versions_normalization_policy
        CHECK (btrim(normalization_policy_version) <> ''),
    CONSTRAINT ck_job_description_versions_skill_dictionary
        CHECK (btrim(skill_dictionary_version) <> ''),
    CONSTRAINT ck_job_description_versions_required_skills_array
        CHECK (jsonb_typeof(required_skills) = 'array'),
    CONSTRAINT ck_job_description_versions_preferred_skills_array
        CHECK (jsonb_typeof(preferred_skills) = 'array'),
    CONSTRAINT ck_job_description_versions_mentioned_skills_array
        CHECK (jsonb_typeof(mentioned_skills) = 'array'),
    CONSTRAINT ck_job_description_versions_skill_count
        CHECK (
            jsonb_array_length(required_skills)
            + jsonb_array_length(preferred_skills)
            + jsonb_array_length(mentioned_skills) <= 256
        ),
    CONSTRAINT uq_job_description_versions_number
        UNIQUE (job_description_id, version_number),
    CONSTRAINT uq_job_description_versions_current_identity
        UNIQUE (id, job_description_id, deduplication_fingerprint),
    CONSTRAINT fk_job_description_versions_owner
        FOREIGN KEY (job_description_id)
        REFERENCES job_descriptions (id)
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE job_descriptions
    ADD CONSTRAINT fk_job_descriptions_current_version
    FOREIGN KEY (current_version_id, id, current_deduplication_fingerprint)
    REFERENCES job_description_versions (
        id,
        job_description_id,
        deduplication_fingerprint
    )
    ON DELETE RESTRICT
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX idx_job_description_versions_history
    ON job_description_versions (job_description_id, version_number DESC);

CREATE INDEX idx_job_description_versions_content_hash
    ON job_description_versions (content_hash);

CREATE INDEX idx_job_description_versions_title_ci
    ON job_description_versions (lower(title));

CREATE INDEX idx_job_description_versions_company_ci
    ON job_description_versions (lower(company));

CREATE INDEX idx_job_description_versions_location_ci
    ON job_description_versions (lower(location));

CREATE FUNCTION reject_job_description_version_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = 'job description versions are immutable';
END;
$$;

CREATE TRIGGER trg_job_description_versions_immutable
BEFORE UPDATE OR DELETE ON job_description_versions
FOR EACH ROW
EXECUTE FUNCTION reject_job_description_version_mutation();
