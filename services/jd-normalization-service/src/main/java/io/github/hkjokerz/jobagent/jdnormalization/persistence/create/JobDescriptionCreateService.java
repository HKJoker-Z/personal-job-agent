package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import io.github.hkjokerz.jobagent.jdnormalization.config.ServiceProperties;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.JobDescriptionNormalizer;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.NormalizeJobDescriptionRequest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class JobDescriptionCreateService {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(JobDescriptionCreateService.class);

    private final JobDescriptionNormalizer normalizer;
    private final CreateFingerprints fingerprints;
    private final IdempotencyLedgerRepository ledgerRepository;
    private final int maximumResponseBytes;

    public JobDescriptionCreateService(
            JobDescriptionNormalizer normalizer,
            CreateFingerprints fingerprints,
            IdempotencyLedgerRepository ledgerRepository,
            ServiceProperties properties) {
        this.normalizer = normalizer;
        this.fingerprints = fingerprints;
        this.ledgerRepository = ledgerRepository;
        this.maximumResponseBytes =
                properties.getIdempotency().getMaximumResponseBytes();
    }

    public CompletedCreateResponse create(
            String rawIdempotencyKey,
            NormalizeJobDescriptionRequest request,
            String requestId) {
        NormalizationResult normalization = normalizer.normalize(request);
        CreateFingerprints.Fingerprints computed =
                fingerprints.forCreate(normalization);
        NormalizedCreate create = NormalizedCreate.from(normalization, computed);
        byte[] keyHash = fingerprints.idempotencyKeyHash(rawIdempotencyKey);

        try {
            CompletedCreateResponse response =
                    claimAndComplete(keyHash, create, requestId);
            return response;
        } catch (CreateApiException exception) {
            throw exception;
        } catch (DataAccessException | IllegalStateException exception) {
            LOGGER.error("idempotency_persistence_failed");
            throw CreateApiException.persistenceFailed();
        } finally {
            cleanupBestEffort();
        }
    }

    private CompletedCreateResponse claimAndComplete(
            byte[] keyHash,
            NormalizedCreate create,
            String requestId) {
        for (int ownershipAttempt = 0; ownershipAttempt < 2; ownershipAttempt++) {
            Instant claimTime = now();
            IdempotencyLedgerRepository.Claim claim = ledgerRepository.claim(
                    keyHash,
                    create.requestFingerprint(),
                    UUID.randomUUID(),
                    claimTime);
            switch (claim.outcome()) {
                case REPLAY -> {
                    return claim.response();
                }
                case REUSED -> throw CreateApiException.keyReused();
                case IN_PROGRESS -> throw CreateApiException.inProgress(
                        claim.retryAfterSeconds());
                case ACQUIRED -> {
                    try {
                        return ledgerRepository.finalizeCreate(
                                claim.ledgerId(),
                                claim.attemptToken(),
                                create,
                                requestId,
                                maximumResponseBytes,
                                now());
                    } catch (IdempotencyLedgerRepository.ClaimOwnershipException exception) {
                        if (ownershipAttempt == 1) {
                            throw CreateApiException.inProgress(1);
                        }
                    }
                }
            }
        }
        throw CreateApiException.persistenceFailed();
    }

    private void cleanupBestEffort() {
        try {
            ledgerRepository.cleanupExpiredCompleted(now());
        } catch (DataAccessException | IllegalStateException exception) {
            LOGGER.warn("idempotency_cleanup_failed");
        }
    }

    private static Instant now() {
        return Instant.now().truncatedTo(ChronoUnit.MICROS);
    }
}
