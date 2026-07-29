package io.github.hkjokerz.jobagent.jdnormalization.web;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.CursorCodec;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.JobDescriptionReadService;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadApiException;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.JobDescriptionReadResponses;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/job-descriptions")
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
@SecurityRequirement(name = "internalApiKey")
@ApiResponses({
    @ApiResponse(
            responseCode = "400",
            description = "Invalid request or cursor",
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
            responseCode = "503",
            description = "Database unavailable",
            content = @Content(schema = @Schema(implementation = ApiErrorResponse.class)))
})
public class JobDescriptionReadController {

    private static final Pattern STRONG_ETAG = Pattern.compile("\"(?:0|[1-9][0-9]*)\"");
    private static final String CURRENT_CACHE_CONTROL = "private, max-age=0, must-revalidate";
    private static final String COLLECTION_CACHE_CONTROL = "private, no-store";

    private final JobDescriptionReadService readService;
    private final CursorCodec cursorCodec;

    public JobDescriptionReadController(
            JobDescriptionReadService readService,
            CursorCodec cursorCodec) {
        this.readService = readService;
        this.cursorCodec = cursorCodec;
    }

    @GetMapping
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented 64-character grammar")
    @Operation(
            summary = "List bounded current Job Description summaries",
            description = "Uses an opaque filter-bound keyset cursor; no total count is computed.")
    @ApiResponse(
            responseCode = "200",
            description = "Bounded summary page",
            content = @Content(
                    schema = @Schema(
                            implementation =
                                    JobDescriptionReadResponses.ListResponse.class)))
    public ResponseEntity<JobDescriptionReadResponses.ListResponse> list(
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false) String sort,
            @RequestParam(required = false) String cursor,
            @RequestParam(required = false) String title,
            @RequestParam(required = false) String company,
            @RequestParam(required = false) String location,
            @RequestParam(name = "content_hash", required = false) String contentHash,
            @RequestParam(name = "canonical_url", required = false) String canonicalUrl) {
        int boundedLimit = boundedLimit(limit, 20, 100);
        CursorCodec.ListSort parsedSort = CursorCodec.ListSort.parse(sort);
        CursorCodec.NormalizedFilters filters = cursorCodec.normalizeFilters(
                title,
                company,
                location,
                contentHash,
                canonicalUrl);
        CursorCodec.ListCursor parsedCursor = cursorCodec.decodeListCursor(
                cursor,
                parsedSort,
                filters.fingerprint());
        return ResponseEntity.ok()
                .header("Cache-Control", COLLECTION_CACHE_CONTROL)
                .body(JobDescriptionReadResponses.ListResponse.from(
                        readService.list(
                                boundedLimit,
                                parsedSort,
                                filters,
                                parsedCursor)));
    }

    @GetMapping("/{id}")
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented 64-character grammar")
    @Operation(
            summary = "Read the exact current immutable Job Description version",
            description = "Returns a strong aggregate-version ETag and supports If-None-Match.")
    @ApiResponses({
        @ApiResponse(
                responseCode = "200",
                description = "Current resource",
                content = @Content(
                        schema = @Schema(
                                implementation =
                                        JobDescriptionReadResponses.Current.class))),
        @ApiResponse(responseCode = "304", description = "ETag matched")
    })
    public ResponseEntity<JobDescriptionReadResponses.Current> current(
            @org.springframework.web.bind.annotation.PathVariable String id,
            HttpServletRequest request) {
        UUID aggregateId = uuid(id);
        String suppliedEtag = oneIfNoneMatch(request);
        ReadModels.Current current = readService.current(aggregateId);
        String etag = "\"" + current.optimisticLockVersion() + "\"";
        if (etag.equals(suppliedEtag)) {
            return ResponseEntity.status(304)
                    .eTag(etag)
                    .header("Cache-Control", CURRENT_CACHE_CONTROL)
                    .build();
        }
        return ResponseEntity.ok()
                .eTag(etag)
                .header("Cache-Control", CURRENT_CACHE_CONTROL)
                .body(JobDescriptionReadResponses.Current.from(current));
    }

    @GetMapping("/{id}/versions")
    @Parameter(
            name = "X-Request-ID",
            in = ParameterIn.HEADER,
            description = "Optional correlation ID matching the documented 64-character grammar")
    @Operation(
            summary = "List committed immutable versions",
            description = "Uses bounded keyset pagination by version number.")
    @ApiResponse(
            responseCode = "200",
            description = "Immutable version page",
            content = @Content(
                    schema = @Schema(
                            implementation =
                                    JobDescriptionReadResponses.VersionHistoryResponse.class)))
    public ResponseEntity<JobDescriptionReadResponses.VersionHistoryResponse> versions(
            @org.springframework.web.bind.annotation.PathVariable String id,
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false) String sort,
            @RequestParam(required = false) String cursor) {
        UUID aggregateId = uuid(id);
        int boundedLimit = boundedLimit(limit, 10, 25);
        CursorCodec.VersionSort parsedSort = CursorCodec.VersionSort.parse(sort);
        CursorCodec.VersionCursor parsedCursor =
                cursorCodec.decodeVersionCursor(cursor, parsedSort);
        return ResponseEntity.ok()
                .header("Cache-Control", COLLECTION_CACHE_CONTROL)
                .body(JobDescriptionReadResponses.VersionHistoryResponse.from(
                        aggregateId,
                        readService.versions(
                                aggregateId,
                                boundedLimit,
                                parsedSort,
                                parsedCursor)));
    }

    private static int boundedLimit(Integer supplied, int defaultValue, int maximum) {
        int value = supplied == null ? defaultValue : supplied;
        if (value < 1 || value > maximum) {
            throw ReadApiException.invalidRequest("limit", "range_1_" + maximum);
        }
        return value;
    }

    private static UUID uuid(String supplied) {
        try {
            return UUID.fromString(supplied);
        } catch (IllegalArgumentException exception) {
            throw ReadApiException.invalidRequest("id", "uuid");
        }
    }

    private static String oneIfNoneMatch(HttpServletRequest request) {
        List<String> values = Collections.list(request.getHeaders("If-None-Match"));
        if (values.isEmpty()) {
            return null;
        }
        if (values.size() != 1 || !STRONG_ETAG.matcher(values.getFirst()).matches()) {
            throw ReadApiException.invalidRequest("if_none_match", "single_strong_etag");
        }
        return values.getFirst();
    }
}
