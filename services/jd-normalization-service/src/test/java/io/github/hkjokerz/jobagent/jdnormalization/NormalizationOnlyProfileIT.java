package io.github.hkjokerz.jobagent.jdnormalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.matchesPattern;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.hkjokerz.jobagent.jdnormalization.config.NormalizationReadinessHealthIndicator;
import io.github.hkjokerz.jobagent.jdnormalization.config.SchemaReadinessHealthIndicator;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateFingerprints;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.IdempotencyLedgerRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.JobDescriptionCreateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescription;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescriptionVersion;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.CursorCodec;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.JobDescriptionReadService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionVersionRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.ConditionalUpdateRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.JobDescriptionUpdateService;
import io.github.hkjokerz.jobagent.jdnormalization.web.JobDescriptionCreateController;
import io.github.hkjokerz.jobagent.jdnormalization.web.JobDescriptionReadController;
import io.github.hkjokerz.jobagent.jdnormalization.web.JobDescriptionUpdateController;
import io.github.hkjokerz.jobagent.jdnormalization.web.PersistenceApiExceptionHandler;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.hibernate.SessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.assertj.AssertableWebApplicationContext;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=TEST_ONLY_NORMALIZATION_PROFILE_KEY_32_BYTES",
    "server.address=127.0.0.1"
})
@AutoConfigureMockMvc
@ActiveProfiles("normalization-only")
@ExtendWith(OutputCaptureExtension.class)
class NormalizationOnlyProfileIT {

    private static final String API_KEY =
            "TEST_ONLY_NORMALIZATION_PROFILE_KEY_32_BYTES";
    private static final String AUTHORIZATION = "Bearer " + API_KEY;
    private static final String NORMALIZE =
            "/api/v1/job-descriptions/normalize";

    @Autowired
    private ApplicationContext applicationContext;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void startsWithoutDatabaseEnvironmentAndPersistenceBeans() {
        assertThat(applicationContext.getEnvironment()
                        .getProperty("JD_NORMALIZATION_JDBC_URL"))
                .isNull();
        assertThat(applicationContext.getEnvironment()
                        .getProperty("JD_NORMALIZATION_DB_USERNAME"))
                .isNull();
        assertThat(applicationContext.getEnvironment()
                        .getProperty("JD_NORMALIZATION_DB_PASSWORD"))
                .isNull();
        assertThat(applicationContext.getEnvironment()
                        .getProperty("JD_NORMALIZATION_FLYWAY_USERNAME"))
                .isNull();
        assertThat(applicationContext.getEnvironment()
                        .getProperty("JD_NORMALIZATION_FLYWAY_PASSWORD"))
                .isNull();

        assertNoBeans(applicationContext, DataSource.class);
        assertNoBeans(applicationContext, JdbcTemplate.class);
        assertNoBeans(applicationContext, EntityManagerFactory.class);
        assertNoBeans(applicationContext, SessionFactory.class);
        assertNoBeans(applicationContext, PlatformTransactionManager.class);
        assertNoBeans(applicationContext, Flyway.class);
        assertNoBeans(applicationContext, JobDescriptionRepository.class);
        assertNoBeans(applicationContext, JobDescriptionVersionRepository.class);
        assertNoBeans(applicationContext, JobDescription.class);
        assertNoBeans(applicationContext, JobDescriptionVersion.class);
        assertNoBeans(applicationContext, CreateFingerprints.class);
        assertNoBeans(applicationContext, IdempotencyLedgerRepository.class);
        assertNoBeans(applicationContext, JobDescriptionCreateService.class);
        assertNoBeans(applicationContext, CursorCodec.class);
        assertNoBeans(applicationContext, JobDescriptionReadService.class);
        assertNoBeans(applicationContext, ConditionalUpdateRepository.class);
        assertNoBeans(applicationContext, JobDescriptionUpdateService.class);
        assertNoBeans(applicationContext, JobDescriptionCreateController.class);
        assertNoBeans(applicationContext, JobDescriptionReadController.class);
        assertNoBeans(applicationContext, JobDescriptionUpdateController.class);
        assertNoBeans(applicationContext, SchemaReadinessHealthIndicator.class);
        assertNoBeans(applicationContext, PersistenceApiExceptionHandler.class);
        assertThat(applicationContext.containsBean("dataSource")).isFalse();
        assertThat(applicationContext.containsBean("entityManagerFactory")).isFalse();
        assertThat(applicationContext.containsBean("transactionManager")).isFalse();
        assertThat(applicationContext.containsBean("flyway")).isFalse();
        assertThat(applicationContext.containsBean("flywayInitializer")).isFalse();
        assertThat(applicationContext.containsBean("dbHealthContributor")).isFalse();
        assertThat(applicationContext.containsBean("schemaReadiness")).isFalse();
        assertThat(applicationContext.getBean(
                NormalizationReadinessHealthIndicator.class)).isNotNull();
    }

