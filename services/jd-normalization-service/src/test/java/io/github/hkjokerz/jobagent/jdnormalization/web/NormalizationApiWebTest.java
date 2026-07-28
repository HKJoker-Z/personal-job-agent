package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.matchesPattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class NormalizationApiWebTest {

    private static final String API_KEY = "TEST_ONLY_INTERNAL_API_KEY_32_BYTES_LONG";
    private static final String ENDPOINT = "/api/v1/job-descriptions/normalize";

    @Autowired
    private MockMvc mockMvc;

    @Test
    void normalizesApprovedRequestAndReturnsBoundedResponse() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .header("X-Request-ID", "portfolio-request:1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "raw_text": "Senior Backend Engineer\\r\\nRequired:\\r\\n- Java 21",
                                  "metadata": {
                                    "title": "  Senior Backend Engineer ",
                                    "company": "Example Ltd",
                                    "location": "Hong Kong",
                                    "canonical_url": "HTTPS://JOBS.EXAMPLE.TEST:443/a/../backend#apply"
                                  }
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "portfolio-request:1"))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.normalized_text")
                        .value("Senior Backend Engineer\nRequired:\n- Java 21"))
                .andExpect(jsonPath("$.content_hash")
                        .value(matchesPattern("^[0-9a-f]{64}$")))
                .andExpect(jsonPath("$.normalization_policy_version")
                        .value("jd-normalization-v1"))
                .andExpect(jsonPath("$.skill_dictionary_version").value("skills-v1"))
                .andExpect(jsonPath("$.required_skills", hasSize(1)))
                .andExpect(jsonPath("$.required_skills[0].id").value("java"))
                .andExpect(jsonPath("$.required_skills[0].name").value("Java"))
                .andExpect(jsonPath("$.required_skills[0].*").value(hasSize(2)))
                .andExpect(jsonPath("$.preferred_skills", hasSize(0)))
                .andExpect(jsonPath("$.mentioned_skills", hasSize(0)))
                .andExpect(jsonPath("$.metadata.title").value("Senior Backend Engineer"))
                .andExpect(jsonPath("$.metadata.company").value("Example Ltd"))
                .andExpect(jsonPath("$.metadata.location").value("Hong Kong"))
                .andExpect(jsonPath("$.metadata.canonical_url")
                        .value("https://jobs.example.test/backend"));
    }

    @Test
    void generatesUuidV4RequestIdWhenHeaderIsAbsent() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Java\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Request-ID",
                        matchesPattern(
                                "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                                        + "[89ab][0-9a-f]{3}-[0-9a-f]{12}$")));
    }

    @Test
    void rejectsMissingAndInvalidApiKeysWithoutLeakingCredentials() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"do-not-echo\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("do-not-echo"))));

        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer secret-wrong-key")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"do-not-echo\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("secret-wrong-key"))));
    }

    @Test
    void appliesBeanValidationAndEmptyNormalizedTextRules() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"metadata\":{}}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.error.details.field").value("raw_text"))
                .andExpect(jsonPath("$.error.details.rule").value("required"));

        mockMvc.perform(post(ENDPOINT)
                        .header("Authorization", "Bearer " + API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\" \\u0000\\t\\r\\n\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("EMPTY_JOB_DESCRIPTION"))
                .andExpect(jsonPath("$.error.details.field").value("raw_text"))
                .andExpect(jsonPath("$.error.details.rule")
                        .value("non_whitespace_required"));
    }

    @Test
    void exposesStatusOnlyHealthProbesWithoutAuthentication() throws Exception {
        for (String path : new String[] {
            "/actuator/health",
            "/actuator/health/liveness",
            "/actuator/health/readiness"
        }) {
            mockMvc.perform(get(path))
                    .andExpect(status().isOk())
                    .andExpect(header().exists("X-Request-ID"))
                    .andExpect(content().json(
                            "{\"status\":\"UP\"}",
                            JsonCompareMode.STRICT));
        }
    }

    @Test
    void exposesProtectedJsonOpenApiForOnlyApprovedProductEndpoint() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));

        mockMvc.perform(get("/v3/api-docs")
                        .header("Authorization", "Bearer " + API_KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.paths['/api/v1/job-descriptions/normalize'].post")
                        .exists())
                .andExpect(jsonPath("$.paths.length()").value(1))
                .andExpect(jsonPath("$.components.securitySchemes.internalApiKey")
                        .exists())
                .andExpect(content().string(org.hamcrest.Matchers.containsString(
                        "X-Request-ID")));

        mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
    }
}
