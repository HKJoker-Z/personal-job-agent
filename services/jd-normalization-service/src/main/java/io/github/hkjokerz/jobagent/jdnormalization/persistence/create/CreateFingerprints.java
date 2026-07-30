package io.github.hkjokerz.jobagent.jdnormalization.persistence.create;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.NormalizationResult;
import io.github.hkjokerz.jobagent.jdnormalization.normalization.SkillDictionary;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "jd-normalization.persistence.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class CreateFingerprints {

    static final String CREATE_CONTRACT_VERSION = "jd-create-v1";
    static final String DEDUPLICATION_DOMAIN = "jd-deduplication:v1";
    static final String REQUEST_DOMAIN = "jd-create-request:v1";
    private static final String KEY_DOMAIN = "jd-normalization:idempotency-key:v1";

    private final ObjectMapper objectMapper;

    public CreateFingerprints(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public byte[] idempotencyKeyHash(String rawKey) {
        return digest(KEY_DOMAIN, rawKey.getBytes(StandardCharsets.UTF_8));
    }

    public Fingerprints forCreate(NormalizationResult result) {
        ObjectNode deduplication = objectMapper.createObjectNode();
        putNullable(deduplication, "canonical_url", result.metadata().canonicalUrl());
        putNullable(deduplication, "company", result.metadata().company());
        deduplication.set("mentioned_skill_ids", skillIds(result.mentionedSkills()));
        deduplication.put(
                "normalization_policy_version",
                result.normalizationPolicyVersion());
        deduplication.put("normalized_text", result.normalizedText());
        putNullable(deduplication, "location", result.metadata().location());
        deduplication.set("preferred_skill_ids", skillIds(result.preferredSkills()));
        deduplication.set("required_skill_ids", skillIds(result.requiredSkills()));
        deduplication.put(
                "skill_dictionary_version",
                result.skillDictionaryVersion());
        putNullable(deduplication, "title", result.metadata().title());

        ObjectNode request = objectMapper.createObjectNode();
        request.put("content_hash", result.contentHash());
        request.put("create_contract_version", CREATE_CONTRACT_VERSION);
        ObjectNode metadata = request.putObject("metadata");
        putNullable(metadata, "canonical_url", result.metadata().canonicalUrl());
        putNullable(metadata, "company", result.metadata().company());
        putNullable(metadata, "location", result.metadata().location());
        putNullable(metadata, "title", result.metadata().title());
        request.set("mentioned_skills", skills(result.mentionedSkills()));
        request.put(
                "normalization_policy_version",
                result.normalizationPolicyVersion());
        request.put("normalized_text", result.normalizedText());
        request.set("preferred_skills", skills(result.preferredSkills()));
        request.set("required_skills", skills(result.requiredSkills()));
        request.put("skill_dictionary_version", result.skillDictionaryVersion());

        return new Fingerprints(
                digest(DEDUPLICATION_DOMAIN, canonicalBytes(deduplication)),
                digest(REQUEST_DOMAIN, canonicalBytes(request)));
    }

    private byte[] canonicalBytes(ObjectNode value) {
        try {
            return objectMapper.writeValueAsBytes(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Canonical fingerprint JSON could not be encoded");
        }
    }

    private ArrayNode skillIds(java.util.List<SkillDictionary.Skill> values) {
        ArrayNode result = objectMapper.createArrayNode();
        values.forEach(value -> result.add(value.id()));
        return result;
    }

    private ArrayNode skills(java.util.List<SkillDictionary.Skill> values) {
        ArrayNode result = objectMapper.createArrayNode();
        values.forEach(value -> {
            ObjectNode skill = result.addObject();
            skill.put("id", value.id());
            skill.put("name", value.name());
        });
        return result;
    }

    private static void putNullable(ObjectNode node, String field, String value) {
        if (value == null) {
            node.putNull(field);
        } else {
            node.put(field, value);
        }
    }

    private static byte[] digest(String domain, byte[] payload) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(domain.getBytes(StandardCharsets.UTF_8));
            digest.update((byte) 0);
            return digest.digest(payload);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable");
        }
    }

    public record Fingerprints(
            byte[] deduplicationFingerprint,
            byte[] requestFingerprint) {

        public Fingerprints {
            deduplicationFingerprint = deduplicationFingerprint.clone();
            requestFingerprint = requestFingerprint.clone();
        }
    }
}
