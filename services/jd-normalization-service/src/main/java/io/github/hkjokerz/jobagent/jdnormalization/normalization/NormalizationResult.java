package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.util.List;

public record NormalizationResult(
        String normalizedText,
        String contentHash,
        String normalizationPolicyVersion,
        String skillDictionaryVersion,
        List<SkillDictionary.Skill> requiredSkills,
        List<SkillDictionary.Skill> preferredSkills,
        List<SkillDictionary.Skill> mentionedSkills,
        Metadata metadata) {

    public NormalizationResult {
        requiredSkills = List.copyOf(requiredSkills);
        preferredSkills = List.copyOf(preferredSkills);
        mentionedSkills = List.copyOf(mentionedSkills);
    }

    public record Metadata(
            String title,
            String company,
            String location,
            String canonicalUrl) {
    }
}
