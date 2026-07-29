package io.github.hkjokerz.jobagent.jdnormalization;

import static org.assertj.core.api.Assertions.assertThat;

import io.github.hkjokerz.jobagent.jdnormalization.normalization.SkillDictionary;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class JdNormalizationServiceApplicationTest {

    @Autowired
    private ApplicationContext applicationContext;

    @Autowired
    private SkillDictionary skillDictionary;

    @Test
    void startsBoundedPhaseOneApplicationContext() {
        assertThat(applicationContext).isNotNull();
        assertThat(skillDictionary.version()).isEqualTo("skills-v1");
        assertThat(applicationContext.containsBean("entityManagerFactory")).isFalse();
        assertThat(applicationContext.containsBean("dataSource")).isFalse();
    }
}
