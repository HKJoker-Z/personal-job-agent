package io.github.hkjokerz.jobagent.jdnormalization.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.SkillDictionary;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

@Schema(description = "Deterministic normalized representation")
public record NormalizeJobDescriptionResponse(
        @JsonProperty("normalized_text") String normalizedText,
        @JsonProperty("content_hash")
        @Schema(pattern = "^[0-9a-f]{64}$")
        String contentHash,
        @JsonProperty("normalization_policy_version") String normalizationPolicyVersion,
        @JsonProperty("skill_dictionary_version") String skillDictionaryVersion,
        @JsonProperty("required_skills") List<Skill> requiredSkills,
        @JsonProperty("preferred_skills") List<Skill> preferredSkills,
        @JsonProperty("mentioned_skills") List<Skill> mentionedSkills,
        Metadata metadata) {

    public static NormalizeJobDescriptionResponse from(NormalizationResult result) {
        return new NormalizeJobDescriptionResponse(
                result.normalizedText(),
                result.contentHash(),
                result.normalizationPolicyVersion(),
                result.skillDictionaryVersion(),
                result.requiredSkills().stream().map(Skill::from).toList(),
                result.preferredSkills().stream().map(Skill::from).toList(),
                result.mentionedSkills().stream().map(Skill::from).toList(),
                new Metadata(
                        result.metadata().title(),
                        result.metadata().company(),
                        result.metadata().location(),
                        result.metadata().canonicalUrl()));
    }

    public record Skill(String id, String name) {

        static Skill from(SkillDictionary.Skill skill) {
            return new Skill(skill.id(), skill.name());
        }
    }

    public record Metadata(
            String title,
            String company,
            String location,
            @JsonProperty("canonical_url") String canonicalUrl) {
    }
}
