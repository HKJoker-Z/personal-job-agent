package io.github.hkjokerz.jobagent.jdnormalization.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Immutable
@Table(name = "job_description_versions")
public class JobDescriptionVersion {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "job_description_id", nullable = false, updatable = false)
    private UUID jobDescriptionId;

    @Column(name = "version_number", nullable = false, updatable = false)
    private int versionNumber;

    @Column(name = "title", length = 200, updatable = false)
    private String title;

    @Column(name = "company", length = 200, updatable = false)
    private String company;

    @Column(name = "location", length = 200, updatable = false)
    private String location;

    @Column(name = "normalized_text", nullable = false, updatable = false)
    private String normalizedText;

    @Column(name = "content_hash", nullable = false, updatable = false)
    private byte[] contentHash;

    @Column(name = "deduplication_fingerprint", nullable = false, updatable = false)
    private byte[] deduplicationFingerprint;

    @Column(
            name = "normalization_policy_version",
            nullable = false,
            length = 64,
            updatable = false)
    private String normalizationPolicyVersion;

    @Column(
            name = "skill_dictionary_version",
            nullable = false,
            length = 64,
            updatable = false)
    private String skillDictionaryVersion;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "required_skills", nullable = false, columnDefinition = "jsonb", updatable = false)
    private List<SkillSnapshot> requiredSkills;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preferred_skills", nullable = false, columnDefinition = "jsonb", updatable = false)
    private List<SkillSnapshot> preferredSkills;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "mentioned_skills", nullable = false, columnDefinition = "jsonb", updatable = false)
    private List<SkillSnapshot> mentionedSkills;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected JobDescriptionVersion() {
    }

    public UUID getId() {
        return id;
    }

    public UUID getJobDescriptionId() {
        return jobDescriptionId;
    }

    public int getVersionNumber() {
        return versionNumber;
    }

    public String getTitle() {
        return title;
    }

    public String getCompany() {
        return company;
    }

    public String getLocation() {
        return location;
    }

    public String getNormalizedText() {
        return normalizedText;
    }

    public byte[] getContentHash() {
        return contentHash.clone();
    }

    public byte[] getDeduplicationFingerprint() {
        return deduplicationFingerprint.clone();
    }

    public String getNormalizationPolicyVersion() {
        return normalizationPolicyVersion;
    }

    public String getSkillDictionaryVersion() {
        return skillDictionaryVersion;
    }

    public List<SkillSnapshot> getRequiredSkills() {
        return List.copyOf(requiredSkills);
    }

    public List<SkillSnapshot> getPreferredSkills() {
        return List.copyOf(preferredSkills);
    }

    public List<SkillSnapshot> getMentionedSkills() {
        return List.copyOf(mentionedSkills);
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
