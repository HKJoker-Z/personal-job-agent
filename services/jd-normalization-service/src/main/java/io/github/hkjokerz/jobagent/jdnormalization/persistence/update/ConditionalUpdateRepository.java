package io.github.hkjokerz.jobagent.jdnormalization.persistence.update;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.NormalizedCreate;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Repository
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ConditionalUpdateRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final JavaType skillListType;
    private final TransactionTemplate transactions;

    public ConditionalUpdateRepository(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper,
            PlatformTransactionManager transactionManager) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
        this.skillListType = objectMapper.getTypeFactory()
                .constructCollectionType(List.class, SkillSnapshot.class);
        this.transactions = new TransactionTemplate(transactionManager);
        this.transactions.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
    }

    public UpdateResult update(
            UUID aggregateId,
            long expectedVersion,
            NormalizedCreate replacement,
            Instant now) {
        return transactions.execute(status ->
                updateInTransaction(aggregateId, expectedVersion, replacement, now));
    }

    public Optional<Duplicate> findDuplicate(
            UUID aggregateId,
            NormalizedCreate replacement) {
        return transactions.execute(status ->
                duplicate(aggregateId, replacement));
    }

    private UpdateResult updateInTransaction(
            UUID aggregateId,
            long expectedVersion,
            NormalizedCreate replacement,
            Instant now) {
        CurrentRow current = lockedCurrent(aggregateId)
                .orElseThrow(UpdateApiException::notFound);
        if (current.optimisticLockVersion() != expectedVersion) {
            throw UpdateApiException.preconditionFailed();
        }
        if (sameState(current, replacement)) {
            return new UpdateResult(current.toCurrent(), false);
        }

        Optional<Duplicate> duplicate = duplicate(aggregateId, replacement);
        if (duplicate.isPresent()) {
            Duplicate conflict = duplicate.orElseThrow();
            throw UpdateApiException.alreadyExists(
                    conflict.category(),
                    conflict.jobDescriptionId());
        }
        if (current.versionNumber() == Integer.MAX_VALUE
                || current.optimisticLockVersion() == Long.MAX_VALUE) {
            throw new IllegalStateException("Job Description version capacity is exhausted");
        }

        UUID versionId = UUID.randomUUID();
        int nextVersionNumber = current.versionNumber() + 1;
        Instant updateTime = monotonicTime(now, current.updatedAt());
        int rootUpdated = jdbcTemplate.update("""
                UPDATE job_descriptions
                SET canonical_url = ?,
                    current_version_id = ?,
                    current_deduplication_fingerprint = ?,
                    optimistic_lock_version = optimistic_lock_version + 1,
                    updated_at = ?
                WHERE id = ?
                  AND optimistic_lock_version = ?
                """,
                replacement.canonicalUrl(),
                versionId,
                replacement.deduplicationFingerprint(),
                utc(updateTime),
                aggregateId,
                expectedVersion);
        if (rootUpdated != 1) {
            throw UpdateApiException.preconditionFailed();
        }

        jdbcTemplate.update("""
                INSERT INTO job_description_versions (
                    id,
                    job_description_id,
                    version_number,
                    title,
                    company,
                    location,
                    normalized_text,
                    content_hash,
                    deduplication_fingerprint,
                    normalization_policy_version,
                    skill_dictionary_version,
                    required_skills,
                    preferred_skills,
                    mentioned_skills,
                    created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CAST(? AS jsonb), CAST(? AS jsonb), CAST(? AS jsonb), ?
                )
                """,
                versionId,
                aggregateId,
                nextVersionNumber,
                replacement.title(),
                replacement.company(),
                replacement.location(),
                replacement.normalizedText(),
                replacement.contentHash(),
                replacement.deduplicationFingerprint(),
                replacement.normalizationPolicyVersion(),
                replacement.skillDictionaryVersion(),
                replacement.requiredSkillsJson(objectMapper),
                replacement.preferredSkillsJson(objectMapper),
                replacement.mentionedSkillsJson(objectMapper),
                utc(updateTime));

        CurrentRow updated = lockedCurrent(aggregateId)
                .orElseThrow(() -> new IllegalStateException(
                        "Updated Job Description disappeared"));
        if (updated.optimisticLockVersion() != expectedVersion + 1
                || updated.versionNumber() != nextVersionNumber
                || !updated.versionId().equals(versionId)) {
            throw new IllegalStateException(
                    "Updated Job Description current identity is inconsistent");
        }
        return new UpdateResult(updated.toCurrent(), true);
    }

    private Optional<CurrentRow> lockedCurrent(UUID aggregateId) {
        List<RootRow> roots = jdbcTemplate.query("""
                SELECT
                    j.id,
                    j.canonical_url,
                    j.optimistic_lock_version,
                    j.created_at,
                    j.updated_at,
                    j.current_version_id,
                    j.current_deduplication_fingerprint
                FROM job_descriptions j
                WHERE j.id = ?
                FOR UPDATE
                """,
                (resultSet, rowNumber) -> new RootRow(
                        resultSet.getObject("id", UUID.class),
                        resultSet.getString("canonical_url"),
                        resultSet.getLong("optimistic_lock_version"),
                        instant(resultSet, "created_at"),
                        instant(resultSet, "updated_at"),
                        resultSet.getObject("current_version_id", UUID.class),
                        resultSet.getBytes("current_deduplication_fingerprint")),
                aggregateId);
        if (roots.size() > 1) {
            throw new IllegalStateException("Job Description root identity is not unique");
        }
        if (roots.isEmpty()) {
            return Optional.empty();
        }
        RootRow root = roots.getFirst();
        List<VersionRow> versions = jdbcTemplate.query("""
                SELECT
                    v.id AS version_id,
                    v.version_number,
                    v.normalized_text,
                    v.content_hash,
                    v.deduplication_fingerprint,
                    v.normalization_policy_version,
                    v.skill_dictionary_version,
                    v.required_skills::text AS required_skills,
                    v.preferred_skills::text AS preferred_skills,
                    v.mentioned_skills::text AS mentioned_skills,
                    v.title,
                    v.company,
                    v.location
                FROM job_description_versions v
                WHERE v.id = ?
                  AND v.job_description_id = ?
                  AND v.deduplication_fingerprint = ?
                """,
                (resultSet, rowNumber) -> new VersionRow(
                        resultSet.getObject("version_id", UUID.class),
                        resultSet.getInt("version_number"),
                        resultSet.getString("normalized_text"),
                        resultSet.getBytes("content_hash"),
                        resultSet.getBytes("deduplication_fingerprint"),
                        resultSet.getString("normalization_policy_version"),
                        resultSet.getString("skill_dictionary_version"),
                        skills(resultSet.getString("required_skills")),
                        skills(resultSet.getString("preferred_skills")),
                        skills(resultSet.getString("mentioned_skills")),
                        resultSet.getString("title"),
                        resultSet.getString("company"),
                        resultSet.getString("location")),
                root.currentVersionId(),
                root.id(),
                root.currentDeduplicationFingerprint());
        if (versions.size() != 1) {
            throw new IllegalStateException(
                    "Job Description current version identity is inconsistent");
        }
        VersionRow version = versions.getFirst();
        return Optional.of(new CurrentRow(
                root.id(),
                root.canonicalUrl(),
                root.optimisticLockVersion(),
                root.createdAt(),
                root.updatedAt(),
                version.versionId(),
                version.versionNumber(),
                version.normalizedText(),
                version.contentHash(),
                version.deduplicationFingerprint(),
                version.normalizationPolicyVersion(),
                version.skillDictionaryVersion(),
                version.requiredSkills(),
                version.preferredSkills(),
                version.mentionedSkills(),
                version.title(),
                version.company(),
                version.location()));
    }

    private Optional<Duplicate> duplicate(
            UUID aggregateId,
            NormalizedCreate replacement) {
        if (replacement.canonicalUrl() != null) {
            List<UUID> canonicalMatches = jdbcTemplate.queryForList("""
                    SELECT id
                    FROM job_descriptions
                    WHERE id <> ?
                      AND canonical_url = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    UUID.class,
                    aggregateId,
                    replacement.canonicalUrl());
            if (!canonicalMatches.isEmpty()) {
                return Optional.of(new Duplicate(
                        "canonical_url",
                        canonicalMatches.getFirst()));
            }
        }
        List<UUID> fingerprintMatches = jdbcTemplate.queryForList("""
                SELECT id
                FROM job_descriptions
                WHERE id <> ?
                  AND current_deduplication_fingerprint = ?
                ORDER BY id
                LIMIT 1
                """,
                UUID.class,
                aggregateId,
                replacement.deduplicationFingerprint());
        if (!fingerprintMatches.isEmpty()) {
            return Optional.of(new Duplicate(
                    "deduplication_fingerprint",
                    fingerprintMatches.getFirst()));
        }
        return Optional.empty();
    }

    private static boolean sameState(
            CurrentRow current,
            NormalizedCreate replacement) {
        return Objects.equals(current.canonicalUrl(), replacement.canonicalUrl())
                && Objects.equals(current.normalizedText(), replacement.normalizedText())
                && Arrays.equals(current.contentHash(), replacement.contentHash())
                && Arrays.equals(
                        current.deduplicationFingerprint(),
                        replacement.deduplicationFingerprint())
                && Objects.equals(
                        current.normalizationPolicyVersion(),
                        replacement.normalizationPolicyVersion())
                && Objects.equals(
                        current.skillDictionaryVersion(),
                        replacement.skillDictionaryVersion())
                && current.requiredSkills().equals(replacement.requiredSkills())
                && current.preferredSkills().equals(replacement.preferredSkills())
                && current.mentionedSkills().equals(replacement.mentionedSkills())
                && Objects.equals(current.title(), replacement.title())
                && Objects.equals(current.company(), replacement.company())
                && Objects.equals(current.location(), replacement.location());
    }

    private List<SkillSnapshot> skills(String json) {
        try {
            return objectMapper.readValue(json, skillListType);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Stored Job Description skills are invalid");
        }
    }

    private static Instant instant(
            java.sql.ResultSet resultSet,
            String column) throws java.sql.SQLException {
        return resultSet.getObject(column, OffsetDateTime.class).toInstant();
    }

    private static Instant monotonicTime(Instant supplied, Instant current) {
        if (supplied.isAfter(current)) {
            return supplied;
        }
        return current.plusNanos(1_000);
    }

    private static OffsetDateTime utc(Instant value) {
        return OffsetDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    public record Duplicate(String category, UUID jobDescriptionId) {
    }

    private record RootRow(
            UUID id,
            String canonicalUrl,
            long optimisticLockVersion,
            Instant createdAt,
            Instant updatedAt,
            UUID currentVersionId,
            byte[] currentDeduplicationFingerprint) {

        private RootRow {
            currentDeduplicationFingerprint =
                    currentDeduplicationFingerprint.clone();
        }
    }

    private record VersionRow(
            UUID versionId,
            int versionNumber,
            String normalizedText,
            byte[] contentHash,
            byte[] deduplicationFingerprint,
            String normalizationPolicyVersion,
            String skillDictionaryVersion,
            List<SkillSnapshot> requiredSkills,
            List<SkillSnapshot> preferredSkills,
            List<SkillSnapshot> mentionedSkills,
            String title,
            String company,
            String location) {

        private VersionRow {
            contentHash = contentHash.clone();
            deduplicationFingerprint = deduplicationFingerprint.clone();
            requiredSkills = List.copyOf(requiredSkills);
            preferredSkills = List.copyOf(preferredSkills);
            mentionedSkills = List.copyOf(mentionedSkills);
        }
    }

    private record CurrentRow(
            UUID id,
            String canonicalUrl,
            long optimisticLockVersion,
            Instant createdAt,
            Instant updatedAt,
            UUID versionId,
            int versionNumber,
            String normalizedText,
            byte[] contentHash,
            byte[] deduplicationFingerprint,
            String normalizationPolicyVersion,
            String skillDictionaryVersion,
            List<SkillSnapshot> requiredSkills,
            List<SkillSnapshot> preferredSkills,
            List<SkillSnapshot> mentionedSkills,
            String title,
            String company,
            String location) {

        private CurrentRow {
            contentHash = contentHash.clone();
            deduplicationFingerprint = deduplicationFingerprint.clone();
            requiredSkills = List.copyOf(requiredSkills);
            preferredSkills = List.copyOf(preferredSkills);
            mentionedSkills = List.copyOf(mentionedSkills);
        }

        ReadModels.Current toCurrent() {
            return new ReadModels.Current(
                    id,
                    canonicalUrl,
                    optimisticLockVersion,
                    versionNumber,
                    normalizedText,
                    contentHash,
                    normalizationPolicyVersion,
                    skillDictionaryVersion,
                    requiredSkills,
                    preferredSkills,
                    mentionedSkills,
                    title,
                    company,
                    location,
                    createdAt,
                    updatedAt);
        }
    }
}
