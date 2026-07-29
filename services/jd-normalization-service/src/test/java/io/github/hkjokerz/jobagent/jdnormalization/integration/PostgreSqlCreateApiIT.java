package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateFingerprints;
import java.util.Arrays;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
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
@ExtendWith(OutputCaptureExtension.class)
class PostgreSqlCreateApiIT extends PostgreSqlIntegrationSupport {

    private static final String FIRST_KEY = "110e8400-e29b-41d4-a716-446655440000";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private CreateFingerprints fingerprints;

    @Test
    void firstCreateIsAtomicGetEquivalentAndExactlyReplayable() throws Exception {
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");
        int ledgerBefore = count("request_idempotency");
        String body = request(
                "Required:\n- Java 21\n- PostgreSQL",
                "Backend Engineer",
                "Example Ltd",
                "Hong Kong",
                "https://jobs.create.example.test/backend");

        MvcResult first = mockMvc.perform(authorizedPost(FIRST_KEY, body)
                        .header("X-Request-ID", "create-postgres:1"))
                .andExpect(status().isCreated())
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().string("X-Request-ID", "create-postgres:1"))
                .andExpect(header().string(
                        "Location",
                        org.hamcrest.Matchers.matchesPattern(
                                "/api/v1/job-descriptions/[0-9a-f-]{36}")))
                .andExpect(header().doesNotExist("Idempotency-Replayed"))
                .andExpect(jsonPath("$.optimistic_lock_version").value(0))
                .andExpect(jsonPath("$.current_version_number").value(1))
                .andExpect(jsonPath("$.required_skills[*].id").value(hasSize(2)))
                .andReturn();
        JsonNode firstJson = json(first);
        UUID aggregateId = UUID.fromString(firstJson.path("id").textValue());
        String location = first.getResponse().getHeader("Location");

