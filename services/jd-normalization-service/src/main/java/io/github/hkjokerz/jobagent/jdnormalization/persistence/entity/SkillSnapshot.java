package io.github.hkjokerz.jobagent.jdnormalization.persistence.entity;

import java.util.Objects;

public record SkillSnapshot(String id, String name) {

    public SkillSnapshot {
        id = Objects.requireNonNull(id, "id");
        name = Objects.requireNonNull(name, "name");
    }
}
