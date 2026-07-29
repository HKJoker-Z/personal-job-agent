package io.github.hkjokerz.jobagent.jdnormalization.persistence.read;

import java.util.Map;

public final class ReadApiException extends RuntimeException {

    private final String code;
    private final Map<String, Object> details;

    private ReadApiException(String code, Map<String, Object> details) {
        super(code);
        this.code = code;
        this.details = Map.copyOf(details);
    }

    public static ReadApiException notFound() {
        return new ReadApiException("JOB_DESCRIPTION_NOT_FOUND", Map.of());
    }

    public static ReadApiException invalidCursor() {
        return new ReadApiException("INVALID_CURSOR", Map.of());
    }

    public static ReadApiException invalidRequest(String field, String rule) {
        return new ReadApiException(
                "INVALID_REQUEST",
                Map.of("field", field, "rule", rule));
    }

    public String code() {
        return code;
    }

    public Map<String, Object> details() {
        return details;
    }
}
