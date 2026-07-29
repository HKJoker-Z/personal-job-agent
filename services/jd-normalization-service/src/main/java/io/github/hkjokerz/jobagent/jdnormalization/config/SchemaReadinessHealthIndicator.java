package io.github.hkjokerz.jobagent.jdnormalization.config;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component("schemaReadiness")
@ConditionalOnBean(JdbcTemplate.class)
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class SchemaReadinessHealthIndicator implements HealthIndicator {

    private final JdbcTemplate jdbcTemplate;

    public SchemaReadinessHealthIndicator(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Health health() {
        try {
            Boolean usable = jdbcTemplate.queryForObject("""
                    SELECT
                        to_regclass('job_descriptions') IS NOT NULL
                        AND to_regclass('job_description_versions') IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM flyway_schema_history
                            WHERE version = '1'
                              AND success
                        )
                    """, Boolean.class);
            return Boolean.TRUE.equals(usable) ? Health.up().build() : Health.down().build();
        } catch (DataAccessException exception) {
            return Health.down().build();
        }
    }
}
