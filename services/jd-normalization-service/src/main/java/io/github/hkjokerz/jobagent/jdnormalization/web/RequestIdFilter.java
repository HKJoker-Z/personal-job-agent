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
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
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
            if (request.getRequestURI().equals("/v3/api-docs.yaml")) {
                ApiExceptionHandler.writeError(
                        cachingResponse,
                        objectMapper,
                        HttpServletResponse.SC_NOT_FOUND,
                        "ROUTE_NOT_FOUND",
                        "The requested route was not found.",
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
        } catch (InvalidUtf8Exception exception) {
            if (!cachingResponse.isCommitted()) {
                cachingResponse.reset();
                cachingResponse.setHeader(HEADER_NAME, requestId);
                ApiExceptionHandler.writeError(
                        cachingResponse,
                        objectMapper,
                        HttpServletResponse.SC_BAD_REQUEST,
                        "INVALID_REQUEST",
                        "The request body is invalid.",
                        requestId,
                        Map.of());
            }
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
            try {
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
            } finally {
                MDC.clear();
            }
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

    public static final class InvalidUtf8Exception extends IOException {

        public InvalidUtf8Exception() {
            super("Request body must be valid UTF-8 JSON");
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
                byte[] body = super.getInputStream().readNBytes(maximumBytes + 1);
                if (body.length > maximumBytes) {
                    throw new PayloadTooLargeException();
                }
                validateUtf8JsonBytes(body);
                inputStream = new ByteArrayServletInputStream(body);
            }
            return inputStream;
        }

        @Override
        public BufferedReader getReader() throws IOException {
            return new BufferedReader(
                    new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }

        private static void validateUtf8JsonBytes(byte[] body) throws InvalidUtf8Exception {
            for (byte value : body) {
                if (value == 0) {
                    throw new InvalidUtf8Exception();
                }
            }
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(body));
            } catch (CharacterCodingException exception) {
                throw new InvalidUtf8Exception();
            }
        }
    }

    private static final class ByteArrayServletInputStream extends ServletInputStream {

        private final ByteArrayInputStream delegate;

        private ByteArrayServletInputStream(byte[] body) {
            delegate = new ByteArrayInputStream(body);
        }

        @Override
        public boolean isFinished() {
            return delegate.available() == 0;
        }

        @Override
        public boolean isReady() {
            return true;
        }

        @Override
        public void setReadListener(ReadListener readListener) {
            throw new IllegalStateException("Asynchronous request reads are not supported");
        }

        @Override
        public int read() {
            return delegate.read();
        }

        @Override
        public int read(byte[] buffer, int offset, int length) {
            return delegate.read(buffer, offset, length);
        }
    }
}
