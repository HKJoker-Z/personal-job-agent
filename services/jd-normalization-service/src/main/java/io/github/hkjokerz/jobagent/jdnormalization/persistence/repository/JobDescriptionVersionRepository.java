package io.github.hkjokerz.jobagent.jdnormalization.persistence.repository;

import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.JobDescriptionVersion;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface JobDescriptionVersionRepository
        extends Repository<JobDescriptionVersion, UUID> {

    @Query("""
            select v
            from JobDescriptionVersion v
            where v.jobDescriptionId = :jobDescriptionId
              and (:beforeVersion is null or v.versionNumber < :beforeVersion)
            order by v.versionNumber desc
            """)
    List<JobDescriptionVersion> findHistoryDescending(
            @Param("jobDescriptionId") UUID jobDescriptionId,
            @Param("beforeVersion") Integer beforeVersion,
            Pageable pageable);

    @Query("""
            select v
            from JobDescriptionVersion v
            where v.jobDescriptionId = :jobDescriptionId
              and (:afterVersion is null or v.versionNumber > :afterVersion)
            order by v.versionNumber asc
            """)
    List<JobDescriptionVersion> findHistoryAscending(
            @Param("jobDescriptionId") UUID jobDescriptionId,
            @Param("afterVersion") Integer afterVersion,
            Pageable pageable);
}
