package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "jd-normalization.security.authentication-disabled=true",
    "jd-normalization.security.api-key=",
    "server.address=127.0.0.1"
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
}
