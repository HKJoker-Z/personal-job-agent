package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
class PostgreSqlUpdateApiIT extends PostgreSqlIntegrationSupport {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void changedReplacementsCreateContiguousImmutableVersionsAndAdvanceEtag()
            throws Exception {
        String createBody = request(
                "Required:\n- Java",
                "Backend Engineer",
                "Original Company",
                "Hong Kong",
                "https://jobs.update.example.test/contiguous");
        MvcResult created = create(
                "710e8400-e29b-41d4-a716-446655440000",
                createBody);
        UUID aggregateId = id(created);
        String originalVersion = versionJson(aggregateId, 1);

        String replacementOne = """
                {
                  "raw_text": "Required:\\n- Java 21\\n- PostgreSQL",
                  "metadata": {"title": "Platform Engineer"}
                }
                """;
        MvcResult firstUpdate = mockMvc.perform(authorizedPut(
                        aggregateId,
                        "\"0\"",
                        replacementOne)
                        .header("X-Request-ID", "update-postgres:1"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "update-postgres:1"))
                .andExpect(header().string("ETag", "\"1\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.optimistic_lock_version").value(1))
                .andExpect(jsonPath("$.current_version_number").value(2))
                .andExpect(jsonPath("$.canonical_url").value(nullValue()))
                .andExpect(jsonPath("$.metadata.title").value("Platform Engineer"))
                .andExpect(jsonPath("$.metadata.company").value(nullValue()))
                .andExpect(jsonPath("$.metadata.location").value(nullValue()))
                .andReturn();

        MvcResult current = mockMvc.perform(get(
                                "/api/v1/job-descriptions/{id}",
                                aggregateId)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""))
                .andReturn();
        assertThat(json(current)).isEqualTo(json(firstUpdate));
        mockMvc.perform(get("/api/v1/job-descriptions/{id}", aggregateId)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("If-None-Match", "\"1\""))
                .andExpect(status().isNotModified())
                .andExpect(header().string("ETag", "\"1\""))
                .andExpect(content().string(""));
        assertThat(versionJson(aggregateId, 1)).isEqualTo(originalVersion);
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

        mockMvc.perform(get("/api/v1/job-descriptions/{id}/versions", aggregateId)
                        .header("Authorization", "Bearer " + API_KEY)
                        .queryParam("sort", "version_asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andExpect(jsonPath("$.items[0].version_number").value(1))
                .andExpect(jsonPath("$.items[1].version_number").value(2))
                .andExpect(jsonPath("$.items[0].metadata.company")
                        .value("Original Company"))
                .andExpect(jsonPath("$.items[1].metadata.company")
                        .value(nullValue()));

        String replacementTwo = request(
                "Required:\n- Java 21\n- PostgreSQL\nPreferred:\n- Redis",
                "Senior Platform Engineer",
                null,
                "Remote",
                null);
        mockMvc.perform(authorizedPut(aggregateId, "\"1\"", replacementTwo))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"2\""))
                .andExpect(jsonPath("$.optimistic_lock_version").value(2))
                .andExpect(jsonPath("$.current_version_number").value(3));

