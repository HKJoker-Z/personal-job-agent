package io.github.hkjokerz.jobagent.jdnormalization.persistence.update;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import java.util.Objects;

public record UpdateResult(
        ReadModels.Current current,
        boolean changed) {

    public UpdateResult {
        current = Objects.requireNonNull(current, "current");
    }
}
