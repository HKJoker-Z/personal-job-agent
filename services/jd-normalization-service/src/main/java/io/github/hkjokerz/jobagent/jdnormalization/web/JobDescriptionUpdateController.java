package io.github.hkjokerz.jobagent.jdnormalization.web;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.JobDescriptionUpdateService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateResult;
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
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/job-descriptions")
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
@SecurityRequirement(name = "internalApiKey")
public class JobDescriptionUpdateController {

    private static final String NO_STORE = "no-store";

    private final JobDescriptionUpdateService updateService;

    public JobDescriptionUpdateController(
            JobDescriptionUpdateService updateService) {
        this.updateService = updateService;
    }

    @PutMapping(
            value = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Conditionally replace the current Job Description state",
            description = "Requires one strong If-Match ETag. A changed replacement "
                    + "atomically creates one immutable version and advances the root. "
                    + "An effective no-op performs no write. PUT does not use "
                    + "Idempotency-Key and performs no external provider call.")
    @Parameter(
            name = "If-Match",
            in = ParameterIn.HEADER,
            required = true,
            description = "One strong quoted nonnegative decimal aggregate version, "
                    + "for example \"0\"",
            schema = @Schema(
                    maxLength = 21,
                    pattern = "^\"(?:0|[1-9][0-9]{0,18})\"$"))
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented "
                    + "64-character grammar")
    @ApiResponses({
        @ApiResponse(
                responseCode = "200",
                description = "Updated or unchanged current resource",
                headers = {
                    @Header(
                            name = "ETag",
                            description = "Current strong optimistic-lock ETag",
                            schema = @Schema(type = "string")),
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
                description = "If-Match or request syntax is invalid",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "401",
                description = "Authentication failed",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "404",
                description = "Job Description not found",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "409",
                description = "Canonical URL or deduplication conflict",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "412",
                description = "If-Match does not match the current aggregate version",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "428",
                description = "If-Match is required",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "500",
                description = "Unexpected persistence failure",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "503",
                description = "Database unavailable",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<JobDescriptionReadResponses.Current> update(
            @PathVariable String id,
            @Valid @RequestBody NormalizeJobDescriptionRequest request,
            HttpServletRequest servletRequest) {
        UUID aggregateId = uuid(id);
        long expectedVersion = StrongEtag.requiredIfMatch(servletRequest);
        UpdateResult result =
                updateService.update(aggregateId, expectedVersion, request);
        String etag = "\"" + result.current().optimisticLockVersion() + "\"";
        return ResponseEntity.ok()
                .eTag(etag)
                .header("Cache-Control", NO_STORE)
                .body(JobDescriptionReadResponses.Current.from(result.current()));
    }

    private static UUID uuid(String value) {
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException exception) {
            throw ReadApiException.invalidRequest("id", "uuid");
        }
    }
}
