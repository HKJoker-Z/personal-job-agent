package io.github.hkjokerz.jobagent.jdnormalization.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;

@Schema(description = "Stable API error envelope")
public record ApiErrorResponse(
        @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
        ErrorBody error) {

    public static ApiErrorResponse of(
            String code,
            String message,
            String requestId,
            Map<String, Object> details) {
        return new ApiErrorResponse(new ErrorBody(code, message, requestId, details));
    }

    public record ErrorBody(
            @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
            String code,
            @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
            String message,
            @JsonProperty("request_id")
            @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
            String requestId,
            @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
            Map<String, Object> details) {

        public ErrorBody {
            details = details == null ? Map.of() : Map.copyOf(details);
        }
    }
}
