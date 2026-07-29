package io.github.hkjokerz.jobagent.jdnormalization.persistence.repository;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescription;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface JobDescriptionRepository extends Repository<JobDescription, UUID> {

    boolean existsById(UUID id);

    @Query("""
            select
                j.id as id,
                j.canonicalUrl as canonicalUrl,
                j.optimisticLockVersion as optimisticLockVersion,
                v.versionNumber as currentVersionNumber,
                v.normalizedText as normalizedText,
                v.contentHash as contentHash,
                v.normalizationPolicyVersion as normalizationPolicyVersion,
                v.skillDictionaryVersion as skillDictionaryVersion,
                v.requiredSkills as requiredSkills,
                v.preferredSkills as preferredSkills,
                v.mentionedSkills as mentionedSkills,
                v.title as title,
                v.company as company,
                v.location as location,
                j.createdAt as createdAt,
                j.updatedAt as updatedAt
            from JobDescription j, JobDescriptionVersion v
            where j.id = :id
              and v.id = j.currentVersionId
              and v.jobDescriptionId = j.id
            """)
    Optional<CurrentProjection> findCurrent(@Param("id") UUID id);

    interface CurrentProjection {

        UUID getId();

        String getCanonicalUrl();

        long getOptimisticLockVersion();

        int getCurrentVersionNumber();

        String getNormalizedText();

        byte[] getContentHash();

        String getNormalizationPolicyVersion();

        String getSkillDictionaryVersion();

        List<SkillSnapshot> getRequiredSkills();

        List<SkillSnapshot> getPreferredSkills();

        List<SkillSnapshot> getMentionedSkills();

        String getTitle();

        String getCompany();

        String getLocation();

        Instant getCreatedAt();

        Instant getUpdatedAt();
    }
}
