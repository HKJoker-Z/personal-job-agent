package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.hkjokerz.jobagent.jdnormalization.JdNormalizationServiceApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "jd-normalization.security.authentication-disabled=true",
    "jd-normalization.security.api-key=",
    "jd-normalization.persistence.enabled=false",
    "server.address=127.0.0.1",
    "management.endpoint.health.group.readiness.include=readinessState",
    "spring.autoconfigure.exclude="
            + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,"
            + "org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration,"
            + "org.springframework.boot.autoconfigure.data.jpa.JpaRepositoriesAutoConfiguration,"
            + "org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration"
})
@AutoConfigureMockMvc
@ActiveProfiles("dev")
class SecurityWebTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exactDevProfileAndLoopbackMayDisableAuthentication() throws Exception {
        mockMvc.perform(post("/api/v1/job-descriptions/normalize")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Java\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mentioned_skills[0].id").value("java"));

        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk());
    }

    @Test
    void corsAndBrowserSessionAuthenticationAreNotEnabled() throws Exception {
        mockMvc.perform(post("/api/v1/job-descriptions/normalize")
                        .header("Origin", "https://browser.example.test")
                        .cookie(new jakarta.servlet.http.Cookie("SESSION", "not-authentication"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"raw_text\":\"Java\"}"))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers
                        .header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void startupRejectsMissingOrShortKeyOutsideDevelopmentMode() {
        for (String suppliedKey : new String[] {"", "short-test-key"}) {
            new WebApplicationContextRunner()
                    .withUserConfiguration(JdNormalizationServiceApplication.class)
                    .withPropertyValues(
                            "spring.profiles.active=default",
                            "server.address=127.0.0.1",
                            databaseExclusions(),
                            "jd-normalization.persistence.enabled=false",
                            "management.endpoint.health.group.readiness.include=readinessState",
                            "jd-normalization.security.authentication-disabled=false",
                            "jd-normalization.security.api-key=" + suppliedKey)
                    .run(context -> {
                        org.assertj.core.api.Assertions.assertThat(context).hasFailed();
                        org.assertj.core.api.Assertions.assertThat(context.getStartupFailure())
                                .hasRootCauseMessage(
                                        "JD_NORMALIZATION_API_KEY must contain at least 32 bytes");
                    });
        }
    }

    @Test
    void startupRejectsDisabledAuthenticationWithoutExactDevLoopbackMode() {
        new WebApplicationContextRunner()
                .withUserConfiguration(JdNormalizationServiceApplication.class)
                    .withPropertyValues(
                            "server.address=127.0.0.1",
                            databaseExclusions(),
                            "jd-normalization.persistence.enabled=false",
                            "management.endpoint.health.group.readiness.include=readinessState",
                            "jd-normalization.security.authentication-disabled=true")
                .run(context -> {
                    org.assertj.core.api.Assertions.assertThat(context).hasFailed();
                    org.assertj.core.api.Assertions.assertThat(context.getStartupFailure())
                            .hasRootCauseMessage(
                                    "Disabled authentication requires the exact dev profile "
                                            + "and loopback binding");
                });

        new WebApplicationContextRunner()
                .withUserConfiguration(JdNormalizationServiceApplication.class)
                    .withPropertyValues(
                            "spring.profiles.active=dev",
                            "server.address=0.0.0.0",
                            databaseExclusions(),
                            "jd-normalization.persistence.enabled=false",
                            "management.endpoint.health.group.readiness.include=readinessState",
                            "jd-normalization.security.authentication-disabled=true")
                .run(context -> {
                    org.assertj.core.api.Assertions.assertThat(context).hasFailed();
                    org.assertj.core.api.Assertions.assertThat(context.getStartupFailure())
                            .hasRootCauseMessage(
                                    "Disabled authentication requires the exact dev profile "
                                            + "and loopback binding");
                });
    }

    private static String databaseExclusions() {
        return "spring.autoconfigure.exclude="
                + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,"
                + "org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration,"
                + "org.springframework.boot.autoconfigure.data.jpa.JpaRepositoriesAutoConfiguration,"
                + "org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration";
    }
}
