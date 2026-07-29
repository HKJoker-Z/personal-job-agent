package io.github.hkjokerz.jobagent.jdnormalization.persistence.read;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class ReadModels {

    private ReadModels() {
    }

    public record Current(
            UUID id,
            String canonicalUrl,
            long optimisticLockVersion,
            int currentVersionNumber,
            String normalizedText,
            byte[] contentHash,
            String normalizationPolicyVersion,
            String skillDictionaryVersion,
            List<SkillSnapshot> requiredSkills,
            List<SkillSnapshot> preferredSkills,
            List<SkillSnapshot> mentionedSkills,
            String title,
            String company,
            String location,
            Instant createdAt,
            Instant updatedAt) {

        public Current {
            contentHash = contentHash.clone();
            requiredSkills = List.copyOf(requiredSkills);
            preferredSkills = List.copyOf(preferredSkills);
            mentionedSkills = List.copyOf(mentionedSkills);
        }
    }

    public record Summary(
            UUID id,
            String canonicalUrl,
            long optimisticLockVersion,
            int currentVersionNumber,
            String title,
            String company,
            String location,
            byte[] contentHash,
            Instant createdAt,
            Instant updatedAt) {

        public Summary {
            contentHash = contentHash.clone();
        }
    }

    public record Version(
            UUID versionId,
            int versionNumber,
            String normalizedText,
            byte[] contentHash,
            String normalizationPolicyVersion,
            String skillDictionaryVersion,
            List<SkillSnapshot> requiredSkills,
            List<SkillSnapshot> preferredSkills,
            List<SkillSnapshot> mentionedSkills,
            String title,
            String company,
            String location,
            Instant createdAt) {

        public Version {
            contentHash = contentHash.clone();
            requiredSkills = List.copyOf(requiredSkills);
            preferredSkills = List.copyOf(preferredSkills);
            mentionedSkills = List.copyOf(mentionedSkills);
        }
    }

    public record Slice<T>(List<T> items, String nextCursor) {

        public Slice {
            items = List.copyOf(items);
        }
    }
}
