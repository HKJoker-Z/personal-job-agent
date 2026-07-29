package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hkjokerz.jobagent.jdnormalization.config.ServiceProperties;
import java.io.IOException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;

@Component
public class SkillDictionaryLoader {

    private static final Pattern VALID_ID = Pattern.compile("[a-z0-9][a-z0-9-]{0,63}");
    private static final String TOKEN_PREFIX_BOUNDARY = "\\p{L}\\p{N}_.+#";
    private static final String TOKEN_SUFFIX_BOUNDARY = "\\p{L}\\p{N}_";

    private final ObjectMapper objectMapper;

    public SkillDictionaryLoader(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @org.springframework.context.annotation.Bean
    SkillDictionary skillDictionary(
            ServiceProperties properties,
            ResourceLoader resourceLoader) {
        if (properties.getDictionaryMaxEntries() < 1
                || properties.getDictionaryMaxEntries() > NormalizationPolicy.MAX_UNIQUE_SKILLS) {
            throw new IllegalStateException("Skill dictionary bound is invalid");
        }
        return load(
                resourceLoader.getResource(properties.getDictionaryResource()),
                properties.getDictionaryMaxEntries());
    }

    public SkillDictionary load(Resource resource, int maximumEntries) {
        DictionaryFile file;
        try (var input = resource.getInputStream()) {
            file = objectMapper.readValue(input, DictionaryFile.class);
        } catch (IOException exception) {
            throw new IllegalStateException("Skill dictionary could not be loaded");
        }

        if (file.version() == null
                || !NormalizationPolicy.SKILL_DICTIONARY_VERSION.equals(file.version())
                || file.skills() == null
                || file.skills().isEmpty()
                || file.skills().size() > maximumEntries) {
            throw new IllegalStateException("Skill dictionary metadata is invalid");
        }

        Set<String> ids = new HashSet<>();
        Map<String, String> aliasOwners = new HashMap<>();
        List<SkillDictionary.Entry> entries = new ArrayList<>(file.skills().size());
        for (SkillRecord record : file.skills()) {
            validateRequiredFields(record);
            if (!ids.add(record.id())) {
                throw new IllegalStateException("Skill dictionary IDs must be unique");
            }

            SkillDictionary.MatchType matchType;
            try {
                matchType = SkillDictionary.MatchType.valueOf(record.matchType());
            } catch (IllegalArgumentException exception) {
                throw new IllegalStateException("Skill dictionary match type is unsupported");
            }

            List<String> aliases = new ArrayList<>(record.aliases().size());
            List<Pattern> patterns = new ArrayList<>(record.aliases().size());
            for (String suppliedAlias : record.aliases()) {
                String alias = normalizeAlias(suppliedAlias);
                if (alias.isBlank()) {
                    throw new IllegalStateException("Skill dictionary alias is blank");
                }
                String priorOwner = aliasOwners.putIfAbsent(alias, record.id());
                if (priorOwner != null) {
                    throw new IllegalStateException("Skill dictionary aliases must be unique");
                }
                aliases.add(alias);
                patterns.add(compileQuotedAlias(alias));
            }

            entries.add(new SkillDictionary.Entry(
                    new SkillDictionary.Skill(record.id(), record.name()),
                    aliases,
                    matchType,
                    patterns));
        }

        entries.sort(java.util.Comparator.comparing(entry -> entry.skill().id()));
        return new SkillDictionary(file.version(), entries);
    }

    private static void validateRequiredFields(SkillRecord record) {
        if (record == null
                || record.id() == null
                || !VALID_ID.matcher(record.id()).matches()
                || record.name() == null
                || record.name().isBlank()
                || record.aliases() == null
                || record.aliases().isEmpty()
                || record.matchType() == null) {
            throw new IllegalStateException("Skill dictionary record is incomplete");
        }
    }

    private static String normalizeAlias(String alias) {
        if (alias == null) {
            return "";
        }
        return TextNormalizer.collapseWhitespace(
                        Normalizer.normalize(alias, Normalizer.Form.NFC))
                .toLowerCase(Locale.ROOT);
    }

    private static Pattern compileQuotedAlias(String alias) {
        String suffixBoundary = TOKEN_SUFFIX_BOUNDARY
                + (alias.endsWith("+") ? "+" : "")
                + (alias.endsWith("#") ? "#" : "");
        return Pattern.compile(
                "(?<![" + TOKEN_PREFIX_BOUNDARY + "])"
                        + Pattern.quote(alias)
                        + "(?![" + suffixBoundary + "])",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    }

    private record DictionaryFile(String version, List<SkillRecord> skills) {
    }

    private record SkillRecord(
            String id,
            String name,
            List<String> aliases,
            @JsonProperty("match_type") String matchType) {
    }
}
