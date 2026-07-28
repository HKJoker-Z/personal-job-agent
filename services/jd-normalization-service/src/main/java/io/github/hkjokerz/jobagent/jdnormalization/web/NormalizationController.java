package io.github.hkjokerz.jobagent.jdnormalization.web;

import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/job-descriptions")
public class NormalizationController {

    private final JobDescriptionNormalizer normalizer;

    public NormalizationController(JobDescriptionNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @PostMapping(
            path = "/normalize",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Normalize one Job Description deterministically",
            description = "Returns normalized text, its SHA-256 hash, lexical skill matches, "
                    + "and normalized explicitly supplied metadata.",
            security = @SecurityRequirement(name = "internalApiKey"))
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented 64-character grammar")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Normalized result"),
        @ApiResponse(
                responseCode = "400",
                description = "Invalid request",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "401",
                description = "Authentication failed",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "413",
                description = "Request body too large",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class))),
        @ApiResponse(
                responseCode = "422",
                description = "Validation failed",
                content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public ResponseEntity<NormalizeJobDescriptionResponse> normalize(
            @Valid @RequestBody NormalizeJobDescriptionRequest request,
            @RequestHeader(value = "X-Request-ID", required = false)
                    String ignoredRequestId) {
        return ResponseEntity.ok()
                .header("Cache-Control", "no-store")
                .body(NormalizeJobDescriptionResponse.from(normalizer.normalize(request)));
    }
}
