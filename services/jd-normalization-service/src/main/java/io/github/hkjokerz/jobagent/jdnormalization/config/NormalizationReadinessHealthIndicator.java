package io.github.hkjokerz.jobagent.jdnormalization.config;

import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationPolicy;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.SkillDictionary;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component("normalizationReadiness")
@Profile("normalization-only")
public class NormalizationReadinessHealthIndicator implements HealthIndicator {

    private final JobDescriptionNormalizer normalizer;
    private final SkillDictionary skillDictionary;

    public NormalizationReadinessHealthIndicator(
            JobDescriptionNormalizer normalizer,
            SkillDictionary skillDictionary) {
        this.normalizer = normalizer;
        this.skillDictionary = skillDictionary;
    }

    @Override
    public Health health() {
        boolean ready = normalizer != null
                && NormalizationPolicy.SKILL_DICTIONARY_VERSION.equals(
                        skillDictionary.version())
                && !skillDictionary.entries().isEmpty();
        return ready ? Health.up().build() : Health.down().build();
    }
}
