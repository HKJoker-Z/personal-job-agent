package io.github.hkjokerz.jobagent.jdnormalization.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CompletedCreateResponse;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.JobDescriptionCreateService;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.JobDescriptionReadResponses;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/job-descriptions")
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class JobDescriptionCreateController {

    static final String IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";
    static final String REPLAYED_HEADER = "Idempotency-Replayed";
    static final String REPLAY_ATTRIBUTE =
            JobDescriptionCreateController.class.getName() + ".replayed";
    static final String OUTCOME_ATTRIBUTE =
            JobDescriptionCreateController.class.getName() + ".outcome";
    static final String CREATED_ID_ATTRIBUTE =
            JobDescriptionCreateController.class.getName() + ".createdId";
    private static final Pattern VALID_KEY =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{15,127}");

    private final JobDescriptionCreateService createService;

    public JobDescriptionCreateController(JobDescriptionCreateService createService) {
        this.createService = createService;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Create an immutable Job Description aggregate idempotently",
            description = "Requires one valid Idempotency-Key. PostgreSQL atomically creates "
                    + "the aggregate, immutable version 1, and completed replay result. "
                    + "No external provider is called.",
            security = @SecurityRequirement(name = "internalApiKey"))
    @Parameter(
            name = IDEMPOTENCY_KEY_HEADER,
            in = ParameterIn.HEADER,
            required = true,
            description = "16-128 ASCII characters matching "
                    + "[A-Za-z0-9][A-Za-z0-9._:-]{15,127}; UUIDv4 is recommended",
            schema = @Schema(
                    minLength = 16,
                    maxLength = 128,
                    pattern = "^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"))
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented 64-character grammar")
    @ApiResponses({
        @ApiResponse(
                responseCode = "201",
                description = "Created current resource, or exact completed-result replay",
                headers = {
                    @Header(
                            name = "Location",
                            description = "Current-resource path stored with the result",
                            schema = @Schema(type = "string")),
                    @Header(
                            name = "ETag",
                            description = "Stored optimistic-lock validator; initially \"0\"",
                            schema = @Schema(type = "string")),
                    @Header(
                            name = "Idempotency-Replayed",
                            description = "Present with value true only for a completed replay",
                            schema = @Schema(type = "boolean")),
                    @Header(
                            name = "Cache-Control",
                            description = "Always no-store",
                            schema = @Schema(type = "string"))
                },
                content = @Content(
                        schema = @Schema(
                                implementation =
                                        JobDescriptionReadResponses.Current.class))),
        @ApiResponse(
                responseCode = "400",
                description = "Idempotency-Key is missing or invalid",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "401",
                description = "Authentication failed",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "409",
                description = "Key reuse, active processing, or duplicate resource",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "500",
                description = "The idempotency result could not be safely persisted",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<JsonNode> create(
            @Valid @RequestBody NormalizeJobDescriptionRequest request,
            HttpServletRequest servletRequest) {
        String key = idempotencyKey(servletRequest);
        String requestId = ApiExceptionHandler.trustedRequestId(servletRequest);
        CompletedCreateResponse response =
                createService.create(key, request, requestId);
        servletRequest.setAttribute(
                REPLAY_ATTRIBUTE,
                Boolean.toString(response.replayed()));
        servletRequest.setAttribute(
                OUTCOME_ATTRIBUTE,
                switch (response.status()) {
                    case 201 -> "created";
                    case 409 -> "duplicate";
                    default -> "persistence_failed";
                });
        if (response.status() == 201
                && !response.replayed()
                && response.jobDescriptionId() != null) {
            servletRequest.setAttribute(
                    CREATED_ID_ATTRIBUTE,
                    response.jobDescriptionId().toString());
        }
        ResponseEntity.BodyBuilder builder = ResponseEntity.status(response.status())
                .header(HttpHeaders.CACHE_CONTROL, "no-store");
        if (response.location() != null) {
            builder.header(HttpHeaders.LOCATION, response.location());
        }
        if (response.etag() != null) {
            builder.header(HttpHeaders.ETAG, response.etag());
        }
        if (response.replayed()) {
            builder.header(REPLAYED_HEADER, "true");
        }
        return builder.body(response.body());
    }

    private static String idempotencyKey(HttpServletRequest request) {
        List<String> values = request.getHeaderNames() == null
                ? List.of()
                : Collections.list(request.getHeaders(IDEMPOTENCY_KEY_HEADER));
        if (values.isEmpty()) {
            throw CreateApiException.keyRequired();
        }
        if (values.size() != 1 || !VALID_KEY.matcher(values.getFirst()).matches()) {
            throw CreateApiException.keyInvalid();
        }
        return values.getFirst();
    }
}
