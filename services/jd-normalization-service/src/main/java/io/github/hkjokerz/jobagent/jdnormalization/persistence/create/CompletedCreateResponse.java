package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.UUID;

public record CompletedCreateResponse(
        int status,
        JsonNode body,
        String location,
        String etag,
        UUID jobDescriptionId,
        boolean replayed) {

    public CompletedCreateResponse {
        body = body.deepCopy();
    }

    public CompletedCreateResponse asReplay() {
        return new CompletedCreateResponse(
                status,
                body,
                location,
                etag,
                jobDescriptionId,
                true);
    }
}
