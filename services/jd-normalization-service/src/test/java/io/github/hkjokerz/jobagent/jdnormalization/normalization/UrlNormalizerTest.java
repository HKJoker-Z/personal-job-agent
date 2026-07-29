package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class UrlNormalizerTest {

    private final UrlNormalizer normalizer = new UrlNormalizer();

    @Test
    void normalizesHttpsUrlWithoutContactingHost() {
        assertThat(normalizer.normalize(
                        " HTTPS://BÜCHER.Example:443/jobs/../Backend/%7e?q=%2f&x=1#fragment "))
                .isEqualTo(
                        "https://xn--bcher-kva.example/Backend/%7E?q=%2F&x=1");
    }

    @Test
    void suppliesRootPathPreservesPathCaseQueryOrderAndNondefaultPort() {
        assertThat(normalizer.normalize("https://EXAMPLE.test:8443?b=2&a=1"))
                .isEqualTo("https://example.test:8443/?b=2&a=1");
    }

    @Test
    void removesDotSegmentsAndFragmentButNotTrackingParameters() {
        assertThat(normalizer.normalize(
                        "https://example.test/a/./b/../c?utm_source=x#private"))
                .isEqualTo("https://example.test/a/c?utm_source=x");
    }

    @Test
    void rejectsNonHttpsRelativeUserInfoMalformedAndBlankUrls() {
        assertInvalid("http://example.test/a");
        assertInvalid("/relative");
        assertInvalid("https://user@example.test/a");
        assertInvalid("https://example.test/%zz");
        assertThatThrownBy(() -> normalizer.normalize(" \u0000 "))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> assertThat(
                                ((NormalizationPolicy.Violation) exception).rule())
                        .isEqualTo("non_blank"));
    }

    @Test
    void enforcesNormalizedAsciiLength() {
        String overLimit = "https://example.test/" + "a".repeat(2_100);

        assertThatThrownBy(() -> normalizer.normalize(overLimit))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> assertThat(
                                ((NormalizationPolicy.Violation) exception).rule())
                        .isEqualTo("max_ascii_characters"));
    }

    private void assertInvalid(String value) {
        assertThatThrownBy(() -> normalizer.normalize(value))
                .isInstanceOf(NormalizationPolicy.Violation.class)
                .satisfies(exception -> {
                    NormalizationPolicy.Violation violation =
                            (NormalizationPolicy.Violation) exception;
                    assertThat(violation.field()).isEqualTo("metadata.canonical_url");
                    assertThat(violation.rule()).isEqualTo("absolute_https_url");
                });
    }
}