        MvcResult current = mockMvc.perform(get(location)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"0\""))
                .andReturn();
        assertThat(json(current)).isEqualTo(firstJson);

        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 1);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore + 1);
        assertThat(count("request_idempotency")).isEqualTo(ledgerBefore + 1);
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT count(*)
                FROM job_description_versions
                WHERE job_description_id = ?
                  AND version_number = 1
                """,
                Integer.class,
                aggregateId)).isEqualTo(1);
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT status
                FROM request_idempotency
                WHERE job_description_id = ?
                """,
                String.class,
                aggregateId)).isEqualTo("completed");

        MvcResult replay = mockMvc.perform(authorizedPost(FIRST_KEY, body)
                        .header("X-Request-ID", "create-postgres:2"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", location))
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string("Idempotency-Replayed", "true"))
                .andReturn();
        assertThat(replay.getResponse().getContentAsString())
                .isEqualTo(first.getResponse().getContentAsString());
        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 1);
        assertThat(count("job_description_versions")).isEqualTo(versionsBefore + 1);
        assertThat(count("request_idempotency")).isEqualTo(ledgerBefore + 1);

        mockMvc.perform(authorizedPost(
                        FIRST_KEY,
                        request(
                                "Required:\n- Java 21\n- PostgreSQL\n- Spring",
                                "Backend Engineer",
                                "Example Ltd",
                                "Hong Kong",
                                "https://jobs.create.example.test/backend")))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void samePayloadDifferentKeysCreatesOneAggregateAndReplaysTheDuplicate()
            throws Exception {
        int rootsBefore = count("job_descriptions");
        int versionsBefore = count("job_description_versions");
        String body = request(
                "Required:\n- Java\nPreferred:\n- Redis",
                "Deduplicated Engineer",
                "Example Ltd",
                null,
                null);
        String firstKey = "220e8400-e29b-41d4-a716-446655440000";
        String duplicateKey = "230e8400-e29b-41d4-a716-446655440000";

        MvcResult created = mockMvc.perform(authorizedPost(firstKey, body))
                .andExpect(status().isCreated())
                .andReturn();
        UUID createdId = UUID.fromString(json(created).path("id").textValue());

        MvcResult duplicate = mockMvc.perform(authorizedPost(duplicateKey, body)
                        .header("X-Request-ID", "duplicate-postgres:1"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.error.details.conflict_category")
                        .value("deduplication_fingerprint"))
                .andExpect(jsonPath("$.error.details.job_description_id")
                        .value(createdId.toString()))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString(
                                "uq_job_descriptions"))))
                .andReturn();

        MvcResult replay = mockMvc.perform(authorizedPost(duplicateKey, body))
                .andExpect(status().isConflict())
                .andExpect(header().string("Idempotency-Replayed", "true"))
                .andReturn();
        assertThat(replay.getResponse().getContentAsString())
                .isEqualTo(duplicate.getResponse().getContentAsString());
        mockMvc.perform(authorizedPost(
                        duplicateKey,
                        request(
                                "Required:\n- Java\nPreferred:\n- Redis",
                                "Different Request",
                                "Example Ltd",
                                null,
                                null)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_REUSED"));
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
                fingerprints.idempotencyKeyHash(duplicateKey))).isEqualTo(2);
    }

    @Test
    void contentCanBeReusedWhenNormalizedMetadataChanges() throws Exception {
        int rootsBefore = count("job_descriptions");
        String rawText = "Required:\n- Java\n- PostgreSQL";
        String firstKey = "330e8400-e29b-41d4-a716-446655440000";
        String secondKey = "340e8400-e29b-41d4-a716-446655440000";

        JsonNode first = json(mockMvc.perform(authorizedPost(
                                firstKey,
                                request(
                                        rawText,
                                        "Backend Engineer",
                                        "Example Ltd",
                                        null,
                                        null)))
                        .andExpect(status().isCreated())
                        .andReturn());
        JsonNode second = json(mockMvc.perform(authorizedPost(
                                secondKey,
                                request(
                                        rawText,
                                        "Platform Engineer",
                                        "Example Ltd",
                                        null,
                                        null)))
                        .andExpect(status().isCreated())
                        .andReturn());

        assertThat(first.path("content_hash").textValue())
                .isEqualTo(second.path("content_hash").textValue());
        assertThat(first.path("id").textValue()).isNotEqualTo(second.path("id").textValue());
        assertThat(count("job_descriptions")).isEqualTo(rootsBefore + 2);
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(DISTINCT current_deduplication_fingerprint)
                FROM job_descriptions
                WHERE id IN (?, ?)
                """,
                Integer.class,
                UUID.fromString(first.path("id").textValue()),
                UUID.fromString(second.path("id").textValue()))).isEqualTo(2);
    }

    @Test
    void canonicalUrlConflictWinsForDifferentContentAndIsReplayable() throws Exception {
        String canonicalUrl = "https://jobs.create.example.test/canonical-conflict";
        String firstKey = "440e8400-e29b-41d4-a716-446655440000";
        String secondKey = "450e8400-e29b-41d4-a716-446655440000";
        mockMvc.perform(authorizedPost(
                        firstKey,
                        request(
                                "Required:\n- Java",
                                "Java Engineer",
                                null,
                                null,
                                canonicalUrl)))
                .andExpect(status().isCreated());

        MvcResult conflict = mockMvc.perform(authorizedPost(
                        secondKey,
                        request(
                                "Required:\n- React",
                                "Frontend Engineer",
                                null,
                                null,
                                canonicalUrl)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.error.details.conflict_category")
                        .value("canonical_url"))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString(canonicalUrl))))
                .andReturn();

        mockMvc.perform(authorizedPost(
                        secondKey,
                        request(
                                "Required:\n- React",
                                "Frontend Engineer",
                                null,
                                null,
                                canonicalUrl)))
                .andExpect(status().isConflict())
                .andExpect(header().string("Idempotency-Replayed", "true"))
                .andExpect(content().string(conflict.getResponse().getContentAsString()));
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE idempotency_key_hash = ?
                  AND status = 'processing'
                """,
                Integer.class,
                fingerprints.idempotencyKeyHash(secondKey))).isZero();
    }

    @Test
    void authenticatesBeforeReplayAndKeepsSensitiveValuesOutOfLedgerErrorsAndLogs(
            CapturedOutput output) throws Exception {
        String rawKey = "550e8400-e29b-41d4-a716-446655440099";
        String rawText = "Sensitive-marker-jd Required Java";
        String canonicalUrl =
                "https://jobs.create.example.test/sensitive-marker-url";
        String metadataMarker = "Sensitive Marker Company";
        String body = request(
                rawText,
                "Sensitive Marker Title",
                metadataMarker,
                null,
                canonicalUrl);

        mockMvc.perform(authorizedPost(rawKey, body))
                .andExpect(status().isCreated());
        int ledgerCount = count("request_idempotency");
        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Idempotency-Key", rawKey)
                        .contentType("application/json")
                        .content(body))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
        assertThat(count("request_idempotency")).isEqualTo(ledgerCount);

        byte[] storedHash = jdbcTemplate.queryForObject("""
                SELECT idempotency_key_hash
                FROM request_idempotency
                WHERE idempotency_key_hash = ?
                """,
                byte[].class,
                fingerprints.idempotencyKeyHash(rawKey));
        assertThat(storedHash)
                .isEqualTo(fingerprints.idempotencyKeyHash(rawKey))
                .isNotEqualTo(rawKey.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM request_idempotency
                WHERE response_body::text LIKE ?
                """,
                Integer.class,
                "%" + rawKey + "%")).isZero();

        String logs = output.getAll();
        assertThat(logs)
                .doesNotContain(rawKey)
                .doesNotContain(rawText)
                .doesNotContain(canonicalUrl)
                .doesNotContain(metadataMarker)
                .doesNotContain(API_KEY)
                .doesNotContain("Authorization")
                .doesNotContain("INSERT INTO")
                .doesNotContain("uq_job_descriptions");
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedPost(String key, String body) {
        return post("/api/v1/job-descriptions")
                .header("Authorization", "Bearer " + API_KEY)
                .header("Idempotency-Key", key)
                .contentType("application/json")
                .content(body);
    }

    private String request(
            String rawText,
            String title,
            String company,
            String location,
            String canonicalUrl) throws Exception {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("raw_text", rawText);
        ObjectNode metadata = root.putObject("metadata");
        putNullable(metadata, "title", title);
        putNullable(metadata, "company", company);
        putNullable(metadata, "location", location);
        putNullable(metadata, "canonical_url", canonicalUrl);
        return objectMapper.writeValueAsString(root);
    }

    private static void putNullable(ObjectNode node, String name, String value) {
        if (value == null) {
            node.putNull(name);
        } else {
            node.put(name, value);
        }
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private int count(String table) {
        assertThat(Arrays.asList(
                        "job_descriptions",
                        "job_description_versions",
                        "request_idempotency"))
                .contains(table);
        return jdbcTemplate.queryForObject(
                "SELECT count(*) FROM " + table,
                Integer.class);
    }
}
