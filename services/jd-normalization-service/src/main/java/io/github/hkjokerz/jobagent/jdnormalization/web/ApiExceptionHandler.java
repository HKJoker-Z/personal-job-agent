package io.github.hkjokerz.jobagent.jdnormalization.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationPolicy;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.ConstraintViolationException;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(NormalizationPolicy.Violation.class)
    ResponseEntity<ApiErrorResponse> handlePolicyViolation(
            NormalizationPolicy.Violation exception,
            HttpServletRequest request) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("field", exception.field());
        details.put("rule", exception.rule());
        details.putAll(exception.safeMetadata());
        String message = "EMPTY_JOB_DESCRIPTION".equals(exception.errorCode())
                ? "The Job Description must contain non-whitespace text."
                : "The request could not be processed.";
        return error(
                HttpStatus.UNPROCESSABLE_ENTITY,
                exception.errorCode(),
                message,
                request,
                details);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiErrorResponse> handleBeanValidation(
            MethodArgumentNotValidException exception,
            HttpServletRequest request) {
        Map<String, Object> details = new LinkedHashMap<>();
        exception.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .ifPresent(fieldError -> {
                    details.put("field", safeField(fieldError.getField()));
                    details.put("rule", "required");
                });
        return error(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "VALIDATION_FAILED",
                "The request could not be processed.",
                request,
                details);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    ResponseEntity<ApiErrorResponse> handleConstraintViolation(
            ConstraintViolationException exception,
            HttpServletRequest request) {
        return error(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "VALIDATION_FAILED",
                "The request could not be processed.",
                request,
                Map.of());
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiErrorResponse> handleUnreadableMessage(
            HttpMessageNotReadableException exception,
            HttpServletRequest request) {
        if (hasCause(exception, RequestIdFilter.PayloadTooLargeException.class)) {
            return error(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "PAYLOAD_TOO_LARGE",
                    "The request body is too large.",
                    request,
                    Map.of("maximum_bytes", NormalizationPolicy.MAX_REQUEST_BYTES));
        }
        return error(
                HttpStatus.BAD_REQUEST,
                "INVALID_REQUEST",
                "The request body is invalid.",
                request,
                Map.of());
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<ApiErrorResponse> handleUnsupportedMediaType(
            HttpMediaTypeNotSupportedException exception,
            HttpServletRequest request) {
        return error(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                "The request media type is unsupported.",
                request,
                Map.of());
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    ResponseEntity<ApiErrorResponse> handleMethodNotAllowed(
            HttpRequestMethodNotSupportedException exception,
            HttpServletRequest request) {
        return error(
                HttpStatus.METHOD_NOT_ALLOWED,
                "METHOD_NOT_ALLOWED",
                "The request method is not allowed.",
                request,
                Map.of());
    }

    @ExceptionHandler({NoHandlerFoundException.class, NoResourceFoundException.class})
    ResponseEntity<ApiErrorResponse> handleNotFound(
            Exception exception,
            HttpServletRequest request) {
        return error(
                HttpStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "The requested route was not found.",
                request,
                Map.of());
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiErrorResponse> handleInternalError(
            Exception exception,
            HttpServletRequest request) {
        LOGGER.error("internal_request_failure");
        return error(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "The request could not be completed.",
                request,
                Map.of());
    }

    public static void writeError(
            HttpServletResponse response,
            ObjectMapper objectMapper,
            int status,
            String code,
            String message,
            String requestId,
            Map<String, Object> details) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader(RequestIdFilter.HEADER_NAME, requestId);
        objectMapper.writeValue(
                response.getOutputStream(),
                ApiErrorResponse.of(code, message, requestId, details));
    }

    private static ResponseEntity<ApiErrorResponse> error(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request,
            Map<String, Object> details) {
        String requestId = trustedRequestId(request);
        return ResponseEntity.status(status)
                .header(RequestIdFilter.HEADER_NAME, requestId)
                .header("Cache-Control", "no-store")
                .body(ApiErrorResponse.of(code, message, requestId, details));
    }

    public static String trustedRequestId(HttpServletRequest request) {
        Object value = request.getAttribute(RequestIdFilter.ATTRIBUTE_NAME);
        return value instanceof String requestId
                ? requestId
                : java.util.UUID.randomUUID().toString();
    }

    private static String safeField(String field) {
        return switch (field) {
            case "rawText" -> "raw_text";
            case "metadata.title" -> "metadata.title";
            case "metadata.company" -> "metadata.company";
            case "metadata.location" -> "metadata.location";
            case "metadata.canonicalUrl" -> "metadata.canonical_url";
            default -> "request";
        };
    }

    private static boolean hasCause(Throwable throwable, Class<?> causeType) {
        Throwable current = throwable;
        while (current != null) {
            if (causeType.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
