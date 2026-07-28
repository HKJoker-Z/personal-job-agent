package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class JobDescriptionNormalizerTest {

    private JobDescriptionNormalizer normalizer;

    @BeforeEach
    void setUp() {
        SkillDictionary dictionary = new SkillDictionaryLoader(new ObjectMapper()).load(
                new ClassPathResource("skills/skills-v1.json"),
                NormalizationPolicy.MAX_UNIQUE_SKILLS);
        normalizer = new JobDescriptionNormalizer(
                new TextNormalizer(),
                new UrlNormalizer(),
                new SkillExtractor(dictionary));
    }

    @Test
    void returnsKnownSha256VectorPolicyAndDictionaryVersions() {
        NormalizationResult result = normalizer.normalize(
                new NormalizeJobDescriptionRequest("abc", null));

        assertThat(result.normalizedText()).isEqualTo("abc");
        assertThat(result.contentHash())
                .isEqualTo("ba7816bf8f01cfea414140de5dae2223"
                        + "b00361a396177a9cb410ff61f20015ad")
                .matches("[0-9a-f]{64}");
        assertThat(result.normalizationPolicyVersion())
                .isEqualTo("jd-normalization-v1");
        assertThat(result.skillDictionaryVersion()).isEqualTo("skills-v1");
    }

    @Test
    void repeatedInputProducesByteIdenticalDeterministicResult() {
        NormalizeJobDescriptionRequest request = new NormalizeJobDescriptionRequest(
                "Required:\r\n- Java 21\r\nPreferred:\r\n- Docker",
                new NormalizeJobDescriptionRequest.Metadata(
                        " Backend\u00a0Engineer ",
                        " Example Ltd ",
                        " Hong Kong ",
                        "HTTPS://JOBS.EXAMPLE.TEST:443/a/../backend#apply"));

        NormalizationResult first = normalizer.normalize(request);
        for (int iteration = 0; iteration < 10; iteration++) {
            assertThat(normalizer.normalize(request)).isEqualTo(first);
        }
    }

    @Test
    void normalizesOnlyExplicitMetadata() {
        NormalizationResult withMetadata = normalizer.normalize(
                new NormalizeJobDescriptionRequest(
                        "Title in source must not be inferred",
                        new NormalizeJobDescriptionRequest.Metadata(
                                "  Senior\u00a0Backend  Engineer ",
                                " Example\u0000 Ltd ",
                                " Hong\u2003Kong ",
                                "https://EXAMPLE.test")));

        assertThat(withMetadata.metadata())
                .isEqualTo(new NormalizationResult.Metadata(
                        "Senior Backend Engineer",
                        "Example Ltd",
                        "Hong Kong",
                        "https://example.test/"));

        NormalizationResult withoutMetadata = normalizer.normalize(
                new NormalizeJobDescriptionRequest(
                        "Senior Backend Engineer at Example Ltd",
                        null));
        assertThat(withoutMetadata.metadata())
                .isEqualTo(new NormalizationResult.Metadata(null, null, null, null));
    }
}
