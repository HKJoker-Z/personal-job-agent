package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import java.util.Map;

public final class CreateApiException extends RuntimeException {

    private final String code;
    private final Map<String, Object> details;
    private final Integer retryAfterSeconds;

    private CreateApiException(
            String code,
            Map<String, Object> details,
            Integer retryAfterSeconds) {
        super(code);
        this.code = code;
        this.details = Map.copyOf(details);
        this.retryAfterSeconds = retryAfterSeconds;
    }

    public static CreateApiException keyRequired() {
        return new CreateApiException(
                "IDEMPOTENCY_KEY_REQUIRED",
                Map.of(),
                null);
    }

    public static CreateApiException keyInvalid() {
        return new CreateApiException(
                "IDEMPOTENCY_KEY_INVALID",
                Map.of(),
                null);
    }

    public static CreateApiException keyReused() {
        return new CreateApiException(
                "IDEMPOTENCY_KEY_REUSED",
                Map.of(),
                null);
    }

    public static CreateApiException inProgress(int retryAfterSeconds) {
        return new CreateApiException(
                "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                Map.of(),
                retryAfterSeconds);
    }

    public static CreateApiException persistenceFailed() {
        return new CreateApiException(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                Map.of(),
                null);
    }

    public String code() {
        return code;
    }

    public Map<String, Object> details() {
        return details;
    }

    public Integer retryAfterSeconds() {
        return retryAfterSeconds;
    }
}
