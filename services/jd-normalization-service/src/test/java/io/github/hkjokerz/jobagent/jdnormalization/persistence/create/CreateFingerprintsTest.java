package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.SkillDictionary;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import org.junit.jupiter.api.Test;

class CreateFingerprintsTest {

    private final CreateFingerprints fingerprints =
            new CreateFingerprints(new ObjectMapper());

    @Test
    void hashesTheRawKeyWithTheRequiredDomainAndNeverConfusesFingerprintDomains()
            throws Exception {
        String key = "550e8400-e29b-41d4-a716-446655440000";
        byte[] expected = MessageDigest.getInstance("SHA-256").digest(
                ("jd-normalization:idempotency-key:v1\0" + key)
                        .getBytes(StandardCharsets.UTF_8));

        assertThat(fingerprints.idempotencyKeyHash(key)).isEqualTo(expected);

        CreateFingerprints.Fingerprints computed = fingerprints.forCreate(result(
                "Backend Engineer",
                "Example",
                "Hong Kong",
                "https://jobs.example.test/backend"));
        assertThat(computed.deduplicationFingerprint()).hasSize(32);
        assertThat(computed.requestFingerprint()).hasSize(32);
        assertThat(computed.deduplicationFingerprint())
                .isNotEqualTo(computed.requestFingerprint());
        assertThat(HexFormat.of().formatHex(expected)).doesNotContain(key);
    }

    @Test
    void canonicalFingerprintsAreDeterministicAndMetadataSensitive() {
        NormalizationResult first = result(
                "Backend Engineer",
                "Example",
                null,
                null);
        NormalizationResult metadataChanged = result(
                "Platform Engineer",
                "Example",
                null,
                null);

        CreateFingerprints.Fingerprints one = fingerprints.forCreate(first);
        CreateFingerprints.Fingerprints repeated = fingerprints.forCreate(first);
        CreateFingerprints.Fingerprints changed =
                fingerprints.forCreate(metadataChanged);

        assertThat(one.deduplicationFingerprint())
                .isEqualTo(repeated.deduplicationFingerprint())
                .isNotEqualTo(changed.deduplicationFingerprint());
        assertThat(one.requestFingerprint())
                .isEqualTo(repeated.requestFingerprint())
                .isNotEqualTo(changed.requestFingerprint());
        assertThat(first.contentHash()).isEqualTo(metadataChanged.contentHash());
    }

    private static NormalizationResult result(
            String title,
            String company,
            String location,
            String canonicalUrl) {
        return new NormalizationResult(
                "Required:\n- Java",
                "11".repeat(32),
                "jd-normalization-v1",
                "skills-v1",
                List.of(new SkillDictionary.Skill("java", "Java")),
                List.of(),
                List.of(new SkillDictionary.Skill("postgresql", "PostgreSQL")),
                new NormalizationResult.Metadata(
                        title,
                        company,
                        location,
                        canonicalUrl));
    }
}
