package io.github.hkjokerz.jobagent.jdnormalization;

import io.github.hkjokerz.jobagent.jdnormalization.config.ServiceProperties;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
@EnableConfigurationProperties(ServiceProperties.class)
@OpenAPIDefinition(
        info = @Info(
                title = "JD Normalization Service API",
                version = "v1",
                description = "Deterministic Job Description normalization; no persistence or AI"))
@SecurityScheme(
        name = "internalApiKey",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "internal API key",
        description = "Internal API key supplied through the Authorization header")
public class JdNormalizationServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdNormalizationServiceApplication.class, args);
    }
}
