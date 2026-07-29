package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.matchesPattern;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.IdempotencyLedgerRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.CursorCodec;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.JobDescriptionReadService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.dao.DataAccessResourceFailureException;

@SpringBootTest(properties = {
    "jd-normalization.persistence.enabled=true",
    "jd-normalization.schema-health.enabled=false"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
class JobDescriptionReadApiWebTest {

    private static final String API_KEY = "TEST_ONLY_INTERNAL_API_KEY_32_BYTES_LONG";
    private static final UUID AGGREGATE_ID =
            UUID.fromString("00000000-0000-4000-8000-000000000101");

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private JobDescriptionReadService readService;

    @MockitoBean
    private IdempotencyLedgerRepository idempotencyLedgerRepository;

    @Test
    void returnsCurrentResourceStrongEtagAndConditional304() throws Exception {
        given(readService.current(AGGREGATE_ID)).willReturn(current());

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("X-Request-ID", "read-current:1"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string(
                        "Cache-Control",
                        "private, max-age=0, must-revalidate"))
                .andExpect(header().string("X-Request-ID", "read-current:1"))
                .andExpect(jsonPath("$.id").value(AGGREGATE_ID.toString()))
                .andExpect(jsonPath("$.canonical_url")
                        .value("https://jobs.example.test/backend"))
                .andExpect(jsonPath("$.optimistic_lock_version").value(0))
                .andExpect(jsonPath("$.current_version_number").value(2))
                .andExpect(jsonPath("$.normalized_text").value("Required:\n- Java"))
                .andExpect(jsonPath("$.content_hash").value("11".repeat(32)))
                .andExpect(jsonPath("$.required_skills[0].id").value("java"))
                .andExpect(jsonPath("$.metadata.title").value("Backend Engineer"));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("If-None-Match", "\"0\""))
                .andExpect(status().isNotModified())
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(content().string(""));
    }

    @Test
    void validatesConditionalHeaderUuidAndAuthenticationBeforeDisclosure() throws Exception {
        given(readService.current(AGGREGATE_ID)).willThrow(ReadApiException.notFound());

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
        verify(readService, never()).current(any());

        mockMvc.perform(get("/api/v1/job-descriptions/not-a-uuid")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("If-None-Match", "\"0\", \"1\""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("JOB_DESCRIPTION_NOT_FOUND"))
                .andExpect(jsonPath("$.error.details").isMap());
    }

    @Test
    void listsOnlyBoundedSummariesAndValidatesCursorAndLimits() throws Exception {
        ReadModels.Summary summary = new ReadModels.Summary(
                AGGREGATE_ID,
                null,
                0,
                1,
                "Engineer",
                "Example",
                "Hong Kong",
                bytes(0x22),
                Instant.parse("2026-07-29T01:00:00Z"),
                Instant.parse("2026-07-29T01:00:00Z"));
        given(readService.list(
                        eq(20),
                        eq(CursorCodec.ListSort.CREATED_AT_DESC),
                        any(),
                        eq(null)))
                .willReturn(new ReadModels.Slice<>(List.of(summary), null));

        mockMvc.perform(get("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .queryParam("title", " ENGINEER "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].normalized_text").doesNotExist())
                .andExpect(jsonPath("$.items[0].required_skills").doesNotExist())
                .andExpect(jsonPath("$.items[0].content_hash").value("22".repeat(32)))
                .andExpect(jsonPath("$.next_cursor").doesNotExist());

        mockMvc.perform(get("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .queryParam("limit", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .queryParam("cursor", "not-base64"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_CURSOR"));
    }

    @Test
    void returnsBoundedVersionHistoryAndStableReadErrors() throws Exception {
        ReadModels.Version version = new ReadModels.Version(
                UUID.fromString("00000000-0000-4000-8000-000000000201"),
                1,
                "Java",
                bytes(0x33),
                "jd-normalization-v1",
                "skills-v1",
                List.of(new SkillSnapshot("java", "Java")),
                List.of(),
                List.of(),
                "Engineer",
                "Example",
                null,
                Instant.parse("2026-07-29T01:00:00Z"));
        given(readService.versions(
                        eq(AGGREGATE_ID),
                        eq(10),
                        eq(CursorCodec.VersionSort.VERSION_DESC),
                        eq(null)))
                .willReturn(new ReadModels.Slice<>(List.of(version), null));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}/versions", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.job_description_id")
                        .value(AGGREGATE_ID.toString()))
                .andExpect(jsonPath("$.items[0].version_number").value(1))
                .andExpect(jsonPath("$.items[0].content_hash").value("33".repeat(32)));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}/versions", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .queryParam("limit", "26"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));

    }

    @Test
    void mapsDatabaseUnavailabilityWithoutLeakingConnectionDetails() throws Exception {
        given(readService.current(AGGREGATE_ID))
                .willThrow(new DataAccessResourceFailureException(
                        "jdbc:postgresql://private-host/jd_normalization user=private"));

        mockMvc.perform(get("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code").value("DATABASE_UNAVAILABLE"))
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("private-host"))))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("jdbc:postgresql"))));
    }

    @Test
    void openApiDocumentsOnlyApprovedJsonEndpointsAndSharedSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions/normalize'].post")
                        .exists())
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions'].get").exists())
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions'].post")
                        .exists())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions'].post.parameters"
                                        + "[?(@.name == 'Idempotency-Key')].required")
                        .value(true))
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions/{id}'].get")
                        .exists())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}/versions'].get")
                        .exists())
                .andExpect(jsonPath("$.components.securitySchemes.internalApiKey.scheme")
                        .value("bearer"))
                .andExpect(content().string(
                        org.hamcrest.Matchers.not(
                                org.hamcrest.Matchers.containsString(API_KEY))));

        mockMvc.perform(get("/swagger-ui/index.html")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
    }

    private static ReadModels.Current current() {
        return new ReadModels.Current(
                AGGREGATE_ID,
                "https://jobs.example.test/backend",
                0,
                2,
                "Required:\n- Java",
                bytes(0x11),
                "jd-normalization-v1",
                "skills-v1",
                List.of(new SkillSnapshot("java", "Java")),
                List.of(),
                List.of(),
                "Backend Engineer",
                "Example Ltd",
                "Hong Kong",
                Instant.parse("2026-07-29T01:00:00Z"),
                Instant.parse("2026-07-29T02:00:00Z"));
    }

    private static byte[] bytes(int value) {
        byte[] output = new byte[32];
        java.util.Arrays.fill(output, (byte) value);
        return output;
    }
}
