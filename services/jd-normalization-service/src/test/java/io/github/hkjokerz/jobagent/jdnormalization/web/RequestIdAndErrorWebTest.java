package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.matchesPattern;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationPolicy;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RequestIdAndErrorWebTest {

    private static final String API_KEY = "TEST_ONLY_INTERNAL_API_KEY_32_BYTES_LONG";
    private static final String ENDPOINT = "/api/v1/job-descriptions/normalize";
    private static final String UUID_V4_PATTERN =
            "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                    + "[89ab][0-9a-f]{3}-[0-9a-f]{12}$";

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private JobDescriptionNormalizer normalizer;

    @Test
    void invalidAndMultipleRequestIdsGetFreshTrustedIds() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("X-Request-ID", "invalid request id")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"private-text\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string(
                        "X-Request-ID",
                        matchesPattern(UUID_V4_PATTERN)))
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST_ID"))
                .andExpect(jsonPath("$.error.request_id")
                        .value(matchesPattern(UUID_V4_PATTERN)))
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(not(containsString("private-text"))));

        mockMvc.perform(post(ENDPOINT)
                        .header("X-Request-ID", "first", "second")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"private-text\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST_ID"))
                .andExpect(jsonPath("$.error.request_id")
                        .value(matchesPattern(UUID_V4_PATTERN)));
    }

    @Test
    void mapsInvalidJsonUnknownFieldsAndInvalidUtf8ToSafeErrors() throws Exception {
        assertInvalidRequest("{\"raw_text\":\"secret-marker\",");
        assertInvalidRequest(
                "{\"raw_text\":\"safe\",\"unknown\":\"secret-marker\"}");

        byte[] invalidUtf8 = new byte[] {
            '{', '"', 'r', 'a', 'w', '_', 't', 'e', 'x', 't', '"', ':', '"',
            (byte) 0xc3, (byte) 0x28, '"', '}'
        };
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(invalidUtf8))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.error.details").isMap());
    }

    @Test
    void mapsUnsupportedMediaTypeAndMethodToStableEnvelope() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("secret-marker"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.error.code").value("UNSUPPORTED_MEDIA_TYPE"))
                .andExpect(jsonPath("$.error.message")
                        .value("The request media type is unsupported."))
                .andExpect(jsonPath("$.error.request_id").isString())
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(not(containsString("secret-marker"))));

        mockMvc.perform(get(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.error.code").value("METHOD_NOT_ALLOWED"))
                .andExpect(jsonPath("$.error.details").isMap());
    }

    @Test
    void enforcesByteBoundBeforeParsingOrLoggingBody() throws Exception {
        String body = "{\"raw_text\":\""
                + "secret-marker".repeat(
                        NormalizationPolicy.MAX_REQUEST_BYTES / 10)
                + "\"}";

        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.error.code").value("PAYLOAD_TOO_LARGE"))
                .andExpect(jsonPath("$.error.details.maximum_bytes")
                        .value(NormalizationPolicy.MAX_REQUEST_BYTES))
                .andExpect(content().string(not(containsString("secret-marker"))));
    }

    @Test
    void mapsUnknownRouteAndSafeInternalErrorWithoutSensitiveValues() throws Exception {
        mockMvc.perform(get("/api/v1/not-a-real-route")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"))
                .andExpect(jsonPath("$.error.details").isMap());

        given(normalizer.normalize(any()))
                .willThrow(new IllegalStateException(
                        "secret-marker /private/path host.internal"));
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"secret-marker\"}"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.error.message")
                        .value("The request could not be completed."))
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(not(containsString("secret-marker"))))
                .andExpect(content().string(not(containsString("/private/path"))))
                .andExpect(content().string(not(containsString("host.internal"))));
    }

    private void assertInvalidRequest(String body) throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(header().exists("X-Request-ID"))
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.error.message")
                        .value("The request body is invalid."))
                .andExpect(jsonPath("$.error.request_id").isString())
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(not(containsString("secret-marker"))));
    }
}
