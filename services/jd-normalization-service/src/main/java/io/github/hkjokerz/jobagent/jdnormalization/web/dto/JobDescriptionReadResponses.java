package io.github.hkjokerz.jobagent.jdnormalization.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

public final class JobDescriptionReadResponses {

    private JobDescriptionReadResponses() {
    }

    @Schema(description = "Current immutable version and aggregate metadata")
    public record Current(
            UUID id,
            @JsonProperty("canonical_url") String canonicalUrl,
            @JsonProperty("optimistic_lock_version") long optimisticLockVersion,
            @JsonProperty("current_version_number") int currentVersionNumber,
            @JsonProperty("normalized_text") String normalizedText,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("normalization_policy_version") String normalizationPolicyVersion,
            @JsonProperty("skill_dictionary_version") String skillDictionaryVersion,
            @JsonProperty("required_skills") List<Skill> requiredSkills,
            @JsonProperty("preferred_skills") List<Skill> preferredSkills,
            @JsonProperty("mentioned_skills") List<Skill> mentionedSkills,
            Metadata metadata,
            @JsonProperty("created_at") Instant createdAt,
            @JsonProperty("updated_at") Instant updatedAt) {

        public static Current from(ReadModels.Current value) {
            return new Current(
                    value.id(),
                    value.canonicalUrl(),
                    value.optimisticLockVersion(),
                    value.currentVersionNumber(),
                    value.normalizedText(),
                    hex(value.contentHash()),
                    value.normalizationPolicyVersion(),
                    value.skillDictionaryVersion(),
                    skills(value.requiredSkills()),
                    skills(value.preferredSkills()),
                    skills(value.mentionedSkills()),
                    new Metadata(value.title(), value.company(), value.location()),
                    value.createdAt(),
                    value.updatedAt());
        }
    }

    public record ListResponse(
            List<Summary> items,
            @JsonProperty("next_cursor") String nextCursor) {

        public ListResponse {
            items = List.copyOf(items);
        }

        public static ListResponse from(ReadModels.Slice<ReadModels.Summary> value) {
            return new ListResponse(
                    value.items().stream().map(Summary::from).toList(),
                    value.nextCursor());
        }
    }

    public record Summary(
            UUID id,
            @JsonProperty("canonical_url") String canonicalUrl,
            @JsonProperty("optimistic_lock_version") long optimisticLockVersion,
            @JsonProperty("current_version_number") int currentVersionNumber,
            Metadata metadata,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("created_at") Instant createdAt,
            @JsonProperty("updated_at") Instant updatedAt) {

        static Summary from(ReadModels.Summary value) {
            return new Summary(
                    value.id(),
                    value.canonicalUrl(),
                    value.optimisticLockVersion(),
                    value.currentVersionNumber(),
                    new Metadata(value.title(), value.company(), value.location()),
                    hex(value.contentHash()),
                    value.createdAt(),
                    value.updatedAt());
        }
    }

    public record VersionHistoryResponse(
            @JsonProperty("job_description_id") UUID jobDescriptionId,
            List<Version> items,
            @JsonProperty("next_cursor") String nextCursor) {

        public VersionHistoryResponse {
            items = List.copyOf(items);
        }

        public static VersionHistoryResponse from(
                UUID jobDescriptionId,
                ReadModels.Slice<ReadModels.Version> value) {
            return new VersionHistoryResponse(
                    jobDescriptionId,
                    value.items().stream().map(Version::from).toList(),
                    value.nextCursor());
        }
    }

    public record Version(
            @JsonProperty("version_id") UUID versionId,
            @JsonProperty("version_number") int versionNumber,
            @JsonProperty("normalized_text") String normalizedText,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("normalization_policy_version") String normalizationPolicyVersion,
            @JsonProperty("skill_dictionary_version") String skillDictionaryVersion,
            @JsonProperty("required_skills") List<Skill> requiredSkills,
            @JsonProperty("preferred_skills") List<Skill> preferredSkills,
            @JsonProperty("mentioned_skills") List<Skill> mentionedSkills,
            Metadata metadata,
            @JsonProperty("created_at") Instant createdAt) {

        static Version from(ReadModels.Version value) {
            return new Version(
                    value.versionId(),
                    value.versionNumber(),
                    value.normalizedText(),
                    hex(value.contentHash()),
                    value.normalizationPolicyVersion(),
                    value.skillDictionaryVersion(),
                    skills(value.requiredSkills()),
                    skills(value.preferredSkills()),
                    skills(value.mentionedSkills()),
                    new Metadata(value.title(), value.company(), value.location()),
                    value.createdAt());
        }
    }

    public record Metadata(String title, String company, String location) {
    }

    public record Skill(String id, String name) {
    }

    private static List<Skill> skills(List<SkillSnapshot> values) {
        return values.stream().map(value -> new Skill(value.id(), value.name())).toList();
    }

    private static String hex(byte[] value) {
        return HexFormat.of().formatHex(value);
    }
}
