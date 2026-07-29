package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CompletedCreateResponse;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateFingerprints;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.IdempotencyLedgerRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.JobDescriptionCreateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.NormalizedCreate;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=" + PostgreSqlIntegrationSupport.API_KEY,
    "jd-normalization.persistence.enabled=true",
    "jd-normalization.idempotency.cleanup-batch-size=2",
    "jd-normalization.idempotency.maximum-response-bytes=1024"
})
@AutoConfigureMockMvc
@ActiveProfiles("integration")
@Testcontainers(disabledWithoutDocker = true)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PostgreSqlIdempotencyConcurrencyIT extends PostgreSqlIntegrationSupport {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private JobDescriptionNormalizer normalizer;

    @Autowired
    private CreateFingerprints fingerprints;

    @Autowired
    private IdempotencyLedgerRepository ledgerRepository;

    @Autowired
    private JobDescriptionCreateService createService;

    @Test
    void sameKeyAcrossSeparateSessionsCreatesOneAggregate() throws Exception {
        String key = "610e8400-e29b-41d4-a716-446655440000";
        String body = request(
                "Required:\n- Java\n- PostgreSQL\nConcurrent same key",
                "Concurrent Same-Key Engineer");
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");
        int ledgerBefore = count("request_idempotency");

        List<ConcurrentResult> results = concurrentPosts(
                List.of(new Request(key, body), new Request(key, body)));
        assertThat(results).allSatisfy(result ->
                assertThat(result.status()).isIn(201, 409));
        if (results.stream().allMatch(result -> result.status() == 201)) {
            assertThat(results.stream()
                            .filter(result -> "true".equals(
                                    result.result().getResponse().getHeader(
                                            "Idempotency-Replayed")))
                            .count())
                    .isEqualTo(1);
        } else {
            ConcurrentResult loser = results.stream()
                    .filter(result -> result.status() == 409)
                    .findFirst()
                    .orElseThrow();
            assertThat(json(loser.result()).path("error").path("code").textValue())
                    .isEqualTo("IDEMPOTENCY_REQUEST_IN_PROGRESS");
        }

        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 1);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore + 1);
        assertThat(count("request_idempotency")).isEqualTo(ledgerBefore + 1);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE idempotency_key_hash = ?
                  AND status = 'completed'
                """,
                Integer.class,
                fingerprints.idempotencyKeyHash(key))).isEqualTo(1);
    }

    @Test
    void concurrentDifferentKeysForSameFingerprintCreateOneAggregateAndCompleteConflict()
            throws Exception {
        String firstKey = "620e8400-e29b-41d4-a716-446655440000";
        String secondKey = "630e8400-e29b-41d4-a716-446655440000";
        String body = request(
                "Required:\n- Java\n- Redis\nConcurrent duplicate",
                "Concurrent Duplicate Engineer");
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");

        List<ConcurrentResult> results = concurrentPosts(List.of(
                new Request(firstKey, body),
                new Request(secondKey, body)));
        assertThat(results.stream().map(ConcurrentResult::status).sorted().toList())
                .containsExactly(201, 409);
        ConcurrentResult conflict = results.stream()
                .filter(result -> result.status() == 409)
                .findFirst()
                .orElseThrow();
        assertThat(json(conflict.result()).path("error").path("code").textValue())
                .isEqualTo("JOB_DESCRIPTION_ALREADY_EXISTS");

        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 1);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore + 1);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE idempotency_key_hash IN (?, ?)
                  AND status = 'completed'
                """,
                Integer.class,
                fingerprints.idempotencyKeyHash(firstKey),
                fingerprints.idempotencyKeyHash(secondKey))).isEqualTo(2);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE idempotency_key_hash IN (?, ?)
                  AND status = 'processing'
                """,
                Integer.class,
                fingerprints.idempotencyKeyHash(firstKey),
                fingerprints.idempotencyKeyHash(secondKey))).isZero();

        mockMvc.perform(authorizedPost(conflict.key(), body))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers
                        .status()
                        .isConflict())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers
                        .header()
                        .string("Idempotency-Replayed", "true"));
    }

    @Test
    void expiredLeaseCanBeTakenOverAndStaleAttemptCannotFinalize() {
        String key = "640e8400-e29b-41d4-a716-446655440000";
        NormalizeJobDescriptionRequest request = requestDto(
                "Required:\n- Java\nStale takeover",
                "Stale Takeover Engineer");
        NormalizedCreate normalized = normalized(request);
        UUID staleAttempt = UUID.randomUUID();
        UUID ledgerId = insertProcessing(
                key,
                normalized.requestFingerprint(),
                staleAttempt,
                Instant.now().minusSeconds(1));
        int rootsBefore = count("job_descriptions");

        CompletedCreateResponse response =
                createService.create(key, request, "stale-takeover:1");
        assertThat(response.status()).isEqualTo(201);
        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 1);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT status
                FROM request_idempotency
                WHERE id = ?
                """,
                String.class,
                ledgerId)).isEqualTo("completed");
        assertThat(jdbcTemplate.queryForObject("""
                SELECT attempt_token
                FROM request_idempotency
                WHERE id = ?
                """,
                UUID.class,
                ledgerId)).isNotEqualTo(staleAttempt);

        int rootsAfterTakeover = count("job_descriptions");
        assertThatThrownBy(() -> ledgerRepository.finalizeCreate(
                        ledgerId,
                        staleAttempt,
                        normalized,
                        "stale-attempt:1",
                        262_144,
                        Instant.now()))
                .isInstanceOf(IdempotencyLedgerRepository.ClaimOwnershipException.class);
        assertThat(count("job_descriptions")).isEqualTo(rootsAfterTakeover);
    }

    @Test
    void activeLeaseReturnsBoundedRetryAfterAndSurvivesCleanup() {
        String key = "650e8400-e29b-41d4-a716-446655440000";
        NormalizeJobDescriptionRequest request = requestDto(
                "Required:\n- Java\nActive processing",
                "Active Lease Engineer");
        NormalizedCreate normalized = normalized(request);
        UUID ledgerId = insertProcessing(
                key,
                normalized.requestFingerprint(),
                UUID.randomUUID(),
                Instant.now().plusSeconds(30));

        assertThatThrownBy(() ->
                        createService.create(key, request, "active-lease:1"))
                .isInstanceOfSatisfying(CreateApiException.class, exception -> {
                    assertThat(exception.code())
                            .isEqualTo("IDEMPOTENCY_REQUEST_IN_PROGRESS");
                    assertThat(exception.retryAfterSeconds()).isBetween(1, 120);
                });
        ledgerRepository.cleanupExpiredCompleted(Instant.now().plusSeconds(60));
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE id = ?
                  AND status = 'processing'
                """,
                Integer.class,
                ledgerId)).isEqualTo(1);
    }

    @Test
    void cleanupIsBoundedDeletesOnlyExpiredCompletedAndDelayedCleanupStillReplays() {
        Instant now = Instant.now();
        byte[] replayKey = fingerprints.idempotencyKeyHash(
                "660e8400-e29b-41d4-a716-446655440000");
        byte[] replayFingerprint = PostgreSqlFixture.digest("expired-replay-request");
        insertCompleted(replayKey, replayFingerprint, now.minusSeconds(1));
        for (int index = 0; index < 3; index++) {
            insertCompleted(
                    PostgreSqlFixture.digest("expired-cleanup-key-" + index),
                    PostgreSqlFixture.digest("expired-cleanup-request-" + index),
                    now.minusSeconds(1));
        }
        UUID activeId = insertProcessing(
                "670e8400-e29b-41d4-a716-446655440000",
                PostgreSqlFixture.digest("active-cleanup-request"),
                UUID.randomUUID(),
                now.plusSeconds(30));

        IdempotencyLedgerRepository.Claim replay = ledgerRepository.claim(
                replayKey,
                replayFingerprint,
                UUID.randomUUID(),
                now);
        assertThat(replay.outcome())
                .isEqualTo(IdempotencyLedgerRepository.Outcome.REPLAY);
        assertThat(replay.response().status()).isEqualTo(409);

        int expiredBefore = jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE status = 'completed'
                  AND expires_at <= ?
                """,
                Integer.class,
                utc(now));
        assertThat(expiredBefore).isEqualTo(4);
        assertThat(ledgerRepository.cleanupExpiredCompleted(now)).isEqualTo(2);
        assertThat(ledgerRepository.cleanupExpiredCompleted(now)).isEqualTo(2);
        assertThat(ledgerRepository.cleanupExpiredCompleted(now)).isZero();
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE id = ?
                  AND status = 'processing'
                """,
                Integer.class,
                activeId)).isEqualTo(1);
    }

    @Test
    void oversizedStoredResponseFailsSafelyWithoutCreatingAnAggregateAndReplays()
            throws Exception {
        String key = "680e8400-e29b-41d4-a716-446655440000";
        String body = request(
                "Required:\n- Java\n" + "bounded response text ".repeat(100),
                "Bounded Response Engineer");
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");

        MvcResult first = mockMvc.perform(authorizedPost(key, body)).andReturn();
        assertThat(first.getResponse().getStatus()).isEqualTo(500);
        assertThat(json(first).path("error").path("code").textValue())
                .isEqualTo("IDEMPOTENCY_PERSISTENCE_FAILED");
        assertThat(count("job_descriptions")).isEqualTo(rootsBefore);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT status
                FROM request_idempotency
                WHERE idempotency_key_hash = ?
                """,
                String.class,
                fingerprints.idempotencyKeyHash(key))).isEqualTo("completed");

        MvcResult replay = mockMvc.perform(authorizedPost(key, body)).andReturn();
        assertThat(replay.getResponse().getStatus()).isEqualTo(500);
        assertThat(replay.getResponse().getHeader("Idempotency-Replayed"))
                .isEqualTo("true");
        assertThat(replay.getResponse().getContentAsString())
                .isEqualTo(first.getResponse().getContentAsString());
        assertThat(count("job_descriptions")).isEqualTo(rootsBefore);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore);
    }

    @Test
    void finalizationRollbackLeavesNoOrphanRootOrVersion() {
        String key = "690e8400-e29b-41d4-a716-446655440000";
        NormalizedCreate valid = normalized(requestDto(
                "Required:\n- Java\nAtomic rollback",
                "Atomic Rollback Engineer"));
        NormalizedCreate invalid = new NormalizedCreate(
                valid.normalizedText(),
                new byte[31],
                valid.deduplicationFingerprint(),
                valid.requestFingerprint(),
                valid.normalizationPolicyVersion(),
                valid.skillDictionaryVersion(),
                valid.requiredSkills(),
                valid.preferredSkills(),
                valid.mentionedSkills(),
                valid.title(),
                valid.company(),
                valid.location(),
                valid.canonicalUrl());
        UUID attempt = UUID.randomUUID();
        IdempotencyLedgerRepository.Claim claim = ledgerRepository.claim(
                fingerprints.idempotencyKeyHash(key),
                invalid.requestFingerprint(),
                attempt,
                Instant.now());
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");

        assertThat(claim.outcome())
                .isEqualTo(IdempotencyLedgerRepository.Outcome.ACQUIRED);
        assertThatThrownBy(() -> ledgerRepository.finalizeCreate(
                        claim.ledgerId(),
                        attempt,
                        invalid,
                        "atomic-rollback:1",
                        262_144,
                        Instant.now()))
                .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);

        assertThat(count("job_descriptions")).isEqualTo(rootsBefore);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT status
                FROM request_idempotency
                WHERE id = ?
                """,
                String.class,
                claim.ledgerId())).isEqualTo("processing");
    }

    private List<ConcurrentResult> concurrentPosts(List<Request> requests) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(requests.size());
        CountDownLatch ready = new CountDownLatch(requests.size());
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<ConcurrentResult>> futures = new ArrayList<>();
            for (Request request : requests) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    MvcResult result = mockMvc.perform(
                                    authorizedPost(request.key(), request.body()))
                            .andReturn();
                    return new ConcurrentResult(
                            request.key(),
                            result.getResponse().getStatus(),
                            result);
                }));
            }
            ready.await();
            start.countDown();
            List<ConcurrentResult> results = new ArrayList<>();
            for (Future<ConcurrentResult> future : futures) {
                results.add(future.get());
            }
            return results.stream()
                    .sorted(Comparator.comparing(ConcurrentResult::key))
                    .toList();
        } finally {
            executor.shutdownNow();
        }
    }

    private UUID insertProcessing(
            String rawKey,
            byte[] requestFingerprint,
            UUID attemptToken,
            Instant leaseExpiresAt) {
        UUID id = UUID.randomUUID();
        Instant created = Instant.now().minusSeconds(60);
        jdbcTemplate.update("""
                INSERT INTO request_idempotency (
                    id, operation, idempotency_key_hash, request_fingerprint,
                    status, attempt_token, lease_expires_at,
                    created_at, updated_at, expires_at
                ) VALUES (
                    ?, 'create-job-description', ?, ?,
                    'processing', ?, ?, ?, ?, ?
                )
                """,
                id,
                fingerprints.idempotencyKeyHash(rawKey),
                requestFingerprint,
                attemptToken,
                utc(leaseExpiresAt),
                utc(created),
                utc(created),
                utc(created.plusSeconds(86_400)));
        return id;
    }

    private void insertCompleted(
            byte[] keyHash,
            byte[] requestFingerprint,
            Instant expiresAt) {
        Instant created = expiresAt.minusSeconds(3_600);
        Instant completed = created.plusSeconds(1);
        jdbcTemplate.update("""
                INSERT INTO request_idempotency (
                    id, operation, idempotency_key_hash, request_fingerprint,
                    status, attempt_token, lease_expires_at,
                    response_status, response_body,
                    created_at, updated_at, expires_at, completed_at
                ) VALUES (
                    ?, 'create-job-description', ?, ?,
                    'completed', ?, ?,
                    409, CAST(
                        '{"error":{"code":"JOB_DESCRIPTION_ALREADY_EXISTS",'
                        || '"message":"The Job Description already exists.",'
                        || '"request_id":"retained-result","details":{}}}'
                        AS jsonb
                    ),
                    ?, ?, ?, ?
                )
                """,
                UUID.randomUUID(),
                keyHash,
                requestFingerprint,
                UUID.randomUUID(),
                utc(created.plusSeconds(30)),
                utc(created),
                utc(completed),
                utc(expiresAt),
                utc(completed));
    }

    private NormalizedCreate normalized(NormalizeJobDescriptionRequest request) {
        NormalizationResult result = normalizer.normalize(request);
        return NormalizedCreate.from(result, fingerprints.forCreate(result));
    }

    private NormalizeJobDescriptionRequest requestDto(String rawText, String title) {
        return new NormalizeJobDescriptionRequest(
                rawText,
                new NormalizeJobDescriptionRequest.Metadata(
                        title,
                        "Concurrency Example",
                        null,
                        null));
    }

    private String request(String rawText, String title) throws Exception {
        return objectMapper.writeValueAsString(requestDto(rawText, title));
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedPost(String key, String body) {
        return post("/api/v1/job-descriptions")
                .header("Authorization", "Bearer " + API_KEY)
                .header("Idempotency-Key", key)
                .contentType("application/json")
                .content(body);
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private int count(String table) {
        assertThat(List.of(
                        "job_descriptions",
                        "job_description_versions",
                        "request_idempotency"))
                .contains(table);
        return jdbcTemplate.queryForObject(
                "SELECT count(*) FROM " + table,
                Integer.class);
    }

    private static OffsetDateTime utc(Instant value) {
        return OffsetDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    private record Request(String key, String body) {
    }

    private record ConcurrentResult(String key, int status, MvcResult result) {
    }
}
