package io.github.hkjokerz.jobagent.jdnormalization.persistence.update;

import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.CreateFingerprints;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.create.NormalizedCreate;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Optional;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class JobDescriptionUpdateService {

    private final JobDescriptionNormalizer normalizer;
    private final CreateFingerprints fingerprints;
    private final ConditionalUpdateRepository updateRepository;

    public JobDescriptionUpdateService(
            JobDescriptionNormalizer normalizer,
            CreateFingerprints fingerprints,
            ConditionalUpdateRepository updateRepository) {
        this.normalizer = normalizer;
        this.fingerprints = fingerprints;
        this.updateRepository = updateRepository;
    }

    public UpdateResult update(
            UUID aggregateId,
            long expectedVersion,
            NormalizeJobDescriptionRequest request) {
        NormalizationResult normalized = normalizer.normalize(request);
        NormalizedCreate replacement = NormalizedCreate.from(
                normalized,
                fingerprints.forCreate(normalized));
        try {
            return updateRepository.update(
                    aggregateId,
                    expectedVersion,
                    replacement,
                    Instant.now().truncatedTo(ChronoUnit.MICROS));
        } catch (DataIntegrityViolationException exception) {
            Optional<ConditionalUpdateRepository.Duplicate> duplicate;
            try {
                duplicate = updateRepository.findDuplicate(
                        aggregateId,
                        replacement);
            } catch (DataAccessException classificationFailure) {
                throw exception;
            }
            if (duplicate.isPresent()) {
                ConditionalUpdateRepository.Duplicate conflict =
                        duplicate.orElseThrow();
                throw UpdateApiException.alreadyExists(
                        conflict.category(),
                        conflict.jobDescriptionId());
            }
            throw exception;
        }
    }
}