    @Test
    void ignoresImpossibleDummyDatabaseSettingsWithoutConnecting(
            CapturedOutput output) {
        new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(JdNormalizationServiceApplication.class)
                .withPropertyValues(
                        "spring.profiles.active=normalization-only",
                        "server.address=127.0.0.1",
                        "jd-normalization.security.api-key=" + API_KEY,
                        "spring.datasource.url="
                                + "jdbc:postgresql://192.0.2.1:1/must-not-connect",
                        "spring.datasource.username=dummy",
                        "spring.datasource.password=dummy",
                        "spring.flyway.url="
                                + "jdbc:postgresql://192.0.2.1:1/must-not-connect",
                        "spring.flyway.user=dummy",
                        "spring.flyway.password=dummy")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertNoBeans(context, DataSource.class);
                    assertNoBeans(context, JdbcTemplate.class);
                    assertNoBeans(context, EntityManagerFactory.class);
                    assertNoBeans(context, PlatformTransactionManager.class);
                    assertNoBeans(context, Flyway.class);
                });

        assertThat(output).doesNotContain("192.0.2.1");
        assertThat(output).doesNotContain("HikariPool");
        assertThat(output).doesNotContain("database_unavailable");
        assertThat(output).doesNotContain("Unable to obtain connection");
    }

    @Test
    void normalizationOnlyCannotBypassApiKeyValidation() {
        for (String suppliedKey : new String[] {"", "short-key"}) {
            normalizationOnlyContext()
                    .withPropertyValues(
                            "jd-normalization.security.authentication-disabled=false",
                            "jd-normalization.security.api-key=" + suppliedKey)
                    .run(context -> {
                        assertThat(context).hasFailed();
                        assertThat(context.getStartupFailure())
                                .hasRootCauseMessage(
                                        "JD_NORMALIZATION_API_KEY must contain at least 32 bytes");
                    });
        }

        normalizationOnlyContext()
                .withPropertyValues(
                        "jd-normalization.security.authentication-disabled=true",
                        "jd-normalization.security.api-key=")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseMessage(
                                    "Disabled authentication requires the exact dev profile "
                                            + "and loopback binding");
                });
    }

    @Test
    void preservesNormalizeAuthenticationRequestIdAndContract() throws Exception {
        mockMvc.perform(post(NORMALIZE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"PRIVATE_RAW_JD_MARKER\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "X-Request-ID",
                        matchesPattern(
                                "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                                        + "[89ab][0-9a-f]{3}-[0-9a-f]{12}$")))
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.error.message")
                        .value("Authentication is required."))
                .andExpect(jsonPath("$.error.request_id").isString())
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(content().string(not(containsString(
                        "PRIVATE_RAW_JD_MARKER"))))
                .andExpect(content().string(not(containsString(API_KEY))));

        mockMvc.perform(post(NORMALIZE)
                        .header("Authorization", AUTHORIZATION)
                        .header("X-Request-ID", "normalization-only:contract")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "raw_text": "Required:\\r\\n- Java 21\\r\\nPreferred:\\r\\n- Docker",
                                  "metadata": {
                                    "title": " Platform Engineer ",
                                    "company": "Synthetic Example",
                                    "location": "Hong Kong"
                                  }
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Request-ID",
                        "normalization-only:contract"))
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.normalized_text")
                        .value("Required:\n- Java 21\nPreferred:\n- Docker"))
                .andExpect(jsonPath("$.content_hash")
                        .value(matchesPattern("^[0-9a-f]{64}$")))
                .andExpect(jsonPath("$.normalization_policy_version")
                        .value("jd-normalization-v1"))
                .andExpect(jsonPath("$.skill_dictionary_version")
                        .value("skills-v1"))
                .andExpect(jsonPath("$.required_skills", hasSize(1)))
                .andExpect(jsonPath("$.required_skills[0].id").value("java"))
                .andExpect(jsonPath("$.preferred_skills", hasSize(1)))
                .andExpect(jsonPath("$.preferred_skills[0].id").value("docker"))
                .andExpect(jsonPath("$.mentioned_skills", hasSize(0)))
                .andExpect(jsonPath("$.metadata.title").value("Platform Engineer"));
    }

    @Test
    void generatesAndPreservesRequestIdsAndStableValidationErrors()
            throws Exception {
        mockMvc.perform(post(NORMALIZE)
                        .header("Authorization", AUTHORIZATION)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Java\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Request-ID",
                        matchesPattern(
                                "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                                        + "[89ab][0-9a-f]{3}-[0-9a-f]{12}$")));

        mockMvc.perform(post(NORMALIZE)
                        .header("Authorization", AUTHORIZATION)
                        .header("X-Request-ID", "normalization-only:validation")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"metadata\":{}}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(header().string(
                        "X-Request-ID",
                        "normalization-only:validation"))
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.error.message")
                        .value("The request could not be processed."))
                .andExpect(jsonPath("$.error.request_id")
                        .value("normalization-only:validation"))
                .andExpect(jsonPath("$.error.details.field").value("raw_text"))
                .andExpect(jsonPath("$.error.details.rule").value("required"));
    }

    @Test
    void exposesOnlyStatusOnlyProcessAndNormalizationHealth()
            throws Exception {
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
    void authenticatedPersistenceRoutesAreAbsent() throws Exception {
        String aggregateId = "00000000-0000-4000-8000-000000000001";
        mockMvc.perform(post("/api/v1/job-descriptions")
                        .header("Authorization", AUTHORIZATION)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Synthetic\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
        mockMvc.perform(get("/api/v1/job-descriptions")
                        .header("Authorization", AUTHORIZATION))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
        mockMvc.perform(get("/api/v1/job-descriptions/{id}", aggregateId)
                        .header("Authorization", AUTHORIZATION))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
        mockMvc.perform(get(
                        "/api/v1/job-descriptions/{id}/versions",
                        aggregateId)
                        .header("Authorization", AUTHORIZATION))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
        mockMvc.perform(put("/api/v1/job-descriptions/{id}", aggregateId)
                        .header("Authorization", AUTHORIZATION)
                        .header("If-Match", "\"0\"")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Synthetic\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
    }

    @Test
    void openApiContainsOnlyNormalizeAndNoSwaggerUi() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));

        mockMvc.perform(get("/v3/api-docs")
                        .header("Authorization", AUTHORIZATION))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.paths['/api/v1/job-descriptions/normalize'].post")
                        .exists())
                .andExpect(jsonPath("$.paths.length()").value(1))
                .andExpect(jsonPath(
                        "$.components.securitySchemes.internalApiKey.scheme")
                        .value("bearer"))
                .andExpect(jsonPath("$.components.schemas.ApiErrorResponse")
                        .exists())
                .andExpect(content().string(containsString("X-Request-ID")))
                .andExpect(content().string(not(containsString(
                        "/api/v1/job-descriptions/{id}"))))
                .andExpect(content().string(not(containsString(API_KEY))));

        mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
        mockMvc.perform(get("/v3/api-docs.yaml")
                        .header("Authorization", AUTHORIZATION))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ROUTE_NOT_FOUND"));
    }

    @Test
    void corsRemainsDisabled() throws Exception {
        mockMvc.perform(options(NORMALIZE)
                        .header("Origin", "https://browser.example.test")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(header().doesNotExist("Access-Control-Allow-Origin"))
                .andExpect(header().doesNotExist("Access-Control-Allow-Methods"));
    }

    private static <T> void assertNoBeans(
            ApplicationContext context,
            Class<T> type) {
        assertThat(context.getBeansOfType(type)).isEmpty();
    }

    private static <T> void assertNoBeans(
            AssertableWebApplicationContext context,
            Class<T> type) {
        assertThat(context.getBeansOfType(type)).isEmpty();
    }

    private static WebApplicationContextRunner normalizationOnlyContext() {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(JdNormalizationServiceApplication.class)
                .withPropertyValues(
                        "spring.profiles.active=normalization-only",
                        "server.address=127.0.0.1");
    }
}
