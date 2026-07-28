package io.github.hkjokerz.jobagent.jdnormalization.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

@Schema(description = "Bounded Job Description text and explicitly supplied metadata")
public record NormalizeJobDescriptionRequest(
        @NotNull
        @JsonProperty("raw_text")
        @Schema(requiredMode = Schema.RequiredMode.REQUIRED, maxLength = 100_000)
        String rawText,
        @Valid
        Metadata metadata) {

    public record Metadata(
            @Schema(maxLength = 200) String title,
            @Schema(maxLength = 200) String company,
            @Schema(maxLength = 200) String location,
            @JsonProperty("canonical_url")
            @Schema(maxLength = 2_048, format = "uri")
            String canonicalUrl) {
    }
}
