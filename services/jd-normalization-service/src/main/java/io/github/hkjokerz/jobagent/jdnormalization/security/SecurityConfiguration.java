package io.github.hkjokerz.jobagent.jdnormalization.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.config.ServiceProperties;
import io.github.hkjokerz.jobagent.jdnormalization.web.ApiExceptionHandler;
import jakarta.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ServiceProperties properties,
            Environment environment,
            ObjectMapper objectMapper,
            @Value("${server.address:127.0.0.1}") String serverAddress) throws Exception {
        boolean developmentProfile =
                Arrays.equals(environment.getActiveProfiles(), new String[] {"dev"});
        boolean disabled = properties.getSecurity().isAuthenticationDisabled();
        String apiKey = properties.getSecurity().getApiKey();
        if (disabled && (!developmentProfile || !isLoopback(serverAddress))) {
            throw new IllegalStateException(
                    "Disabled authentication requires the exact dev profile and loopback binding");
        }
        if (!disabled && apiKey.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalStateException(
                    "JD_NORMALIZATION_API_KEY must contain at least 32 bytes");
        }
        InternalApiKeyFilter apiKeyFilter = new InternalApiKeyFilter(
                apiKey,
                disabled,
                developmentProfile,
                objectMapper);
        properties.getSecurity().clearApiKey();
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> cors.disable())
                .httpBasic(httpBasic -> httpBasic.disable())
                .formLogin(formLogin -> formLogin.disable())
                .logout(logout -> logout.disable())
                .requestCache(requestCache -> requestCache.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> {
                    authorize.requestMatchers(
                                    "/actuator/health",
                                    "/actuator/health/liveness",
                                    "/actuator/health/readiness")
                            .permitAll();
                    if (developmentProfile) {
                        authorize.requestMatchers("/v3/api-docs/**").permitAll();
                    } else {
                        authorize.requestMatchers("/v3/api-docs/**").authenticated();
                    }
                    if (properties.getSecurity().isAuthenticationDisabled()) {
                        authorize.requestMatchers("/api/v1/**").permitAll();
                    } else {
                        authorize.requestMatchers("/api/v1/**").authenticated();
                    }
                    authorize.anyRequest().permitAll();
                })
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, exception) ->
                                writeUnauthorized(response, request, objectMapper))
                        .accessDeniedHandler((request, response, exception) ->
                                writeUnauthorized(response, request, objectMapper)))
                .addFilterBefore(apiKeyFilter, AuthorizationFilter.class);
        return http.build();
    }

    private static void writeUnauthorized(
            HttpServletResponse response,
            jakarta.servlet.http.HttpServletRequest request,
            ObjectMapper objectMapper) throws java.io.IOException {
        String requestId = ApiExceptionHandler.trustedRequestId(request);
        ApiExceptionHandler.writeError(
                response,
                objectMapper,
                HttpServletResponse.SC_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Authentication is required.",
                requestId,
                Map.of());
    }

    private static boolean isLoopback(String address) {
        String normalized = address == null ? "" : address.strip().toLowerCase();
        return normalized.equals("localhost")
                || normalized.equals("127.0.0.1")
                || normalized.equals("::1")
                || normalized.equals("[::1]");
    }
}
