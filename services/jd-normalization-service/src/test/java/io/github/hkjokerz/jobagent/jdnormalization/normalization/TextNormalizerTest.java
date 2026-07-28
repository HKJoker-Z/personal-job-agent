package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class TextNormalizerTest {

    private final TextNormalizer normalizer = new TextNormalizer();

    @Test
    void appliesEveryLineAndWhitespaceRuleInPolicyOrder() {
        String raw = "\n\u0000Cafe\u0301  \r\n"
                + "Required:\r"
                + "-\tJava\u00a0\u200321\u0085"
                + "\u2028"
                + "- Spring Boot\u2029\n\n\n";

        assertThat(normalizer.normalizeJobDescription(raw))
                .isEqualTo("Café\nRequired:\n- Java 21\n\n- Spring Boot");
    }

    @Test
    void convertsEverySupportedLineSeparatorToLf() {
        assertThat(normalizer.normalizeJobDescription("a\r\nb\rc\u0085d\u2028e\u2029f"))
                .isEqualTo("a\nb\nc\nd\ne\nf");
    }

    @Test
    void preservesHeadingPunctuationBulletsAndNonblankLineOrder() {
        String normalized = normalizer.normalizeJobDescription(
                "  Requirements:  \n  -   Java  \n\n\n  •  Spring Boot \n");

        assertThat(normalized).isEqualTo("Requirements:\n- Java\n\n• Spring Boot");
        assertThat(normalized).doesNotEndWith("\n");
    }

    @Test
    void removesNulAndNormalizesUnicodeToNfc() {
        assertThat(normalizer.normalizeJobDescription("\u0000A\u030A"))
                .isEqualTo("Å")
                .isEqualTo(java.text.Normalizer.normalize(
                        "Å",
                        java.text.Normalizer.Form.NFC));
    }

    @Test
    void acceptsExactlyOneHundredThousandUnicodeCodePoints() {
        String boundary = "😀".repeat(NormalizationPolicy.MAX_RAW_TEXT_CODE_POINTS);

        assertThat(normalizer.normalizeJobDescription(boundary))
                .hasSize(NormalizationPolicy.MAX_RAW_TEXT_CODE_POINTS * 2)
                .hasSameSizeAs(boundary);
    }

    @Test
    void rejectsOneCodePointOverTheLimit() {
        String overLimit = "😀".repeat(
                NormalizationPolicy.MAX_RAW_TEXT_CODE_POINTS + 1);

        assertThatThrownBy(() -> normalizer.normalizeJobDescription(overLimit))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> {
                    NormalizationPolicy.Violation violation =
                            (NormalizationPolicy.Violation) exception;
                    assertThat(violation.field()).isEqualTo("raw_text");
                    assertThat(violation.rule()).isEqualTo("max_code_points");
                });
    }

    @Test
    void rejectsTextThatIsEmptyAfterNormalization() {
        assertThatThrownBy(() ->
                normalizer.normalizeJobDescription("\u0000 \t\r\n\u00a0"))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> assertThat(
                                ((NormalizationPolicy.Violation) exception).errorCode())
                        .isEqualTo("EMPTY_JOB_DESCRIPTION"));
    }

    @Test
    void normalizesMetadataWithoutInferringItFromText() {
        assertThat(normalizer.normalizeMetadata(
                        "  Example\u0000\u00a0  Limited  ",
                        "metadata.company"))
                .isEqualTo("Example Limited");
        assertThat(normalizer.normalizeMetadata(null, "metadata.company")).isNull();
    }

    @Test
    void rejectsExplicitlyBlankOrOverlongMetadata() {
        assertThatThrownBy(() ->
                normalizer.normalizeMetadata(" \u0000\t", "metadata.title"))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> assertThat(
                                ((NormalizationPolicy.Violation) exception).rule())
                        .isEqualTo("non_blank"));

        assertThatThrownBy(() ->
                normalizer.normalizeMetadata(
                        "😀".repeat(NormalizationPolicy.MAX_METADATA_CODE_POINTS + 1),
                        "metadata.title"))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> assertThat(
                                ((NormalizationPolicy.Violation) exception).rule())
                        .isEqualTo("max_code_points"));
    }
}