        assertThat(jdbcTemplate.queryForList("""
                SELECT version_number
                FROM job_description_versions
                WHERE job_description_id = ?
                ORDER BY version_number
                """,
                Integer.class,
                aggregateId)).containsExactly(1, 2, 3);
        assertThat(versionJson(aggregateId, 1)).isEqualTo(originalVersion);
    }

    @Test
    void effectiveNoopPerformsNoWriteAndStaleNoopStillFails() throws Exception {
        String body = request(
                "Required:\n- Java\n- PostgreSQL",
                "No-op Engineer",
                "Example Ltd",
                null,
                null);
        MvcResult created = create(
                "720e8400-e29b-41d4-a716-446655440000",
                body);
        UUID aggregateId = id(created);
        String rootBefore = rootJson(aggregateId);
        String updatedAtBefore = updatedAt(aggregateId);

        MvcResult noOp = mockMvc.perform(authorizedPut(
                        aggregateId,
                        "\"0\"",
                        request(
                                "  Required:  \r\n- Java\r\n- PostgreSQL  ",
                                " No-op   Engineer ",
                                " Example Ltd ",
                                null,
                                null)))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andReturn();
        assertThat(json(noOp)).isEqualTo(json(created));
        assertThat(rootJson(aggregateId)).isEqualTo(rootBefore);
        assertThat(updatedAt(aggregateId)).isEqualTo(updatedAtBefore);
        assertThat(versionCount(aggregateId)).isEqualTo(1);

        String changed = request(
                "Required:\n- Java 21\n- PostgreSQL",
                "No-op Engineer",
                "Example Ltd",
                null,
                null);
        mockMvc.perform(authorizedPut(aggregateId, "\"0\"", changed))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""));
        String changedRoot = rootJson(aggregateId);
        String changedUpdatedAt = updatedAt(aggregateId);

        mockMvc.perform(authorizedPut(aggregateId, "\"0\"", changed))
                .andExpect(status().isPreconditionFailed())
                .andExpect(jsonPath("$.error.code").value("PRECONDITION_FAILED"))
                .andExpect(jsonPath("$.error.details").isMap());
        assertThat(rootJson(aggregateId)).isEqualTo(changedRoot);
        assertThat(versionCount(aggregateId)).isEqualTo(2);

        mockMvc.perform(authorizedPut(aggregateId, "\"1\"", changed))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""));
        assertThat(rootJson(aggregateId)).isEqualTo(changedRoot);
        assertThat(updatedAt(aggregateId)).isEqualTo(changedUpdatedAt);
        assertThat(versionCount(aggregateId)).isEqualTo(2);
    }

    @Test
    void canonicalAndDeduplicationConflictsAreSafeAndRollbackCompletely()
            throws Exception {
        MvcResult canonicalSource = create(
                "730e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java",
                        "Canonical Source",
                        null,
                        null,
                        "https://jobs.update.example.test/canonical-source"));
        UUID canonicalSourceId = id(canonicalSource);
        String occupiedUrl =
                "https://jobs.update.example.test/canonical-occupied";
        MvcResult canonicalOccupied = create(
                "731e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- React",
                        "Canonical Occupied",
                        null,
                        null,
                        occupiedUrl));
        UUID canonicalOccupiedId = id(canonicalOccupied);
        String canonicalRootBefore = rootJson(canonicalSourceId);
        String canonicalVersionBefore = versionJson(canonicalSourceId, 1);

        mockMvc.perform(authorizedPut(
                        canonicalSourceId,
                        "\"0\"",
                        request(
                                "Required:\n- PostgreSQL",
                                "Canonical Replacement",
                                null,
                                null,
                                occupiedUrl)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.error.details.conflict_category")
                        .value("canonical_url"))
                .andExpect(jsonPath("$.error.details.job_description_id")
                        .value(canonicalOccupiedId.toString()))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString(occupiedUrl))))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("constraint"))))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("UPDATE job_descriptions"))));
        assertThat(rootJson(canonicalSourceId)).isEqualTo(canonicalRootBefore);
        assertThat(versionJson(canonicalSourceId, 1))
                .isEqualTo(canonicalVersionBefore);
        assertThat(versionCount(canonicalSourceId)).isEqualTo(1);

        MvcResult fingerprintSource = create(
                "732e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java",
                        "Fingerprint Source",
                        "First",
                        null,
                        null));
        UUID fingerprintSourceId = id(fingerprintSource);
        String occupiedFingerprintBody = request(
                "Required:\n- Java 21\n- Redis",
                "Fingerprint Occupied",
                "Second",
                null,
                null);
        MvcResult fingerprintOccupied = create(
                "733e8400-e29b-41d4-a716-446655440000",
                occupiedFingerprintBody);
        UUID fingerprintOccupiedId = id(fingerprintOccupied);
        String fingerprintRootBefore = rootJson(fingerprintSourceId);

        mockMvc.perform(authorizedPut(
                        fingerprintSourceId,
                        "\"0\"",
                        occupiedFingerprintBody))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.error.details.conflict_category")
                        .value("deduplication_fingerprint"))
                .andExpect(jsonPath("$.error.details.job_description_id")
                        .value(fingerprintOccupiedId.toString()));
        assertThat(rootJson(fingerprintSourceId)).isEqualTo(fingerprintRootBefore);
        assertThat(versionCount(fingerprintSourceId)).isEqualTo(1);
    }

    @Test
    void updateDoesNotTouchCreateLedgerAndCreateReplayRemainsHistorical()
            throws Exception {
        String key = "740e8400-e29b-41d4-a716-446655440000";
        String originalBody = request(
                "Required:\n- Java",
                "Historical Replay Engineer",
                null,
                null,
                null);
        MvcResult created = create(key, originalBody);
        UUID aggregateId = id(created);
        String originalResponse = created.getResponse().getContentAsString();
        String originalLocation = created.getResponse().getHeader("Location");
        int ledgerBefore = ledgerCount();

        mockMvc.perform(authorizedPut(
                        aggregateId,
                        "\"0\"",
                        request(
                                "Required:\n- Java 21\n- PostgreSQL",
                                "Updated Historical Engineer",
                                null,
                                null,
                                null)))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""));
        assertThat(ledgerCount()).isEqualTo(ledgerBefore);

        MvcResult replay = mockMvc.perform(authorizedPost(key, originalBody))
                .andExpect(status().isCreated())
                .andExpect(header().string("Idempotency-Replayed", "true"))
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string("Location", originalLocation))
                .andReturn();
        assertThat(replay.getResponse().getContentAsString())
                .isEqualTo(originalResponse);

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", aggregateId)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""))
                .andExpect(jsonPath("$.current_version_number").value(2))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.equalTo(originalResponse))));

        mockMvc.perform(put("/api/v1/job-descriptions/{id}", aggregateId)
                        .contentType("application/json")
                        .content(originalBody))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
    }

    @Test
    void replacementContentAndSecretsStayOutOfLogsAndErrors(
            CapturedOutput output) throws Exception {
        String rawMarker = "sensitive-update-jd-marker";
        String metadataMarker = "Sensitive Update Company Marker";
        String urlMarker =
                "https://jobs.update.example.test/sensitive-url-marker";
        MvcResult source = create(
                "750e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- Java",
                        "Safe Source",
                        null,
                        null,
                        null));
        UUID sourceId = id(source);
        create(
                "751e8400-e29b-41d4-a716-446655440000",
                request(
                        "Required:\n- React",
                        "Safe Occupied",
                        null,
                        null,
                        urlMarker));

        MvcResult conflict = mockMvc.perform(authorizedPut(
                        sourceId,
                        "\"0\"",
                        request(
                                rawMarker,
                                "Sensitive Update Title Marker",
                                metadataMarker,
                                null,
                                urlMarker)))
                .andExpect(status().isConflict())
                .andReturn();
        String response = conflict.getResponse().getContentAsString();
        assertThat(response)
                .doesNotContain(rawMarker)
                .doesNotContain(metadataMarker)
                .doesNotContain(urlMarker)
                .doesNotContain("constraint")
                .doesNotContain("UPDATE job_descriptions");

        assertThat(output.getAll())
                .doesNotContain(rawMarker)
                .doesNotContain(metadataMarker)
                .doesNotContain(urlMarker)
                .doesNotContain(API_KEY)
                .doesNotContain("Authorization")
                .doesNotContain("UPDATE job_descriptions")
                .doesNotContain("uq_job_descriptions");
    }

    private MvcResult create(String key, String body) throws Exception {
        return mockMvc.perform(authorizedPost(key, body))
                .andExpect(status().isCreated())
                .andExpect(header().string("ETag", "\"0\""))
                .andReturn();
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedPost(String key, String body) {
        return post("/api/v1/job-descriptions")
                .header("Authorization", "Bearer " + API_KEY)
                .header("Idempotency-Key", key)
                .contentType("application/json")
                .content(body);
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedPut(UUID aggregateId, String ifMatch, String body) {
        return put("/api/v1/job-descriptions/{id}", aggregateId)
                .header("Authorization", "Bearer " + API_KEY)
                .header("If-Match", ifMatch)
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

    private static void putNullable(ObjectNode node, String field, String value) {
        if (value == null) {
            node.putNull(field);
        } else {
            node.put(field, value);
        }
    }

    private UUID id(MvcResult result) throws Exception {
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

    private String updatedAt(UUID aggregateId) {
        return jdbcTemplate.queryForObject("""
                SELECT updated_at::text
                FROM job_descriptions
                WHERE id = ?
                """,
                String.class,
                aggregateId);
    }

    private int versionCount(UUID aggregateId) {
        return jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM job_description_versions
                WHERE job_description_id = ?
                """,
                Integer.class,
                aggregateId);
    }

    private int ledgerCount() {
        return jdbcTemplate.queryForObject(
                "SELECT count(*) FROM request_idempotency",
                Integer.class);
    }
}
