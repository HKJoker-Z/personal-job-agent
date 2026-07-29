package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class TextNormalizer {

    public String normalizeJobDescription(String rawText) {
        requireWithinCodePointLimit(
                rawText,
                "raw_text",
                NormalizationPolicy.MAX_RAW_TEXT_CODE_POINTS);

        String nfc = Normalizer.normalize(removeNul(rawText), Normalizer.Form.NFC);
        String withLf = normalizeLineEndings(nfc);
        String[] sourceLines = withLf.split("\n", -1);
        List<String> outputLines = new ArrayList<>(sourceLines.length);
        boolean pendingBlank = false;

        for (String sourceLine : sourceLines) {
            String line = collapseHorizontalWhitespace(sourceLine);
            if (line.isEmpty()) {
                if (!outputLines.isEmpty()) {
                    pendingBlank = true;
                }
                continue;
            }
            if (pendingBlank) {
                outputLines.add("");
                pendingBlank = false;
            }
            outputLines.add(line);
        }

        String normalized = String.join("\n", outputLines);
        if (normalized.codePoints().noneMatch(codePoint -> !isUnicodeWhitespace(codePoint))) {
            throw new NormalizationPolicy.Violation(
                    "EMPTY_JOB_DESCRIPTION",
                    "raw_text",
                    "non_whitespace_required",
                    Map.of());
        }
        return normalized;
    }

    public String normalizeMetadata(String value, String field) {
        if (value == null) {
            return null;
        }
        requireWithinCodePointLimit(
                value,
                field,
                NormalizationPolicy.MAX_METADATA_CODE_POINTS);
        String normalized = collapseWhitespace(
                Normalizer.normalize(removeNul(value), Normalizer.Form.NFC));
        if (normalized.isEmpty()) {
            throw new NormalizationPolicy.Violation(
                    "VALIDATION_FAILED",
                    field,
                    "non_blank",
                    Map.of());
        }
        requireWithinCodePointLimit(
                normalized,
                field,
                NormalizationPolicy.MAX_METADATA_CODE_POINTS);
        return normalized;
    }

    private static void requireWithinCodePointLimit(String value, String field, int maximum) {
        if (value == null) {
            return;
        }
        int codePoints = value.codePointCount(0, value.length());
        if (codePoints > maximum) {
            throw new NormalizationPolicy.Violation(
                    "VALIDATION_FAILED",
                    field,
                    "max_code_points",
                    Map.of("maximum", maximum));
        }
    }

    private static String removeNul(String value) {
        return value.replace("\u0000", "");
    }

    private static String normalizeLineEndings(String value) {
        StringBuilder output = new StringBuilder(value.length());
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            offset += Character.charCount(codePoint);
            if (codePoint == '\r') {
                if (offset < value.length() && value.codePointAt(offset) == '\n') {
                    offset++;
                }
                output.append('\n');
            } else if (codePoint == 0x0085 || codePoint == 0x2028 || codePoint == 0x2029) {
                output.append('\n');
            } else {
                output.appendCodePoint(codePoint);
            }
        }
        return output.toString();
    }

    static String collapseWhitespace(String value) {
        return collapseMatchingWhitespace(value, false);
    }

    private static String collapseHorizontalWhitespace(String value) {
        return collapseMatchingWhitespace(value, true);
    }

    private static String collapseMatchingWhitespace(String value, boolean horizontalOnly) {
        StringBuilder output = new StringBuilder(value.length());
        boolean pendingSpace = false;
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            offset += Character.charCount(codePoint);
            boolean matchingWhitespace = horizontalOnly
                    ? isHorizontalWhitespace(codePoint)
                    : isUnicodeWhitespace(codePoint);
            if (matchingWhitespace) {
                if (!output.isEmpty()) {
                    pendingSpace = true;
                }
            } else {
                if (pendingSpace) {
                    output.append(' ');
                    pendingSpace = false;
                }
                output.appendCodePoint(codePoint);
            }
        }
        return output.toString();
    }

    private static boolean isHorizontalWhitespace(int codePoint) {
        return codePoint == '\t' || Character.isSpaceChar(codePoint);
    }

    static boolean isUnicodeWhitespace(int codePoint) {
        return Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint);
    }
}
