package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CompletedCreateResponse;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.IdempotencyLedgerRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.JobDescriptionCreateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.JobDescriptionReadService;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
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
class JobDescriptionCreateApiWebTest {

    private static final String API_KEY = "TEST_ONLY_INTERNAL_API_KEY_32_BYTES_LONG";
    private static final String KEY = "550e8400-e29b-41d4-a716-446655440000";
    private static final String BODY = """
            {
              "raw_text": "Required:\\n- Java",
              "metadata": {"title": "Backend Engineer"}
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockitoBean
    private JobDescriptionCreateService createService;

    @MockitoBean
    private IdempotencyLedgerRepository ledgerRepository;

    @MockitoBean
    private JobDescriptionReadService readService;

    @Test
    void requiresOneSyntacticallyValidKeyAfterAuthentication() throws Exception {
        mockMvc.perform(post("/api/v1/job-descriptions")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_REQUIRED"));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", "too-short")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_INVALID"));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", "a".repeat(129))
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_INVALID"));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", "a".repeat(15) + "!")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_INVALID"));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", KEY, UUID.randomUUID().toString())
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_INVALID"));

        verify(createService, never())
                .create(anyString(), any(NormalizeJobDescriptionRequest.class), anyString());
    }

    @Test
    void returnsStoredCreationAndReplayHeadersWithoutChangingTheBody() throws Exception {
        UUID aggregateId = UUID.fromString("00000000-0000-4000-8000-000000000501");
        com.fasterxml.jackson.databind.JsonNode body = objectMapper.readTree("""
                {"id":"00000000-0000-4000-8000-000000000501","optimistic_lock_version":0}
                """);
        given(createService.create(
                        eq(KEY),
                        any(NormalizeJobDescriptionRequest.class),
                        eq("create-web:1")))
                .willReturn(new CompletedCreateResponse(
                        201,
                        body,
                        "/api/v1/job-descriptions/" + aggregateId,
                        "\"0\"",
                        aggregateId,
                        false));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", KEY)
                        .header("X-Request-ID", "create-web:1")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location",
                        "/api/v1/job-descriptions/" + aggregateId))
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().doesNotExist("Idempotency-Replayed"))
                .andExpect(content().json(body.toString()));

        given(createService.create(
                        eq(KEY),
                        any(NormalizeJobDescriptionRequest.class),
                        eq("create-web:2")))
                .willReturn(new CompletedCreateResponse(
                        201,
                        body,
                        "/api/v1/job-descriptions/" + aggregateId,
                        "\"0\"",
                        aggregateId,
                        true));

        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", KEY)
                        .header("X-Request-ID", "create-web:2")
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isCreated())
                .andExpect(header().string("Idempotency-Replayed", "true"))
                .andExpect(header().string(
                        "Location",
                        "/api/v1/job-descriptions/" + aggregateId))
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(content().json(body.toString()));
    }

    @Test
    void mapsReuseAndInProgressToStableSafeConflicts() throws Exception {
        given(createService.create(
                        eq(KEY),
                        any(NormalizeJobDescriptionRequest.class),
                        anyString()))
                .willThrow(CreateApiException.keyReused());
        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", KEY)
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("IDEMPOTENCY_KEY_REUSED"))
                .andExpect(jsonPath("$.error.details").isMap());

        String otherKey = "660e8400-e29b-41d4-a716-446655440000";
        given(createService.create(
                        eq(otherKey),
                        any(NormalizeJobDescriptionRequest.class),
                        anyString()))
                .willThrow(CreateApiException.inProgress(7));
        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("Idempotency-Key", otherKey)
                        .contentType("application/json")
                        .content(BODY))
                .andExpect(status().isConflict())
                .andExpect(header().string("Retry-After", "7"))
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_REQUEST_IN_PROGRESS"))
                .andExpect(content().string(
                        org.hamcrest.Matchers.not(
                                org.hamcrest.Matchers.containsString(KEY))));
    }
}
