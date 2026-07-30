package io.github.hkjokerz.jobagent.jdnormalization.persistence.read;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationPolicy;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.TextNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.UrlNormalizer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class CursorCodec {

    public static final int LIST_CURSOR_MAX_LENGTH = 1024;
    public static final int VERSION_CURSOR_MAX_LENGTH = 512;
    private static final int CURSOR_VERSION = 1;
    private static final Pattern CONTENT_HASH = Pattern.compile("[0-9a-f]{64}");

    private final ObjectMapper objectMapper;
    private final TextNormalizer textNormalizer;
    private final UrlNormalizer urlNormalizer;

    public CursorCodec(
            ObjectMapper objectMapper,
            TextNormalizer textNormalizer,
            UrlNormalizer urlNormalizer) {
        this.objectMapper = objectMapper;
        this.textNormalizer = textNormalizer;
        this.urlNormalizer = urlNormalizer;
    }

    public NormalizedFilters normalizeFilters(
            String title,
            String company,
            String location,
            String contentHash,
            String canonicalUrl) {
        try {
            String normalizedTitle = normalizeTextFilter(title, "title");
            String normalizedCompany = normalizeTextFilter(company, "company");
            String normalizedLocation = normalizeTextFilter(location, "location");
            String normalizedUrl = urlNormalizer.normalize(canonicalUrl);
            byte[] hashBytes = decodeContentHash(contentHash);
            String fingerprint = filterFingerprint(
                    normalizedTitle,
                    normalizedCompany,
                    normalizedLocation,
                    contentHash,
                    normalizedUrl);
            return new NormalizedFilters(
                    normalizedTitle,
                    normalizedCompany,
                    normalizedLocation,
                    hashBytes,
                    contentHash,
                    normalizedUrl,
                    fingerprint);
        } catch (NormalizationPolicy.Violation exception) {
            String field = exception.field().replace("metadata.", "");
            throw ReadApiException.invalidRequest(field, exception.rule());
        }
    }

    public ListCursor decodeListCursor(
            String encoded,
            ListSort expectedSort,
            String expectedFilterFingerprint) {
        if (encoded == null) {
            return null;
        }
        if (encoded.isBlank() || encoded.length() > LIST_CURSOR_MAX_LENGTH) {
            throw ReadApiException.invalidCursor();
        }
        try {
            byte[] json = Base64.getUrlDecoder().decode(encoded);
            if (json.length > 768) {
                throw ReadApiException.invalidCursor();
            }
            ListCursor cursor = objectMapper.readValue(json, ListCursor.class);
            if (cursor.version() != CURSOR_VERSION
                    || cursor.sort() != expectedSort
                    || cursor.createdAt() == null
                    || cursor.id() == null
                    || !CONTENT_HASH.matcher(cursor.filterFingerprint()).matches()
                    || !MessageDigest.isEqual(
                            cursor.filterFingerprint().getBytes(StandardCharsets.US_ASCII),
                            expectedFilterFingerprint.getBytes(StandardCharsets.US_ASCII))) {
                throw ReadApiException.invalidCursor();
            }
            return cursor;
        } catch (ReadApiException exception) {
            throw exception;
        } catch (RuntimeException | java.io.IOException exception) {
            throw ReadApiException.invalidCursor();
        }
    }

    public String encodeListCursor(
            ListSort sort,
            Instant createdAt,
            UUID id,
            String filterFingerprint) {
        return encode(
                new ListCursor(CURSOR_VERSION, sort, createdAt, id, filterFingerprint),
                LIST_CURSOR_MAX_LENGTH);
    }

    public VersionCursor decodeVersionCursor(String encoded, VersionSort expectedSort) {
        if (encoded == null) {
            return null;
        }
        if (encoded.isBlank() || encoded.length() > VERSION_CURSOR_MAX_LENGTH) {
            throw ReadApiException.invalidCursor();
        }
        try {
            byte[] json = Base64.getUrlDecoder().decode(encoded);
            if (json.length > 384) {
                throw ReadApiException.invalidCursor();
            }
            VersionCursor cursor = objectMapper.readValue(json, VersionCursor.class);
            if (cursor.version() != CURSOR_VERSION
                    || cursor.sort() != expectedSort
                    || cursor.versionNumber() < 1) {
                throw ReadApiException.invalidCursor();
            }
            return cursor;
        } catch (ReadApiException exception) {
            throw exception;
        } catch (RuntimeException | java.io.IOException exception) {
            throw ReadApiException.invalidCursor();
        }
    }

    public String encodeVersionCursor(VersionSort sort, int versionNumber) {
        return encode(
                new VersionCursor(CURSOR_VERSION, sort, versionNumber),
                VERSION_CURSOR_MAX_LENGTH);
    }

    public static byte[] decodeContentHash(String supplied) {
        if (supplied == null) {
            return null;
        }
        if (!CONTENT_HASH.matcher(supplied).matches()) {
            throw ReadApiException.invalidRequest(
                    "content_hash",
                    "lowercase_sha256_hex");
        }
        return HexFormat.of().parseHex(supplied);
    }

    private String normalizeTextFilter(String supplied, String field) {
        if (supplied == null) {
            return null;
        }
        return textNormalizer
                .normalizeMetadata(supplied, field)
                .toLowerCase(Locale.ROOT);
    }

    private String filterFingerprint(
            String title,
            String company,
            String location,
            String contentHash,
            String canonicalUrl) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("title", title);
        values.put("company", company);
        values.put("location", location);
        values.put("content_hash", contentHash);
        values.put("canonical_url", canonicalUrl);
        try {
            return HexFormat.of().formatHex(
                    sha256().digest(objectMapper.writeValueAsBytes(values)));
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("Unable to encode normalized filters");
        }
    }

    private String encode(Object cursor, int maximumLength) {
        try {
            String encoded = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(objectMapper.writeValueAsBytes(cursor));
            if (encoded.length() > maximumLength) {
                throw new IllegalStateException("Cursor exceeded its documented bound");
            }
            return encoded;
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("Unable to encode cursor");
        }
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    public enum ListSort {
        @JsonProperty("created_at_desc")
        CREATED_AT_DESC,
        @JsonProperty("created_at_asc")
        CREATED_AT_ASC;

        public static ListSort parse(String value) {
            return switch (value == null ? "created_at_desc" : value) {
                case "created_at_desc" -> CREATED_AT_DESC;
                case "created_at_asc" -> CREATED_AT_ASC;
                default -> throw ReadApiException.invalidRequest("sort", "supported_value");
            };
        }
    }

    public enum VersionSort {
        @JsonProperty("version_desc")
        VERSION_DESC,
        @JsonProperty("version_asc")
        VERSION_ASC;

        public static VersionSort parse(String value) {
            return switch (value == null ? "version_desc" : value) {
                case "version_desc" -> VERSION_DESC;
                case "version_asc" -> VERSION_ASC;
                default -> throw ReadApiException.invalidRequest("sort", "supported_value");
            };
        }
    }

    public record NormalizedFilters(
            String title,
            String company,
            String location,
            byte[] contentHash,
            String contentHashHex,
            String canonicalUrl,
            String fingerprint) {

        public NormalizedFilters {
            contentHash = contentHash == null ? null : contentHash.clone();
        }
    }

    public record ListCursor(
            @JsonProperty("v") int version,
            ListSort sort,
            @JsonProperty("created_at") Instant createdAt,
            UUID id,
            @JsonProperty("filter_fingerprint") String filterFingerprint) {
    }

    public record VersionCursor(
            @JsonProperty("v") int version,
            VersionSort sort,
            @JsonProperty("version_number") int versionNumber) {
    }
}
