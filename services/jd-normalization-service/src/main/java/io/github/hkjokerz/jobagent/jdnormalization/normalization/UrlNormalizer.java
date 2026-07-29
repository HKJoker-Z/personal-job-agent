package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;
import java.text.Normalizer;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class UrlNormalizer {

    public String normalize(String suppliedUrl) {
        if (suppliedUrl == null) {
            return null;
        }

        String candidate = Normalizer.normalize(
                        suppliedUrl.replace("\u0000", ""),
                        Normalizer.Form.NFC)
                .strip();
        if (candidate.isEmpty()) {
            throw invalidUrl("non_blank");
        }
        if (candidate.codePoints().anyMatch(TextNormalizer::isUnicodeWhitespace)) {
            throw invalidUrl("absolute_https_url");
        }

        try {
            URI input = new URI(candidate);
            if (!"https".equalsIgnoreCase(input.getScheme())
                    || input.isOpaque()
                    || input.getRawAuthority() == null
                    || input.getRawAuthority().isBlank()
                    || input.getRawUserInfo() != null) {
                throw invalidUrl("absolute_https_url");
            }

            Authority authority = parseAuthority(input);
            String asciiHost = IDN.toASCII(
                            authority.host(),
                            IDN.USE_STD3_ASCII_RULES)
                    .toLowerCase(Locale.ROOT);
            if (asciiHost.isBlank()) {
                throw invalidUrl("absolute_https_url");
            }
            int port = authority.port() == 443 ? -1 : authority.port();
            String path = input.getRawPath();
            if (path == null || path.isEmpty()) {
                path = "/";
            }

            StringBuilder rebuiltValue = new StringBuilder("https://")
                    .append(asciiHost);
            if (port != -1) {
                rebuiltValue.append(':').append(port);
            }
            rebuiltValue.append(path);
            if (input.getRawQuery() != null) {
                rebuiltValue.append('?').append(input.getRawQuery());
            }
            URI rebuilt = new URI(rebuiltValue.toString()).normalize();
            String normalized = uppercasePercentEncoding(rebuilt.toASCIIString());
            if (normalized.length() > NormalizationPolicy.MAX_CANONICAL_URL_ASCII_LENGTH) {
                throw new NormalizationPolicy.Violation(
                        "VALIDATION_FAILED",
                        "metadata.canonical_url",
                        "max_ascii_characters",
                        Map.of("maximum", NormalizationPolicy.MAX_CANONICAL_URL_ASCII_LENGTH));
            }
            return normalized;
        } catch (IllegalArgumentException | URISyntaxException exception) {
            if (exception instanceof NormalizationPolicy.Violation violation) {
                throw violation;
            }
            throw invalidUrl("absolute_https_url");
        }
    }

    private static Authority parseAuthority(URI input) {
        if (input.getHost() != null) {
            return new Authority(input.getHost(), input.getPort());
        }

        String authority = input.getRawAuthority();
        if (authority.startsWith("[") || authority.contains("@")) {
            throw invalidUrl("absolute_https_url");
        }
        int port = -1;
        String host = authority;
        int colon = authority.lastIndexOf(':');
        if (colon >= 0) {
            host = authority.substring(0, colon);
            String portText = authority.substring(colon + 1);
            if (portText.isEmpty() || !portText.chars().allMatch(Character::isDigit)) {
                throw invalidUrl("absolute_https_url");
            }
            try {
                port = Integer.parseInt(portText);
            } catch (NumberFormatException exception) {
                throw invalidUrl("absolute_https_url");
            }
            if (port < 1 || port > 65_535) {
                throw invalidUrl("absolute_https_url");
            }
        }
        return new Authority(host, port);
    }

    private static String uppercasePercentEncoding(String value) {
        StringBuilder output = new StringBuilder(value.length());
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            output.append(current);
            if (current == '%' && index + 2 < value.length()) {
                output.append(Character.toUpperCase(value.charAt(++index)));
                output.append(Character.toUpperCase(value.charAt(++index)));
            }
        }
        return output.toString();
    }

    private static NormalizationPolicy.Violation invalidUrl(String rule) {
        return new NormalizationPolicy.Violation(
                "VALIDATION_FAILED",
                "metadata.canonical_url",
                rule,
                Map.of());
    }

    private record Authority(String host, int port) {
    }
}
