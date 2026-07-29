package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateFingerprints;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.NormalizedCreate;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.ConditionalUpdateRepository;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import java.time.Instant;
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
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=" + PostgreSqlIntegrationSupport.API_KEY,
    "jd-normalization.persistence.enabled=true"
})
@AutoConfigureMockMvc
@ActiveProfiles("integration")
@Testcontainers(disabledWithoutDocker = true)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PostgreSqlUpdateConcurrencyIT extends PostgreSqlIntegrationSupport {

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
    private ConditionalUpdateRepository updateRepository;

    @Test
    void separateActorsUsingOneEtagAllowExactlyOneImmutableSuccessor()
            throws Exception {
        MvcResult created = create(
                "810e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java",
                        "Concurrent Update Engineer"));
        UUID aggregateId = id(created);
        String firstBody = request(
                "Required:\n- Java 21\n- PostgreSQL",
                "Concurrent Winner A");
        String secondBody = request(
                "Required:\n- Java 21\n- Redis",
                "Concurrent Winner B");

        List<ConcurrentResult> results = concurrentUpdates(
                aggregateId,
                List.of(firstBody, secondBody));
        assertThat(results.stream()
                        .map(ConcurrentResult::status)
                        .sorted()
                        .toList())
                .containsExactly(200, 412);
        ConcurrentResult winner = results.stream()
                .filter(result -> result.status() == 200)
                .findFirst()
                .orElseThrow();
        ConcurrentResult loser = results.stream()
                .filter(result -> result.status() == 412)
                .findFirst()
                .orElseThrow();
        assertThat(json(loser.result()).path("error").path("code").textValue())
                .isEqualTo("PRECONDITION_FAILED");

        MvcResult current = mockMvc.perform(get(
                                "/api/v1/job-descriptions/{id}",
                                aggregateId)
                        .header("Authorization", "Bearer " + API_KEY))
                .andReturn();
        assertThat(current.getResponse().getStatus()).isEqualTo(200);
        assertThat(current.getResponse().getHeader("ETag")).isEqualTo("\"1\"");
        assertThat(json(current)).isEqualTo(json(winner.result()));
        assertThat(jdbcTemplate.queryForList("""
                SELECT version_number
                FROM job_description_versions
                WHERE job_description_id = ?
                ORDER BY version_number
                """,
                Integer.class,
                aggregateId)).containsExactly(1, 2);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_descriptions j
                JOIN job_description_versions v
                  ON v.id = j.current_version_id
                 AND v.job_description_id = j.id
                 AND v.deduplication_fingerprint =
                     j.current_deduplication_fingerprint
                WHERE j.id = ?
                  AND j.optimistic_lock_version = 1
                  AND v.version_number = 2
                """,
                Integer.class,
                aggregateId)).isEqualTo(1);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_description_versions v
                LEFT JOIN job_descriptions j
                  ON j.id = v.job_description_id
                WHERE j.id IS NULL
                """,
                Integer.class)).isZero();
    }

    @Test
    void forcedVersionInsertFailureRollsBackTheEarlierRootUpdate()
            throws Exception {
        MvcResult created = create(
                "820e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java",
                        "Rollback Update Engineer"));
        UUID aggregateId = id(created);
        String rootBefore = rootJson(aggregateId);
        String versionBefore = versionJson(aggregateId, 1);
        NormalizedCreate valid = normalized(new NormalizeJobDescriptionRequest(
                "Required:\n- Java 21\n- PostgreSQL",
                new NormalizeJobDescriptionRequest.Metadata(
                        "Rollback Replacement",
                        null,
                        null,
                        null)));
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

        assertThatThrownBy(() -> updateRepository.update(
                        aggregateId,
                        0,
                        invalid,
                        Instant.now()))
                .isInstanceOf(DataIntegrityViolationException.class);

        assertThat(rootJson(aggregateId)).isEqualTo(rootBefore);
        assertThat(versionJson(aggregateId, 1)).isEqualTo(versionBefore);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_description_versions
                WHERE job_description_id = ?
                """,
                Integer.class,
                aggregateId)).isEqualTo(1);
        MvcResult current = mockMvc.perform(get(
                                "/api/v1/job-descriptions/{id}",
                                aggregateId)
                        .header("Authorization", "Bearer " + API_KEY))
                .andReturn();
        assertThat(current.getResponse().getHeader("ETag")).isEqualTo("\"0\"");
        assertThat(json(current)).isEqualTo(json(created));
    }

    @Test
    void concurrentAggregatesCannotCommitTheSameCurrentFingerprint()
            throws Exception {
        UUID firstId = id(create(
                "830e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java\nFirst aggregate",
                        "Concurrent Aggregate One")));
        UUID secondId = id(create(
                "831e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- React\nSecond aggregate",
                        "Concurrent Aggregate Two")));
        String firstBefore = rootJson(firstId);
        String secondBefore = rootJson(secondId);
        String sharedReplacement = request(
                "Required:\n- Java 21\n- PostgreSQL\nShared replacement",
                "Concurrent Shared Replacement");

        List<TargetResult> results = concurrentTargetUpdates(List.of(
                new TargetRequest(firstId, sharedReplacement),
                new TargetRequest(secondId, sharedReplacement)));
        assertThat(results.stream().map(TargetResult::status).sorted().toList())
                .containsExactly(200, 409);
        TargetResult winner = results.stream()
                .filter(result -> result.status() == 200)
                .findFirst()
                .orElseThrow();
        TargetResult conflict = results.stream()
                .filter(result -> result.status() == 409)
                .findFirst()
                .orElseThrow();
        assertThat(json(conflict.result()).path("error").path("code").textValue())
                .isEqualTo("JOB_DESCRIPTION_ALREADY_EXISTS");
        assertThat(json(conflict.result())
                        .path("error")
                        .path("details")
                        .path("conflict_category")
                        .textValue())
                .isEqualTo("deduplication_fingerprint");

        assertThat(jdbcTemplate.queryForObject("""
                SELECT optimistic_lock_version
                FROM job_descriptions
                WHERE id = ?
                """,
                Long.class,
                winner.aggregateId())).isEqualTo(1);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_description_versions
                WHERE job_description_id = ?
                """,
                Integer.class,
                winner.aggregateId())).isEqualTo(2);
        String loserBefore = conflict.aggregateId().equals(firstId)
                ? firstBefore
                : secondBefore;
        assertThat(rootJson(conflict.aggregateId())).isEqualTo(loserBefore);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_description_versions
                WHERE job_description_id = ?
                """,
                Integer.class,
                conflict.aggregateId())).isEqualTo(1);
    }

    private List<ConcurrentResult> concurrentUpdates(
            UUID aggregateId,
            List<String> bodies) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(bodies.size());
        CountDownLatch ready = new CountDownLatch(bodies.size());
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<ConcurrentResult>> futures = new ArrayList<>();
            for (int index = 0; index < bodies.size(); index++) {
                int actor = index;
                String body = bodies.get(index);
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    MvcResult result = mockMvc.perform(put(
                                            "/api/v1/job-descriptions/{id}",
                                            aggregateId)
                                    .header("Authorization", "Bearer " + API_KEY)
                                    .header("If-Match", "\"0\"")
                                    .contentType("application/json")
                                    .content(body))
                            .andReturn();
                    return new ConcurrentResult(actor, result.getResponse().getStatus(), result);
                }));
            }
            ready.await();
            start.countDown();
            List<ConcurrentResult> results = new ArrayList<>();
            for (Future<ConcurrentResult> future : futures) {
                results.add(future.get());
            }
            return results.stream()
                    .sorted(Comparator.comparingInt(ConcurrentResult::actor))
                    .toList();
        } finally {
            executor.shutdownNow();
        }
    }

    private List<TargetResult> concurrentTargetUpdates(
            List<TargetRequest> requests) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(requests.size());
        CountDownLatch ready = new CountDownLatch(requests.size());
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<TargetResult>> futures = new ArrayList<>();
            for (TargetRequest request : requests) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    MvcResult result = mockMvc.perform(put(
                                            "/api/v1/job-descriptions/{id}",
                                            request.aggregateId())
                                    .header("Authorization", "Bearer " + API_KEY)
                                    .header("If-Match", "\"0\"")
                                    .contentType("application/json")
                                    .content(request.body()))
                            .andReturn();
                    return new TargetResult(
                            request.aggregateId(),
                            result.getResponse().getStatus(),
                            result);
                }));
            }
            ready.await();
            start.countDown();
            List<TargetResult> results = new ArrayList<>();
            for (Future<TargetResult> future : futures) {
                results.add(future.get());
            }
            return results.stream()
                    .sorted(Comparator.comparing(TargetResult::aggregateId))
                    .toList();
        } finally {
            executor.shutdownNow();
        }
    }

    private MvcResult create(String key, String body) throws Exception {
        return mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", key)
                        .contentType("application/json")
                        .content(body))
                .andReturn();
    }

    private String request(String rawText, String title) throws Exception {
        return objectMapper.writeValueAsString(new NormalizeJobDescriptionRequest(
                rawText,
                new NormalizeJobDescriptionRequest.Metadata(
                        title,
                        "Concurrency Example",
                        null,
                        null)));
    }

    private NormalizedCreate normalized(NormalizeJobDescriptionRequest request) {
        NormalizationResult result = normalizer.normalize(request);
        return NormalizedCreate.from(result, fingerprints.forCreate(result));
    }

    private UUID id(MvcResult result) throws Exception {
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return UUID.fromString(json(result).path("id").textValue());
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private String rootJson(UUID aggregateId) {
        return jdbcTemplate.queryForObject("""
                SELECT to_jsonb(j)::text
                FROM job_descriptions j
                WHERE id = ?
                """,
                String.class,
                aggregateId);
    }

    private String versionJson(UUID aggregateId, int versionNumber) {
        return jdbcTemplate.queryForObject("""
                SELECT to_jsonb(v)::text
                FROM job_description_versions v
                WHERE job_description_id = ?
                  AND version_number = ?
                """,
                String.class,
                aggregateId,
                versionNumber);
    }

    private record ConcurrentResult(int actor, int status, MvcResult result) {
    }

    private record TargetRequest(UUID aggregateId, String body) {
    }

    private record TargetResult(UUID aggregateId, int status, MvcResult result) {
    }
}
