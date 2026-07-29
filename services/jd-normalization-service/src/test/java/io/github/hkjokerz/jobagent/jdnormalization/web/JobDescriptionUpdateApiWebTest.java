package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.IdempotencyLedgerRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.JobDescriptionCreateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.JobDescriptionReadService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.ConditionalUpdateRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.JobDescriptionUpdateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateResult;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
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

@SpringBootTest(properties = {
    "jd-normalization.persistence.enabled=true",
    "jd-normalization.schema-health.enabled=false"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
class JobDescriptionUpdateApiWebTest {

    private static final String API_KEY = "TEST_ONLY_INTERNAL_API_KEY_32_BYTES_LONG";
    private static final UUID AGGREGATE_ID =
            UUID.fromString("00000000-0000-4000-8000-000000000701");
    private static final String BODY = """
            {
              "raw_text": "Required:\\n- Java 21",
              "metadata": {"title": "Platform Engineer"}
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private JobDescriptionUpdateService updateService;

    @MockitoBean
    private ConditionalUpdateRepository updateRepository;

    @MockitoBean
    private JobDescriptionReadService readService;

    @MockitoBean
    private JobDescriptionCreateService createService;

    @MockitoBean
    private IdempotencyLedgerRepository ledgerRepository;

    @Test
    void returnsChangedAndNoopResponsesWithCurrentStrongEtag() throws Exception {
        given(updateService.update(
                        eq(AGGREGATE_ID),
                        eq(0L),
                        any(NormalizeJobDescriptionRequest.class)))
                .willReturn(new UpdateResult(current(1, 2), true));

        mockMvc.perform(authorizedPut("\"0\"", BODY)
                        .header("X-Request-ID", "update-web:1"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "update-web:1"))
                .andExpect(header().string("ETag", "\"1\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.id").value(AGGREGATE_ID.toString()))
                .andExpect(jsonPath("$.optimistic_lock_version").value(1))
                .andExpect(jsonPath("$.current_version_number").value(2))
                .andExpect(jsonPath("$.metadata.title").value("Platform Engineer"));

        given(updateService.update(
                        eq(AGGREGATE_ID),
                        eq(1L),
                        any(NormalizeJobDescriptionRequest.class)))
                .willReturn(new UpdateResult(current(1, 2), false));

        mockMvc.perform(authorizedPut("\"1\"", BODY))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"1\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.optimistic_lock_version").value(1))
                .andExpect(jsonPath("$.current_version_number").value(2));
    }

    @Test
    void authenticatesBeforeHeaderOrResourceDisclosure() throws Exception {
        mockMvc.perform(put("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));

        verify(updateService, never())
                .update(any(), anyLong(), any(NormalizeJobDescriptionRequest.class));
    }

    @Test
    void rejectsMissingMalformedAndMultipleIfMatchValues() throws Exception {
        mockMvc.perform(put("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isPreconditionRequired())
                .andExpect(jsonPath("$.error.code").value("PRECONDITION_REQUIRED"))
                .andExpect(jsonPath("$.error.details").isMap());

        for (String value : List.of(
                "W/\"1\"",
                "*",
                "1",
                "\"-1\"",
                "\"one\"",
                "\"9223372036854775808\"",
                "\"123456789012345678901\"",
                "\"0\", \"1\"")) {
            mockMvc.perform(authorizedPut(value, BODY))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_IF_MATCH"))
                    .andExpect(jsonPath("$.error.details").isMap());
        }

        mockMvc.perform(put("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("If-Match", "\"0\"", "\"1\"")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_IF_MATCH"));

        verify(updateService, never())
                .update(any(), anyLong(), any(NormalizeJobDescriptionRequest.class));
    }

    @Test
    void returnsStableStaleMissingConflictAndValidationErrors() throws Exception {
        given(updateService.update(
                        eq(AGGREGATE_ID),
                        eq(0L),
                        any(NormalizeJobDescriptionRequest.class)))
                .willThrow(UpdateApiException.preconditionFailed());
        mockMvc.perform(authorizedPut("\"0\"", BODY))
                .andExpect(status().isPreconditionFailed())
                .andExpect(jsonPath("$.error.code").value("PRECONDITION_FAILED"))
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("current_etag"))));

        given(updateService.update(
                        eq(AGGREGATE_ID),
                        eq(1L),
                        any(NormalizeJobDescriptionRequest.class)))
                .willThrow(UpdateApiException.notFound());
        mockMvc.perform(authorizedPut("\"1\"", BODY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_NOT_FOUND"));

        String sensitiveUrl = "https://jobs.example.test/private-conflict";
        given(updateService.update(
                        eq(AGGREGATE_ID),
                        eq(2L),
                        any(NormalizeJobDescriptionRequest.class)))
                .willThrow(UpdateApiException.alreadyExists(
                        "canonical_url",
                        UUID.fromString("00000000-0000-4000-8000-000000000702")));
        mockMvc.perform(authorizedPut(
                        "\"2\"",
                        """
                        {
                          "raw_text": "sensitive replacement",
                          "metadata": {"canonical_url": "%s"}
                        }
                        """.formatted(sensitiveUrl)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("JOB_DESCRIPTION_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.error.details.conflict_category")
                        .value("canonical_url"))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString(sensitiveUrl))))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("constraint"))))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("UPDATE job_descriptions"))));

        mockMvc.perform(authorizedPut("\"3\"", "{}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.error.request_id").isString())
                .andExpect(jsonPath("$.error.details").isMap());
    }

    @Test
    void openApiDocumentsConditionalReplacementWithoutIdempotencyKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put")
                        .exists())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put.parameters"
                                        + "[?(@.name == 'If-Match')].required")
                        .value(true))
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put.parameters"
                                        + "[?(@.name == 'Idempotency-Key')]")
                        .isEmpty())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put"
                                        + ".responses['200'].headers.ETag")
                        .exists())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put"
                                        + ".responses['412']")
                        .exists())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}'].put"
                                        + ".responses['428']")
                        .exists());
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedPut(String ifMatch, String body) {
        return put("/api/v1/job-descriptions/{id}", AGGREGATE_ID)
                .header("Authorization", "Bearer " + API_KEY)
                .header("If-Match", ifMatch)
                .contentType("application/json")
                .content(body);
    }

    private static ReadModels.Current current(long lockVersion, int versionNumber) {
        return new ReadModels.Current(
                AGGREGATE_ID,
                null,
                lockVersion,
                versionNumber,
                "Required:\n- Java 21",
                bytes(0x71),
                "jd-normalization-v1",
                "skills-v1",
                List.of(new SkillSnapshot("java", "Java")),
                List.of(),
                List.of(),
                "Platform Engineer",
                null,
                null,
                Instant.parse("2026-07-29T01:00:00Z"),
                Instant.parse("2026-07-29T02:00:00Z"));
    }

    private static byte[] bytes(int value) {
        byte[] result = new byte[32];
        java.util.Arrays.fill(result, (byte) value);
        return result;
    }
}
