package io.github.hkjokerz.jobagent.jdnormalization.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.web.ApiExceptionHandler;
import io.github.hkjokerz.jobagent.jdnormalization.web.RequestIdFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class InternalApiKeyFilter extends OncePerRequestFilter {

    private final byte[] expectedDigest;
    private final boolean authenticationDisabled;
    private final boolean developmentProfile;
    private final ObjectMapper objectMapper;

    public InternalApiKeyFilter(
            String apiKey,
            boolean authenticationDisabled,
            boolean developmentProfile,
            ObjectMapper objectMapper) {
        this.expectedDigest = authenticationDisabled ? new byte[0] : sha256(apiKey);
        this.authenticationDisabled = authenticationDisabled;
        this.developmentProfile = developmentProfile;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        boolean protectedPath = path.startsWith("/api/v1/")
                || (!developmentProfile && path.startsWith("/v3/api-docs"));
        return !protectedPath || authenticationDisabled;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        List<String> values = request.getHeaderNames() == null
                ? List.of()
                : Collections.list(request.getHeaders("Authorization"));
        if (values.size() != 1 || !validBearer(values.getFirst())) {
            String requestId = ApiExceptionHandler.trustedRequestId(request);
            ApiExceptionHandler.writeError(
                    response,
                    objectMapper,
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "UNAUTHORIZED",
                    "Authentication is required.",
                    requestId,
                    Map.of());
            return;
        }

        UsernamePasswordAuthenticationToken authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "internal-service",
                        null,
                        AuthorityUtils.NO_AUTHORITIES);
        SecurityContextHolder.getContext().setAuthentication(authentication);
        try {
            filterChain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private boolean validBearer(String header) {
        if (header == null
                || header.length() <= 7
                || !header.regionMatches(true, 0, "Bearer ", 0, 7)) {
            return false;
        }
        String candidate = header.substring(7);
        if (candidate.isBlank()) {
            return false;
        }
        byte[] actualDigest = sha256(candidate);
        return MessageDigest.isEqual(expectedDigest, actualDigest);
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable");
        }
    }
}
