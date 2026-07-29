package io.github.hkjokerz.jobagent.jdnormalization.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateApiException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class StrongEtagTest {

    @Test
    void acceptsCanonicalStrongNonnegativeLongValues() {
        assertThat(parse("\"0\"")).isZero();
        assertThat(parse("\"1\"")).isEqualTo(1);
        assertThat(parse("\"42\"")).isEqualTo(42);
        assertThat(parse("\"9223372036854775807\"")).isEqualTo(Long.MAX_VALUE);
    }

    @Test
    void distinguishesMissingFromEveryMalformedEncoding() {
        MockHttpServletRequest missing = new MockHttpServletRequest();
        assertCode(missing, "PRECONDITION_REQUIRED");

        List.of(
                        "W/\"1\"",
                        "*",
                        "1",
                        "\"-1\"",
                        "\"one\"",
                        "\"01\"",
                        "\"9223372036854775808\"",
                        "\"123456789012345678901\"",
                        "\"0\", \"1\"")
                .forEach(value -> {
                    MockHttpServletRequest request = new MockHttpServletRequest();
                    request.addHeader("If-Match", value);
                    assertCode(request, "INVALID_IF_MATCH");
                });

        MockHttpServletRequest multiple = new MockHttpServletRequest();
        multiple.addHeader("If-Match", "\"0\"");
        multiple.addHeader("If-Match", "\"1\"");
        assertCode(multiple, "INVALID_IF_MATCH");
    }

    private static long parse(String value) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("If-Match", value);
        return StrongEtag.requiredIfMatch(request);
    }

    private static void assertCode(
            MockHttpServletRequest request,
            String expectedCode) {
        assertThatThrownBy(() -> StrongEtag.requiredIfMatch(request))
                .isInstanceOfSatisfying(
                        UpdateApiException.class,
                        exception -> assertThat(exception.code())
                                .isEqualTo(expectedCode));
    }
}
