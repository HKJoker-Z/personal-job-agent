package io.github.hkjokerz.jobagent.jdnormalization.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationPolicy;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Request-ID";
    public static final String ATTRIBUTE_NAME =
            RequestIdFilter.class.getName() + ".trustedRequestId";

    private static final Pattern VALID_REQUEST_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}");
    private static final Logger LOGGER = LoggerFactory.getLogger(RequestIdFilter.class);

    private final ObjectMapper objectMapper;

    public RequestIdFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        long started = System.nanoTime();
        HeaderResolution resolution = resolveRequestId(request);
        String requestId = resolution.requestId();
        request.setAttribute(ATTRIBUTE_NAME, requestId);
        ContentCachingResponseWrapper cachingResponse =
                new ContentCachingResponseWrapper(response);
        cachingResponse.setHeader(HEADER_NAME, requestId);

        MDC.put("request_id", requestId);
        MDC.put("method", request.getMethod());
        try {
            if (!resolution.valid()) {
                ApiExceptionHandler.writeError(
                        cachingResponse,
                        objectMapper,
                        HttpServletResponse.SC_BAD_REQUEST,
                        "INVALID_REQUEST_ID",
                        "The request ID is invalid.",
                        requestId,
                        Map.of());
                return;
            }
            if (request.getContentLengthLong() > NormalizationPolicy.MAX_REQUEST_BYTES) {
                ApiExceptionHandler.writeError(
                        cachingResponse,
                        objectMapper,
                        HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE,
                        "PAYLOAD_TOO_LARGE",
                        "The request body is too large.",
                        requestId,
                        Map.of("maximum_bytes", NormalizationPolicy.MAX_REQUEST_BYTES));
                return;
            }

            filterChain.doFilter(
                    new LimitedRequestWrapper(
                            request,
                            NormalizationPolicy.MAX_REQUEST_BYTES),
                    cachingResponse);
        } catch (PayloadTooLargeException exception) {
            if (!cachingResponse.isCommitted()) {
                cachingResponse.reset();
                cachingResponse.setHeader(HEADER_NAME, requestId);
                ApiExceptionHandler.writeError(
                        cachingResponse,
                        objectMapper,
                        HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE,
                        "PAYLOAD_TOO_LARGE",
                        "The request body is too large.",
                        requestId,
                        Map.of("maximum_bytes", NormalizationPolicy.MAX_REQUEST_BYTES));
            }
        } finally {
            sanitizeHealthResponse(request, cachingResponse);
            Object route = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            MDC.put("route", route == null ? "unmatched" : route.toString());
            MDC.put("status", Integer.toString(cachingResponse.getStatus()));
            MDC.put("response_size", Integer.toString(cachingResponse.getContentSize()));
            long durationMillis = (System.nanoTime() - started) / 1_000_000;
            MDC.put("duration_ms", Long.toString(durationMillis));
            LOGGER.info("http_request_completed");
            cachingResponse.copyBodyToResponse();
            MDC.clear();
        }
    }

    private static HeaderResolution resolveRequestId(HttpServletRequest request) {
        List<String> values = request.getHeaderNames() == null
                ? List.of()
                : Collections.list(request.getHeaders(HEADER_NAME));
        if (values.isEmpty()) {
            return new HeaderResolution(UUID.randomUUID().toString(), true);
        }
        if (values.size() != 1 || !VALID_REQUEST_ID.matcher(values.getFirst()).matches()) {
            return new HeaderResolution(UUID.randomUUID().toString(), false);
        }
        return new HeaderResolution(values.getFirst(), true);
    }

    private void sanitizeHealthResponse(
            HttpServletRequest request,
            ContentCachingResponseWrapper response) {
        String path = request.getRequestURI();
        boolean healthPath = path.equals("/actuator/health")
                || path.equals("/actuator/health/liveness")
                || path.equals("/actuator/health/readiness");
        if (!healthPath || response.getStatus() < 200 || response.getStatus() >= 300) {
            return;
        }
        try {
            com.fasterxml.jackson.databind.JsonNode body =
                    objectMapper.readTree(response.getContentAsByteArray());
            if (body != null && body.path("status").isTextual()) {
                String status = body.path("status").textValue();
                response.resetBuffer();
                objectMapper.writeValue(
                        response.getOutputStream(),
                        Map.of("status", status));
            }
        } catch (IOException exception) {
            LOGGER.warn("health_response_sanitization_failed");
        }
    }

    private record HeaderResolution(String requestId, boolean valid) {
    }

    public static final class PayloadTooLargeException extends IOException {

        public PayloadTooLargeException() {
            super("Request body byte limit exceeded");
        }
    }

    private static final class LimitedRequestWrapper extends HttpServletRequestWrapper {

        private final int maximumBytes;
        private ServletInputStream inputStream;

        private LimitedRequestWrapper(HttpServletRequest request, int maximumBytes) {
            super(request);
            this.maximumBytes = maximumBytes;
        }

        @Override
        public ServletInputStream getInputStream() throws IOException {
            if (inputStream == null) {
                inputStream = new LimitedServletInputStream(
                        super.getInputStream(),
                        maximumBytes);
            }
            return inputStream;
        }

        @Override
        public BufferedReader getReader() throws IOException {
            return new BufferedReader(
                    new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }
    }

    private static final class LimitedServletInputStream extends ServletInputStream {

        private final ServletInputStream delegate;
        private final int maximumBytes;
        private int bytesRead;

        private LimitedServletInputStream(
                ServletInputStream delegate,
                int maximumBytes) {
            this.delegate = delegate;
            this.maximumBytes = maximumBytes;
        }

        @Override
        public boolean isFinished() {
            return delegate.isFinished();
        }

        @Override
        public boolean isReady() {
            return delegate.isReady();
        }

        @Override
        public void setReadListener(ReadListener readListener) {
            delegate.setReadListener(readListener);
        }

        @Override
        public int read() throws IOException {
            int value = delegate.read();
            if (value >= 0) {
                addBytes(1);
            }
            return value;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            int count = delegate.read(buffer, offset, length);
            if (count > 0) {
                addBytes(count);
            }
            return count;
        }

        private void addBytes(int count) throws PayloadTooLargeException {
            bytesRead += count;
            if (bytesRead > maximumBytes) {
                throw new PayloadTooLargeException();
            }
        }
    }
}
