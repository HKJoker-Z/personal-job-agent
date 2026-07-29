package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import static org.assertj.core.api.Assertions.assertThat;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescription;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionVersionRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.update.ConditionalUpdateRepository;
import jakarta.persistence.Version;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PersistenceRepositorySafetyTest {

    @Test
    void applicationRepositoriesExposeOnlyFocusedOperations() throws Exception {
        assertThat(methods(JobDescriptionRepository.class))
                .containsExactlyInAnyOrder("existsById", "findCurrent");
        assertThat(methods(JobDescriptionVersionRepository.class))
                .containsExactlyInAnyOrder(
                        "findHistoryAscending",
                        "findHistoryDescending");
        assertThat(methods(IdempotencyLedgerRepository.class))
                .containsExactlyInAnyOrder(
                        "claim",
                        "cleanupExpiredCompleted",
                        "finalizeCreate");
        assertThat(methods(ConditionalUpdateRepository.class))
                .containsExactlyInAnyOrder("findDuplicate", "update");
        assertThat(methods(JobDescriptionRepository.class))
                .noneMatch(name -> name.equals("save") || name.equals("delete"));
        assertThat(JobDescription.class
                        .getDeclaredField("optimisticLockVersion")
                        .isAnnotationPresent(Version.class))
                .isTrue();
    }

    private static Set<String> methods(Class<?> type) {
        return Arrays.stream(type.getDeclaredMethods())
                .filter(method -> java.lang.reflect.Modifier.isPublic(method.getModifiers()))
                .map(Method::getName)
                .collect(Collectors.toSet());
    }
}
