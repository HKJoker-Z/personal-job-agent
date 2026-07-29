package io.github.hkjokerz.jobagent.jdnormalization.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "job_descriptions")
public class JobDescription {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "canonical_url", length = 2048)
    private String canonicalUrl;

    @Column(name = "current_version_id", nullable = false)
    private UUID currentVersionId;

    @Column(name = "current_deduplication_fingerprint", nullable = false)
    private byte[] currentDeduplicationFingerprint;

    @Version
    @Column(name = "optimistic_lock_version", nullable = false)
    private long optimisticLockVersion;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected JobDescription() {
    }

    public UUID getId() {
        return id;
    }

    public String getCanonicalUrl() {
        return canonicalUrl;
    }

    public UUID getCurrentVersionId() {
        return currentVersionId;
    }

    public byte[] getCurrentDeduplicationFingerprint() {
        return currentDeduplicationFingerprint.clone();
    }

    public long getOptimisticLockVersion() {
        return optimisticLockVersion;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
