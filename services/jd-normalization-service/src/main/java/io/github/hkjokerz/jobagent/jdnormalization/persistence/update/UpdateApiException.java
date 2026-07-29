package io.github.hkjokerz.jobagent.jdnormalization.persistence.update;

import java.util.Map;
import java.util.UUID;

public final class UpdateApiException extends RuntimeException {

    private final String code;
    private final Map<String, Object> details;

    private UpdateApiException(String code, Map<String, Object> details) {
        super(code);
        this.code = code;
        this.details = Map.copyOf(details);
    }

    public static UpdateApiException preconditionRequired() {
        return new UpdateApiException("PRECONDITION_REQUIRED", Map.of());
    }

    public static UpdateApiException invalidIfMatch() {
        return new UpdateApiException("INVALID_IF_MATCH", Map.of());
    }

    public static UpdateApiException preconditionFailed() {
        return new UpdateApiException("PRECONDITION_FAILED", Map.of());
    }

    public static UpdateApiException notFound() {
        return new UpdateApiException("JOB_DESCRIPTION_NOT_FOUND", Map.of());
    }

    public static UpdateApiException alreadyExists(
            String category,
            UUID jobDescriptionId) {
        return new UpdateApiException(
                "JOB_DESCRIPTION_ALREADY_EXISTS",
                Map.of(
                        "conflict_category", category,
                        "job_description_id", jobDescriptionId.toString()));
    }

    public String code() {
        return code;
    }

    public Map<String, Object> details() {
        return details;
    }
}
