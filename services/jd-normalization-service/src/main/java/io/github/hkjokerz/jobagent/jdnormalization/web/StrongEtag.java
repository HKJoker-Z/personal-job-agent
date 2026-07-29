package io.github.hkjokerz.jobagent.jdnormalization.web;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.UpdateApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;

final class StrongEtag {

    private static final int MAX_ENCODED_LENGTH = 21;
    private static final Pattern VERSION =
            Pattern.compile("\"(?:0|[1-9][0-9]{0,18})\"");

    private StrongEtag() {
    }

    static long requiredIfMatch(HttpServletRequest request) {
        List<String> values = request.getHeaderNames() == null
                ? List.of()
                : Collections.list(request.getHeaders("If-Match"));
        if (values.isEmpty()) {
            throw UpdateApiException.preconditionRequired();
        }
        if (values.size() != 1) {
            throw UpdateApiException.invalidIfMatch();
        }
        String value = values.getFirst();
        if (value.length() > MAX_ENCODED_LENGTH || !VERSION.matcher(value).matches()) {
            throw UpdateApiException.invalidIfMatch();
        }
        try {
            return Long.parseLong(value.substring(1, value.length() - 1));
        } catch (NumberFormatException exception) {
            throw UpdateApiException.invalidIfMatch();
        }
    }
}
