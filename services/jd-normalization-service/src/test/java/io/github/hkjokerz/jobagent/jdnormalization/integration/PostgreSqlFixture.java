package io.github.hkjokerz.jobagent.jdnormalization.integration;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

final class PostgreSqlFixture {

    private static final String SKILLS = """
            [{"id":"java","name":"Java"}]
            """;

    private final JdbcTemplate jdbcTemplate;
    private final TransactionTemplate transactionTemplate;

    PostgreSqlFixture(
            JdbcTemplate jdbcTemplate,
            TransactionTemplate transactionTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.transactionTemplate = transactionTemplate;
    }

    void insertAggregate(
            UUID aggregateId,
            String canonicalUrl,
            Instant createdAt,
            List<VersionSeed> versions) {
        VersionSeed current = versions.getLast();
        transactionTemplate.executeWithoutResult(status -> {
            jdbcTemplate.update("""
                    INSERT INTO job_descriptions (
                        id,
                        canonical_url,
                        current_version_id,
                        current_deduplication_fingerprint,
                        optimistic_lock_version,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    aggregateId,
                    canonicalUrl,
                    current.id(),
                    current.deduplicationFingerprint(),
                    0L,
                    utc(createdAt),
                    utc(current.createdAt()));
            for (VersionSeed version : versions) {
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
                        version.id(),
                        aggregateId,
                        version.versionNumber(),
                        version.title(),
                        version.company(),
                        version.location(),
                        version.normalizedText(),
                        version.contentHash(),
                        version.deduplicationFingerprint(),
                        "jd-normalization-v1",
                        "skills-v1",
                        SKILLS,
                        "[]",
                        "[]",
                        utc(version.createdAt()));
            }
        });
    }

    static VersionSeed version(
            UUID id,
            int number,
            String title,
            String company,
            String location,
            String normalizedText,
            String contentHashLabel,
            String fingerprintLabel,
            Instant createdAt) {
        return new VersionSeed(
                id,
                number,
                title,
                company,
                location,
                normalizedText,
                digest(contentHashLabel),
                digest(fingerprintLabel),
                createdAt);
    }

    static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    static byte[] repeatedByte(int value) {
        byte[] bytes = new byte[32];
        Arrays.fill(bytes, (byte) value);
        return bytes;
    }

    private static OffsetDateTime utc(Instant value) {
        return OffsetDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    record VersionSeed(
            UUID id,
            int versionNumber,
            String title,
            String company,
            String location,
            String normalizedText,
            byte[] contentHash,
            byte[] deduplicationFingerprint,
            Instant createdAt) {

        VersionSeed {
            contentHash = contentHash.clone();
            deduplicationFingerprint = deduplicationFingerprint.clone();
        }
    }
}
