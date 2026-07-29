package io.github.hkjokerz.jobagent.jdnormalization.persistence.read;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescription;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescriptionVersion;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionRepository;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.repository.JobDescriptionVersionRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Expression;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class JobDescriptionReadService {

    private final EntityManager entityManager;
    private final JobDescriptionRepository jobDescriptionRepository;
    private final JobDescriptionVersionRepository versionRepository;
    private final CursorCodec cursorCodec;

    public JobDescriptionReadService(
            EntityManager entityManager,
            JobDescriptionRepository jobDescriptionRepository,
            JobDescriptionVersionRepository versionRepository,
            CursorCodec cursorCodec) {
        this.entityManager = entityManager;
        this.jobDescriptionRepository = jobDescriptionRepository;
        this.versionRepository = versionRepository;
        this.cursorCodec = cursorCodec;
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public ReadModels.Current current(UUID id) {
        return jobDescriptionRepository.findCurrent(id)
                .map(JobDescriptionReadService::toCurrent)
                .orElseThrow(ReadApiException::notFound);
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public ReadModels.Slice<ReadModels.Summary> list(
            int limit,
            CursorCodec.ListSort sort,
            CursorCodec.NormalizedFilters filters,
            CursorCodec.ListCursor cursor) {
        CriteriaBuilder criteria = entityManager.getCriteriaBuilder();
        CriteriaQuery<ReadModels.Summary> query =
                criteria.createQuery(ReadModels.Summary.class);
        Root<JobDescription> root = query.from(JobDescription.class);
        Root<JobDescriptionVersion> version = query.from(JobDescriptionVersion.class);

        List<Predicate> predicates = new ArrayList<>();
        predicates.add(criteria.equal(version.get("id"), root.get("currentVersionId")));
        predicates.add(criteria.equal(version.get("jobDescriptionId"), root.get("id")));
        addFilters(criteria, predicates, root, version, filters);
        if (cursor != null) {
            addListKeyset(criteria, predicates, root, sort, cursor);
        }

        query.select(criteria.construct(
                        ReadModels.Summary.class,
                        root.get("id"),
                        root.get("canonicalUrl"),
                        root.get("optimisticLockVersion"),
                        version.get("versionNumber"),
                        version.get("title"),
                        version.get("company"),
                        version.get("location"),
                        version.get("contentHash"),
                        root.get("createdAt"),
                        root.get("updatedAt")))
                .where(predicates.toArray(Predicate[]::new));

        if (sort == CursorCodec.ListSort.CREATED_AT_DESC) {
            query.orderBy(
                    criteria.desc(root.get("createdAt")),
                    criteria.desc(root.get("id")));
        } else {
            query.orderBy(
                    criteria.asc(root.get("createdAt")),
                    criteria.asc(root.get("id")));
        }

        List<ReadModels.Summary> fetched = entityManager.createQuery(query)
                .setMaxResults(limit + 1)
                .getResultList();
        boolean hasNext = fetched.size() > limit;
        List<ReadModels.Summary> items =
                new ArrayList<>(fetched.subList(0, Math.min(limit, fetched.size())));
        String nextCursor = null;
        if (hasNext && !items.isEmpty()) {
            ReadModels.Summary last = items.getLast();
            nextCursor = cursorCodec.encodeListCursor(
                    sort,
                    last.createdAt(),
                    last.id(),
                    filters.fingerprint());
        }
        return new ReadModels.Slice<>(items, nextCursor);
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public ReadModels.Slice<ReadModels.Version> versions(
            UUID id,
            int limit,
            CursorCodec.VersionSort sort,
            CursorCodec.VersionCursor cursor) {
        if (!jobDescriptionRepository.existsById(id)) {
            throw ReadApiException.notFound();
        }
        Integer position = cursor == null ? null : cursor.versionNumber();
        PageRequest page = PageRequest.of(0, limit + 1);
        List<JobDescriptionVersion> fetched =
                sort == CursorCodec.VersionSort.VERSION_DESC
                        ? versionRepository.findHistoryDescending(id, position, page)
                        : versionRepository.findHistoryAscending(id, position, page);
        boolean hasNext = fetched.size() > limit;
        List<ReadModels.Version> items = fetched.stream()
                .limit(limit)
                .map(JobDescriptionReadService::toVersion)
                .toList();
        String nextCursor = null;
        if (hasNext && !items.isEmpty()) {
            nextCursor = cursorCodec.encodeVersionCursor(
                    sort,
                    items.getLast().versionNumber());
        }
        return new ReadModels.Slice<>(items, nextCursor);
    }

    private static void addFilters(
            CriteriaBuilder criteria,
            List<Predicate> predicates,
            Root<JobDescription> root,
            Root<JobDescriptionVersion> version,
            CursorCodec.NormalizedFilters filters) {
        if (filters.title() != null) {
            predicates.add(criteria.equal(
                    criteria.lower(version.get("title")),
                    filters.title()));
        }
        if (filters.company() != null) {
            predicates.add(criteria.equal(
                    criteria.lower(version.get("company")),
                    filters.company()));
        }
        if (filters.location() != null) {
            predicates.add(criteria.equal(
                    criteria.lower(version.get("location")),
                    filters.location()));
        }
        if (filters.contentHash() != null) {
            predicates.add(criteria.equal(
                    version.get("contentHash"),
                    filters.contentHash()));
        }
        if (filters.canonicalUrl() != null) {
            predicates.add(criteria.equal(
                    root.get("canonicalUrl"),
                    filters.canonicalUrl()));
        }
    }

    private static void addListKeyset(
            CriteriaBuilder criteria,
            List<Predicate> predicates,
            Root<JobDescription> root,
            CursorCodec.ListSort sort,
            CursorCodec.ListCursor cursor) {
        Expression<Instant> createdAt = root.get("createdAt");
        Expression<UUID> id = root.get("id");
        Predicate timestamp;
        Predicate tiedId;
        if (sort == CursorCodec.ListSort.CREATED_AT_DESC) {
            timestamp = criteria.lessThan(createdAt, cursor.createdAt());
            tiedId = criteria.lessThan(id, cursor.id());
        } else {
            timestamp = criteria.greaterThan(createdAt, cursor.createdAt());
            tiedId = criteria.greaterThan(id, cursor.id());
        }
        predicates.add(criteria.or(
                timestamp,
                criteria.and(
                        criteria.equal(createdAt, cursor.createdAt()),
                        tiedId)));
    }

    private static ReadModels.Version toVersion(JobDescriptionVersion version) {
        return new ReadModels.Version(
                version.getId(),
                version.getVersionNumber(),
                version.getNormalizedText(),
                version.getContentHash(),
                version.getNormalizationPolicyVersion(),
                version.getSkillDictionaryVersion(),
                version.getRequiredSkills(),
                version.getPreferredSkills(),
                version.getMentionedSkills(),
                version.getTitle(),
                version.getCompany(),
                version.getLocation(),
                version.getCreatedAt());
    }

    private static ReadModels.Current toCurrent(
            JobDescriptionRepository.CurrentProjection value) {
        return new ReadModels.Current(
                value.getId(),
                value.getCanonicalUrl(),
                value.getOptimisticLockVersion(),
                value.getCurrentVersionNumber(),
                value.getNormalizedText(),
                value.getContentHash(),
                value.getNormalizationPolicyVersion(),
                value.getSkillDictionaryVersion(),
                value.getRequiredSkills(),
                value.getPreferredSkills(),
                value.getMentionedSkills(),
                value.getTitle(),
                value.getCompany(),
                value.getLocation(),
                value.getCreatedAt(),
                value.getUpdatedAt());
    }
}
