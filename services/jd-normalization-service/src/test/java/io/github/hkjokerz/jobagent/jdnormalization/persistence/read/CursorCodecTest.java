package io.github.hkjokerz.jobagent.jdnormalization.persistence.read;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.TextNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.UrlNormalizer;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CursorCodecTest {

    private CursorCodec codec;

    @BeforeEach
    void setUp() {
        codec = new CursorCodec(
                JsonMapper.builder().addModule(new JavaTimeModule()).build(),
                new TextNormalizer(),
                new UrlNormalizer());
    }

    @Test
    void listCursorIsVersionedOpaqueRepeatableAndBoundToNormalizedFilters() {
        CursorCodec.NormalizedFilters filters = codec.normalizeFilters(
                " Senior\u00a0Backend Engineer ",
                "EXAMPLE LTD",
                null,
                "00".repeat(32),
                "HTTPS://Jobs.Example.Test:443/a/../role#apply");
        Instant timestamp = Instant.parse("2026-07-29T01:02:03.123456Z");
        UUID id = UUID.fromString("00000000-0000-4000-8000-000000000020");

        String first = codec.encodeListCursor(
                CursorCodec.ListSort.CREATED_AT_DESC,
                timestamp,
                id,
                filters.fingerprint());
        String second = codec.encodeListCursor(
                CursorCodec.ListSort.CREATED_AT_DESC,
                timestamp,
                id,
                filters.fingerprint());

        assertThat(first).isEqualTo(second).doesNotContain("=");
        assertThat(first.length()).isLessThanOrEqualTo(CursorCodec.LIST_CURSOR_MAX_LENGTH);
        CursorCodec.ListCursor decoded = codec.decodeListCursor(
                first,
                CursorCodec.ListSort.CREATED_AT_DESC,
                filters.fingerprint());
        assertThat(decoded.createdAt()).isEqualTo(timestamp);
        assertThat(decoded.id()).isEqualTo(id);
        assertThat(filters.title()).isEqualTo("senior backend engineer");
        assertThat(filters.company()).isEqualTo("example ltd");
        assertThat(filters.canonicalUrl()).isEqualTo("https://jobs.example.test/role");
    }

    @Test
    void rejectsSortOrFilterMismatchAndMalformedOrOverlongCursor() {
        CursorCodec.NormalizedFilters filters =
                codec.normalizeFilters("Java Engineer", null, null, null, null);
        String encoded = codec.encodeListCursor(
                CursorCodec.ListSort.CREATED_AT_DESC,
                Instant.parse("2026-07-29T00:00:00Z"),
                UUID.fromString("00000000-0000-4000-8000-000000000001"),
                filters.fingerprint());

        assertInvalidCursor(() -> codec.decodeListCursor(
                encoded,
                CursorCodec.ListSort.CREATED_AT_ASC,
                filters.fingerprint()));
        assertInvalidCursor(() -> codec.decodeListCursor(
                encoded,
                CursorCodec.ListSort.CREATED_AT_DESC,
                "f".repeat(64)));
        assertInvalidCursor(() -> codec.decodeListCursor(
                "***",
                CursorCodec.ListSort.CREATED_AT_DESC,
                filters.fingerprint()));
        assertInvalidCursor(() -> codec.decodeListCursor(
                "a".repeat(CursorCodec.LIST_CURSOR_MAX_LENGTH + 1),
                CursorCodec.ListSort.CREATED_AT_DESC,
                filters.fingerprint()));
    }

    @Test
    void versionCursorIsBoundedAndSortSpecific() {
        String encoded = codec.encodeVersionCursor(
                CursorCodec.VersionSort.VERSION_DESC,
                7);
        assertThat(codec.decodeVersionCursor(
                        encoded,
                        CursorCodec.VersionSort.VERSION_DESC)
                .versionNumber()).isEqualTo(7);
        assertInvalidCursor(() -> codec.decodeVersionCursor(
                encoded,
                CursorCodec.VersionSort.VERSION_ASC));
    }

    @Test
    void validatesExactLowercaseSha256FilterAndSafeMetadataBounds() {
        assertThat(CursorCodec.decodeContentHash("ab".repeat(32))).hasSize(32);
        assertThatThrownBy(() -> CursorCodec.decodeContentHash("AB".repeat(32)))
                .isInstanceOf(ReadApiException.class)
                .extracting(exception -> ((ReadApiException) exception).code())
                .isEqualTo("INVALID_REQUEST");
        assertThatThrownBy(() -> codec.normalizeFilters(
                        "x".repeat(201),
                        null,
                        null,
                        null,
                        null))
                .isInstanceOf(ReadApiException.class)
                .extracting(exception -> ((ReadApiException) exception).details().get("field"))
                .isEqualTo("title");
    }

    private static void assertInvalidCursor(org.assertj.core.api.ThrowableAssert.ThrowingCallable call) {
        assertThatThrownBy(call)
                .isInstanceOf(ReadApiException.class)
                .extracting(exception -> ((ReadApiException) exception).code())
                .isEqualTo("INVALID_CURSOR");
    }
}
