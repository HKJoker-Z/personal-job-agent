package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.entity.SkillSnapshot;
import io.github.hkjokerz.jobagent.jdnormalization.persistence.read.ReadModels;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.ApiErrorResponse;
import io.github.hkjokerz.jobagent.jdnormalization.web.dto.JobDescriptionReadResponses;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record NormalizedCreate(
        String normalizedText,
        byte[] contentHash,
        byte[] deduplicationFingerprint,
        byte[] requestFingerprint,
        String normalizationPolicyVersion,
        String skillDictionaryVersion,
        List<SkillSnapshot> requiredSkills,
        List<SkillSnapshot> preferredSkills,
        List<SkillSnapshot> mentionedSkills,
        String title,
        String company,
        String location,
        String canonicalUrl) {

    public NormalizedCreate {
        contentHash = contentHash.clone();
        deduplicationFingerprint = deduplicationFingerprint.clone();
        requestFingerprint = requestFingerprint.clone();
        requiredSkills = List.copyOf(requiredSkills);
        preferredSkills = List.copyOf(preferredSkills);
        mentionedSkills = List.copyOf(mentionedSkills);
    }

    public static NormalizedCreate from(
            NormalizationResult result,
            CreateFingerprints.Fingerprints fingerprints) {
        return new NormalizedCreate(
                result.normalizedText(),
                HexFormat.of().parseHex(result.contentHash()),
                fingerprints.deduplicationFingerprint(),
                fingerprints.requestFingerprint(),
                result.normalizationPolicyVersion(),
                result.skillDictionaryVersion(),
                result.requiredSkills().stream()
                        .map(skill -> new SkillSnapshot(skill.id(), skill.name()))
                        .toList(),
                result.preferredSkills().stream()
                        .map(skill -> new SkillSnapshot(skill.id(), skill.name()))
                        .toList(),
                result.mentionedSkills().stream()
                        .map(skill -> new SkillSnapshot(skill.id(), skill.name()))
                        .toList(),
                result.metadata().title(),
                result.metadata().company(),
                result.metadata().location(),
                result.metadata().canonicalUrl());
    }

    JsonNode currentResponse(
            UUID aggregateId,
            Instant now,
            ObjectMapper objectMapper) {
        ReadModels.Current current = new ReadModels.Current(
                aggregateId,
                canonicalUrl,
                0L,
                1,
                normalizedText,
                contentHash,
                normalizationPolicyVersion,
                skillDictionaryVersion,
                requiredSkills,
                preferredSkills,
                mentionedSkills,
                title,
                company,
                location,
                now,
                now);
        return objectMapper.valueToTree(JobDescriptionReadResponses.Current.from(current));
    }

    JsonNode errorResponse(
            String code,
            String message,
            String requestId,
            Map<String, Object> details,
            ObjectMapper objectMapper) {
        return objectMapper.valueToTree(
                ApiErrorResponse.of(code, message, requestId, details));
    }

    public String requiredSkillsJson(ObjectMapper objectMapper) {
        return json(requiredSkills, objectMapper);
    }

    public String preferredSkillsJson(ObjectMapper objectMapper) {
        return json(preferredSkills, objectMapper);
    }

    public String mentionedSkillsJson(ObjectMapper objectMapper) {
        return json(mentionedSkills, objectMapper);
    }

    private static String json(Object value, ObjectMapper objectMapper) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Skill snapshot JSON could not be encoded");
        }
    }
}
