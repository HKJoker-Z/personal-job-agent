package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class JobDescriptionNormalizer {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(JobDescriptionNormalizer.class);

    private final TextNormalizer textNormalizer;
    private final UrlNormalizer urlNormalizer;
    private final SkillExtractor skillExtractor;

    public JobDescriptionNormalizer(
            TextNormalizer textNormalizer,
            UrlNormalizer urlNormalizer,
            SkillExtractor skillExtractor) {
        this.textNormalizer = textNormalizer;
        this.urlNormalizer = urlNormalizer;
        this.skillExtractor = skillExtractor;
    }

    public NormalizationResult normalize(NormalizeJobDescriptionRequest request) {
        long started = System.nanoTime();
        String normalizedText = textNormalizer.normalizeJobDescription(request.rawText());
        NormalizeJobDescriptionRequest.Metadata suppliedMetadata = request.metadata();
        NormalizationResult.Metadata metadata = new NormalizationResult.Metadata(
                textNormalizer.normalizeMetadata(
                        suppliedMetadata == null ? null : suppliedMetadata.title(),
                        "metadata.title"),
                textNormalizer.normalizeMetadata(
                        suppliedMetadata == null ? null : suppliedMetadata.company(),
                        "metadata.company"),
                textNormalizer.normalizeMetadata(
                        suppliedMetadata == null ? null : suppliedMetadata.location(),
                        "metadata.location"),
                urlNormalizer.normalize(
                        suppliedMetadata == null ? null : suppliedMetadata.canonicalUrl()));
        SkillExtractor.SkillMatches matches = skillExtractor.extract(normalizedText);
        String contentHash = sha256(normalizedText);
        long durationMillis = (System.nanoTime() - started) / 1_000_000;

        LOGGER.atInfo()
                .addKeyValue("normalization_policy", NormalizationPolicy.VERSION)
                .addKeyValue("skill_dictionary", skillExtractor.dictionaryVersion())
                .addKeyValue("required_count", matches.required().size())
                .addKeyValue("preferred_count", matches.preferred().size())
                .addKeyValue("mentioned_count", matches.mentioned().size())
                .addKeyValue(
                        "normalized_code_points",
                        normalizedText.codePointCount(0, normalizedText.length()))
                .addKeyValue("normalization_duration_ms", durationMillis)
                .log("jd_normalization_completed");

        return new NormalizationResult(
                normalizedText,
                contentHash,
                NormalizationPolicy.VERSION,
                skillExtractor.dictionaryVersion(),
                matches.required(),
                matches.preferred(),
                matches.mentioned(),
                metadata);
    }

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable");
        }
    }
}
