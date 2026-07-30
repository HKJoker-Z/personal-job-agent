package io.github.hkjokerz.jobagent.jdnormalization.web;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.hibernate.exception.JDBCConnectionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class PersistenceApiExceptionHandler {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(PersistenceApiExceptionHandler.class);

    @ExceptionHandler(UpdateApiException.class)
    ResponseEntity<ApiErrorResponse> handleUpdateApiException(
            UpdateApiException exception,
            HttpServletRequest request) {
        HttpStatus status = switch (exception.code()) {
            case "PRECONDITION_REQUIRED" -> HttpStatus.PRECONDITION_REQUIRED;
            case "INVALID_IF_MATCH" -> HttpStatus.BAD_REQUEST;
            case "PRECONDITION_FAILED" -> HttpStatus.PRECONDITION_FAILED;
            case "JOB_DESCRIPTION_NOT_FOUND" -> HttpStatus.NOT_FOUND;
            case "JOB_DESCRIPTION_ALREADY_EXISTS" -> HttpStatus.CONFLICT;
            default -> HttpStatus.INTERNAL_SERVER_ERROR;
        };
        String message = switch (exception.code()) {
            case "PRECONDITION_REQUIRED" -> "An If-Match header is required.";
            case "INVALID_IF_MATCH" -> "The If-Match header is invalid.";
            case "PRECONDITION_FAILED" ->
                    "The If-Match value does not match the current resource.";
            case "JOB_DESCRIPTION_NOT_FOUND" ->
                    "The Job Description was not found.";
            case "JOB_DESCRIPTION_ALREADY_EXISTS" ->
                    "The Job Description already exists.";
            default -> "The request could not be completed.";
        };
        return ApiExceptionHandler.error(
                status,
                exception.code(),
                message,
                request,
                exception.details());
    }

    @ExceptionHandler(CreateApiException.class)
    ResponseEntity<ApiErrorResponse> handleCreateApiException(
            CreateApiException exception,
            HttpServletRequest request) {
        HttpStatus status = switch (exception.code()) {
            case "IDEMPOTENCY_KEY_REQUIRED", "IDEMPOTENCY_KEY_INVALID" ->
                    HttpStatus.BAD_REQUEST;
            case "IDEMPOTENCY_KEY_REUSED", "IDEMPOTENCY_REQUEST_IN_PROGRESS" ->
                    HttpStatus.CONFLICT;
            default -> HttpStatus.INTERNAL_SERVER_ERROR;
        };
        String message = switch (exception.code()) {
            case "IDEMPOTENCY_KEY_REQUIRED" ->
                    "An Idempotency-Key header is required.";
            case "IDEMPOTENCY_KEY_INVALID" ->
                    "The Idempotency-Key header is invalid.";
            case "IDEMPOTENCY_KEY_REUSED" ->
                    "The Idempotency-Key was already used for a different request.";
            case "IDEMPOTENCY_REQUEST_IN_PROGRESS" ->
                    "A request using this Idempotency-Key is still processing.";
            default -> "The idempotent result could not be persisted.";
        };
        String requestId = ApiExceptionHandler.trustedRequestId(request);
        ResponseEntity.BodyBuilder builder = ResponseEntity.status(status)
                .header(RequestIdFilter.HEADER_NAME, requestId)
                .header("Cache-Control", "no-store");
        if (exception.retryAfterSeconds() != null) {
            builder.header(
                    "Retry-After",
                    Integer.toString(exception.retryAfterSeconds()));
        }
        return builder.body(ApiErrorResponse.of(
                exception.code(),
                message,
                requestId,
                exception.details()));
    }

    @ExceptionHandler(ReadApiException.class)
    ResponseEntity<ApiErrorResponse> handleReadApiException(
            ReadApiException exception,
            HttpServletRequest request) {
        HttpStatus status = switch (exception.code()) {
            case "JOB_DESCRIPTION_NOT_FOUND" -> HttpStatus.NOT_FOUND;
            case "INVALID_CURSOR", "INVALID_REQUEST" -> HttpStatus.BAD_REQUEST;
            default -> HttpStatus.INTERNAL_SERVER_ERROR;
        };
        String message = switch (exception.code()) {
            case "JOB_DESCRIPTION_NOT_FOUND" -> "The Job Description was not found.";
            case "INVALID_CURSOR" -> "The pagination cursor is invalid.";
            default -> "The request could not be processed.";
        };
        return ApiExceptionHandler.error(
                status,
                exception.code(),
                message,
                request,
                exception.details());
    }

    @ExceptionHandler({
        DataAccessResourceFailureException.class,
        CannotCreateTransactionException.class,
        JDBCConnectionException.class
    })
    ResponseEntity<ApiErrorResponse> handleDatabaseUnavailable(
            Exception exception,
            HttpServletRequest request) {
        LOGGER.error("database_unavailable");
        return ApiExceptionHandler.error(
                HttpStatus.SERVICE_UNAVAILABLE,
                "DATABASE_UNAVAILABLE",
                "The database is temporarily unavailable.",
                request,
                Map.of());
    }

    @ExceptionHandler(DataAccessException.class)
    ResponseEntity<ApiErrorResponse> handleDatabaseFailure(
            DataAccessException exception,
            HttpServletRequest request) {
        LOGGER.error("database_read_failure");
        return ApiExceptionHandler.error(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "The request could not be completed.",
                request,
                Map.of());
    }
}
