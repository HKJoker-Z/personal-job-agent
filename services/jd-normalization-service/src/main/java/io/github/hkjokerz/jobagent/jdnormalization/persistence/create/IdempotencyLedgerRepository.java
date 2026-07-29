package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.config.ServiceProperties;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Repository
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class IdempotencyLedgerRepository {

    static final String CREATE_OPERATION = "create-job-description";

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactions;
    private final Duration processingLease;
    private final Duration completedRetention;
    private final int cleanupBatchSize;

    public IdempotencyLedgerRepository(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper,
            PlatformTransactionManager transactionManager,
            ServiceProperties properties) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
        this.transactions = new TransactionTemplate(transactionManager);
        this.processingLease = properties.getIdempotency().getProcessingLease();
        this.completedRetention = properties.getIdempotency().getCompletedRetention();
        this.cleanupBatchSize = properties.getIdempotency().getCleanupBatchSize();
        validateConfiguration(properties.getIdempotency());
    }

    public Claim claim(
            byte[] keyHash,
            byte[] requestFingerprint,
            UUID attemptToken,
            Instant now) {
        return transactions.execute(status -> claimInTransaction(
                keyHash,
                requestFingerprint,
                attemptToken,
                now));
    }

    public CompletedCreateResponse finalizeCreate(
            UUID ledgerId,
            UUID attemptToken,
            NormalizedCreate create,
            String requestId,
            int maximumResponseBytes,
            Instant now) {
        return transactions.execute(status -> finalizeInTransaction(
                ledgerId,
                attemptToken,
                create,
                requestId,
                maximumResponseBytes,
                now));
    }

    public int cleanupExpiredCompleted(Instant now) {
        return transactions.execute(status -> jdbcTemplate.update("""
                DELETE FROM request_idempotency
                WHERE id IN (
                    SELECT id
                    FROM request_idempotency
                    WHERE status = 'completed'
                      AND expires_at <= ?
                    ORDER BY expires_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT ?
                )
                """,
                utc(now),
                cleanupBatchSize));
    }

    private Claim claimInTransaction(
            byte[] keyHash,
            byte[] requestFingerprint,
            UUID attemptToken,
            Instant now) {
        UUID ledgerId = UUID.randomUUID();
        Instant leaseExpiresAt = now.plus(processingLease);
        int inserted = jdbcTemplate.update("""
                INSERT INTO request_idempotency (
                    id,
                    operation,
                    idempotency_key_hash,
                    request_fingerprint,
                    status,
                    attempt_token,
                    lease_expires_at,
                    created_at,
                    updated_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, 'processing', ?, ?, ?, ?, ?)
                ON CONFLICT (operation, idempotency_key_hash) DO NOTHING
                """,
                ledgerId,
                CREATE_OPERATION,
                keyHash,
                requestFingerprint,
                attemptToken,
                utc(leaseExpiresAt),
                utc(now),
                utc(now),
                utc(now.plus(completedRetention)));
        if (inserted == 1) {
            return Claim.acquired(ledgerId, attemptToken);
        }

        LedgerRow existing = lockedRow(keyHash);
        if (!Arrays.equals(existing.requestFingerprint(), requestFingerprint)) {
            return Claim.reused();
        }
        if ("completed".equals(existing.status())) {
            return Claim.replay(existing.completedResponse(objectMapper));
        }
        if (existing.leaseExpiresAt().isAfter(now)) {
            return Claim.inProgress(retryAfter(existing.leaseExpiresAt(), now));
        }

        int takenOver = jdbcTemplate.update("""
                UPDATE request_idempotency
                SET attempt_token = ?,
                    lease_expires_at = ?,
                    updated_at = ?,
                    expires_at = ?
                WHERE id = ?
                  AND status = 'processing'
                  AND attempt_token = ?
                  AND lease_expires_at <= ?
                """,
                attemptToken,
                utc(leaseExpiresAt),
                utc(now),
                utc(now.plus(completedRetention)),
                existing.id(),
                existing.attemptToken(),
                utc(now));
        if (takenOver != 1) {
            throw new ClaimOwnershipException();
        }
        return Claim.acquired(existing.id(), attemptToken);
    }

    private CompletedCreateResponse finalizeInTransaction(
            UUID ledgerId,
            UUID attemptToken,
            NormalizedCreate create,
            String requestId,
            int maximumResponseBytes,
            Instant now) {
        LedgerRow ledger = lockedRow(ledgerId);
        if (!"processing".equals(ledger.status())
                || !ledger.attemptToken().equals(attemptToken)) {
            throw new ClaimOwnershipException();
        }

        UUID aggregateId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        String location = "/api/v1/job-descriptions/" + aggregateId;
        String etag = "\"0\"";
        JsonNode successBody = create.currentResponse(
                aggregateId,
                now,
                objectMapper);
        if (storedJsonBytes(json(successBody)) > maximumResponseBytes) {
            JsonNode failure = create.errorResponse(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The idempotent result could not be persisted.",
                    requestId,
                    java.util.Map.of(),
                    objectMapper);
            return complete(
                    ledgerId,
                    attemptToken,
                    500,
                    failure,
                    null,
                    null,
                    null,
                    maximumResponseBytes,
                    now);
        }

        int rootInserted = jdbcTemplate.update("""
                INSERT INTO job_descriptions (
                    id,
                    canonical_url,
                    current_version_id,
                    current_deduplication_fingerprint,
                    optimistic_lock_version,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                aggregateId,
                create.canonicalUrl(),
                versionId,
                create.deduplicationFingerprint(),
                utc(now),
                utc(now));
        if (rootInserted == 0) {
            Duplicate duplicate = duplicate(create);
            JsonNode conflict = create.errorResponse(
                    "JOB_DESCRIPTION_ALREADY_EXISTS",
                    "The Job Description already exists.",
                    requestId,
                    java.util.Map.of(
                            "conflict_category", duplicate.category(),
                            "job_description_id", duplicate.jobDescriptionId().toString()),
                    objectMapper);
            return complete(
                    ledgerId,
                    attemptToken,
                    409,
                    conflict,
                    null,
                    null,
                    null,
                    maximumResponseBytes,
                    now);
        }

        jdbcTemplate.update("""
                INSERT INTO job_description_versions (
                    id,
                    job_description_id,
                    version_number,
                    title,
                    company,
                    location,
                    normalized_text,
                    content_hash,
                    deduplication_fingerprint,
                    normalization_policy_version,
                    skill_dictionary_version,
                    required_skills,
                    preferred_skills,
                    mentioned_skills,
                    created_at
                ) VALUES (
                    ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?,
                    CAST(? AS jsonb), CAST(? AS jsonb), CAST(? AS jsonb), ?
                )
                """,
                versionId,
                aggregateId,
                create.title(),
                create.company(),
                create.location(),
                create.normalizedText(),
                create.contentHash(),
                create.deduplicationFingerprint(),
                create.normalizationPolicyVersion(),
                create.skillDictionaryVersion(),
                create.requiredSkillsJson(objectMapper),
                create.preferredSkillsJson(objectMapper),
                create.mentionedSkillsJson(objectMapper),
                utc(now));

        return complete(
                ledgerId,
                attemptToken,
                201,
                successBody,
                location,
                etag,
                aggregateId,
                maximumResponseBytes,
                now);
    }

    private CompletedCreateResponse complete(
            UUID ledgerId,
            UUID attemptToken,
            int responseStatus,
            JsonNode responseBody,
            String responseLocation,
            String responseEtag,
            UUID aggregateId,
            int maximumResponseBytes,
            Instant now) {
        if (!responseBody.isObject()) {
            throw new IllegalStateException("Stored idempotency responses must be JSON objects");
        }
        String responseJson = json(responseBody);
        if (storedJsonBytes(responseJson) > maximumResponseBytes) {
            throw new IllegalStateException("Idempotency response exceeds the configured limit");
        }
        int updated = jdbcTemplate.update("""
                UPDATE request_idempotency
                SET status = 'completed',
                    response_status = ?,
                    response_body = CAST(? AS jsonb),
                    response_location = ?,
                    response_etag = ?,
                    job_description_id = ?,
                    updated_at = ?,
                    expires_at = ?,
                    completed_at = ?
                WHERE id = ?
                  AND status = 'processing'
                  AND attempt_token = ?
                """,
                responseStatus,
                responseJson,
                responseLocation,
                responseEtag,
                aggregateId,
                utc(now),
                utc(now.plus(completedRetention)),
                utc(now),
                ledgerId,
                attemptToken);
        if (updated != 1) {
            throw new ClaimOwnershipException();
        }
        String storedResponseJson = jdbcTemplate.queryForObject("""
                SELECT response_body::text
                FROM request_idempotency
                WHERE id = ?
                """,
                String.class,
                ledgerId);
        return new CompletedCreateResponse(
                responseStatus,
                parseJson(storedResponseJson),
                responseLocation,
                responseEtag,
                aggregateId,
                false);
    }

    private Duplicate duplicate(NormalizedCreate create) {
        if (create.canonicalUrl() != null) {
            List<UUID> canonicalMatches = jdbcTemplate.queryForList("""
                    SELECT id
                    FROM job_descriptions
                    WHERE canonical_url = ?
                    """,
                    UUID.class,
                    create.canonicalUrl());
            if (!canonicalMatches.isEmpty()) {
                return new Duplicate("canonical_url", canonicalMatches.getFirst());
            }
        }
        List<UUID> fingerprintMatches = jdbcTemplate.queryForList("""
                SELECT id
                FROM job_descriptions
                WHERE current_deduplication_fingerprint = ?
                """,
                UUID.class,
                create.deduplicationFingerprint());
        if (!fingerprintMatches.isEmpty()) {
            return new Duplicate(
                    "deduplication_fingerprint",
                    fingerprintMatches.getFirst());
        }
        throw new IllegalStateException("Aggregate conflict could not be classified");
    }

    private LedgerRow lockedRow(byte[] keyHash) {
        List<LedgerRow> rows = jdbcTemplate.query("""
                SELECT
                    id,
                    request_fingerprint,
                    status,
                    attempt_token,
                    lease_expires_at,
                    response_status,
                    response_body::text AS response_body,
                    response_location,
                    response_etag,
                    job_description_id
                FROM request_idempotency
                WHERE operation = ?
                  AND idempotency_key_hash = ?
                FOR UPDATE
                """,
                (resultSet, rowNumber) -> ledgerRow(resultSet),
                CREATE_OPERATION,
                keyHash);
        if (rows.size() != 1) {
            throw new IllegalStateException("Idempotency claim disappeared");
        }
        return rows.getFirst();
    }

    private LedgerRow lockedRow(UUID ledgerId) {
        List<LedgerRow> rows = jdbcTemplate.query("""
                SELECT
                    id,
                    request_fingerprint,
                    status,
                    attempt_token,
                    lease_expires_at,
                    response_status,
                    response_body::text AS response_body,
                    response_location,
                    response_etag,
                    job_description_id
                FROM request_idempotency
                WHERE id = ?
                FOR UPDATE
                """,
                (resultSet, rowNumber) -> ledgerRow(resultSet),
                ledgerId);
        if (rows.size() != 1) {
            throw new ClaimOwnershipException();
        }
        return rows.getFirst();
    }

    private static LedgerRow ledgerRow(java.sql.ResultSet resultSet)
            throws java.sql.SQLException {
        return new LedgerRow(
                resultSet.getObject("id", UUID.class),
                resultSet.getBytes("request_fingerprint"),
                resultSet.getString("status"),
                resultSet.getObject("attempt_token", UUID.class),
                resultSet.getObject("lease_expires_at", OffsetDateTime.class).toInstant(),
                (Integer) resultSet.getObject("response_status"),
                resultSet.getString("response_body"),
                resultSet.getString("response_location"),
                resultSet.getString("response_etag"),
                resultSet.getObject("job_description_id", UUID.class));
    }

    private JsonNode parseJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored idempotency response is invalid");
        }
    }

    private String json(JsonNode value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Idempotency response could not be encoded");
        }
    }

    private int storedJsonBytes(String value) {
        Integer bytes = jdbcTemplate.queryForObject(
                "SELECT octet_length(CAST(CAST(? AS jsonb) AS text))",
                Integer.class,
                value);
        if (bytes == null) {
            throw new IllegalStateException("Idempotency response size is unavailable");
        }
        return bytes;
    }

    private static int retryAfter(Instant leaseExpiresAt, Instant now) {
        long milliseconds = Math.max(1, Duration.between(now, leaseExpiresAt).toMillis());
        long seconds = Math.max(1, (milliseconds + 999) / 1000);
        return (int) Math.min(seconds, 120);
    }

    private static OffsetDateTime utc(Instant value) {
        return OffsetDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    private static void validateConfiguration(ServiceProperties.Idempotency properties) {
        Duration lease = properties.getProcessingLease();
        Duration retention = properties.getCompletedRetention();
        if (lease == null
                || lease.compareTo(Duration.ofSeconds(1)) < 0
                || lease.compareTo(Duration.ofMinutes(2)) > 0) {
            throw new IllegalStateException(
                    "Idempotency processing lease must be between 1 and 120 seconds");
        }
        if (retention == null
                || retention.compareTo(Duration.ofHours(1)) < 0
                || retention.compareTo(Duration.ofDays(7)) > 0) {
            throw new IllegalStateException(
                    "Idempotency retention must be between 1 hour and 7 days");
        }
        if (properties.getCleanupBatchSize() < 1
                || properties.getCleanupBatchSize() > 100) {
            throw new IllegalStateException(
                    "Idempotency cleanup batch size must be between 1 and 100");
        }
        if (properties.getMaximumResponseBytes() < 1024
                || properties.getMaximumResponseBytes() > 262_144) {
            throw new IllegalStateException(
                    "Idempotency response limit must be between 1 KiB and 256 KiB");
        }
    }

    public record Claim(
            Outcome outcome,
            UUID ledgerId,
            UUID attemptToken,
            CompletedCreateResponse response,
            Integer retryAfterSeconds) {

        static Claim acquired(UUID ledgerId, UUID attemptToken) {
            return new Claim(Outcome.ACQUIRED, ledgerId, attemptToken, null, null);
        }

        static Claim replay(CompletedCreateResponse response) {
            return new Claim(Outcome.REPLAY, null, null, response.asReplay(), null);
        }

        static Claim reused() {
            return new Claim(Outcome.REUSED, null, null, null, null);
        }

        static Claim inProgress(int retryAfterSeconds) {
            return new Claim(
                    Outcome.IN_PROGRESS,
                    null,
                    null,
                    null,
                    retryAfterSeconds);
        }
    }

    public enum Outcome {
        ACQUIRED,
        REPLAY,
        REUSED,
        IN_PROGRESS
    }

    private record LedgerRow(
            UUID id,
            byte[] requestFingerprint,
            String status,
            UUID attemptToken,
            Instant leaseExpiresAt,
            Integer responseStatus,
            String responseBody,
            String responseLocation,
            String responseEtag,
            UUID jobDescriptionId) {

        private LedgerRow {
            requestFingerprint = requestFingerprint.clone();
        }

        CompletedCreateResponse completedResponse(ObjectMapper objectMapper) {
            try {
                return new CompletedCreateResponse(
                        responseStatus,
                        objectMapper.readTree(responseBody),
                        responseLocation,
                        responseEtag,
                        jobDescriptionId,
                        false);
            } catch (JsonProcessingException exception) {
                throw new IllegalStateException("Stored idempotency response is invalid");
            }
        }
    }

    private record Duplicate(String category, UUID jobDescriptionId) {
    }

    public static final class ClaimOwnershipException extends RuntimeException {

        public ClaimOwnershipException() {
            super("Idempotency claim ownership changed");
        }
    }
}
