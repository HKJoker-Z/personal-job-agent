package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class SkillExtractor {

    private static final Pattern REQUIRED_HEADING = Pattern.compile(
            "^(required|required skills|requirements|qualifications)\\s*:?$",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern PREFERRED_HEADING = Pattern.compile(
            "^(preferred|preferred skills|nice to have|bonus|desirable)\\s*:?$",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern GENERIC_HEADING = Pattern.compile(
            "^[\\p{L}\\p{N} /&-]{1,80}:$",
            Pattern.UNICODE_CASE);
    private static final Pattern REQUIRED_CUE = Pattern.compile(
            "(?<![\\p{L}\\p{N}])(?:required|requirements|must[ -]have|qualifications)(?![\\p{L}\\p{N}])",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern PREFERRED_CUE = Pattern.compile(
            "(?<![\\p{L}\\p{N}])(?:preferred|nice[ -]to[ -]have|bonus|desirable)(?![\\p{L}\\p{N}])",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    private final SkillDictionary dictionary;

    public SkillExtractor(SkillDictionary dictionary) {
        this.dictionary = dictionary;
    }

    public SkillMatches extract(String normalizedText) {
        Map<String, Category> categories = new HashMap<>();
        Category section = Category.MENTIONED;

        for (String line : normalizedText.split("\n", -1)) {
            String trimmed = line.strip();
            if (REQUIRED_HEADING.matcher(trimmed).matches()) {
                section = Category.REQUIRED;
            } else if (PREFERRED_HEADING.matcher(trimmed).matches()) {
                section = Category.PREFERRED;
            } else if (GENERIC_HEADING.matcher(trimmed).matches()) {
                section = Category.MENTIONED;
            }

            Category lineCategory = categoryForLine(trimmed, section);
            for (SkillDictionary.Entry entry : dictionary.entries()) {
                boolean matched = entry.patterns().stream()
                        .anyMatch(pattern -> pattern.matcher(trimmed).find());
                if (matched) {
                    categories.merge(
                            entry.skill().id(),
                            lineCategory,
                            Category::stronger);
                }
            }
        }

        List<SkillDictionary.Skill> required = new ArrayList<>();
        List<SkillDictionary.Skill> preferred = new ArrayList<>();
        List<SkillDictionary.Skill> mentioned = new ArrayList<>();
        dictionary.entries().stream()
                .map(SkillDictionary.Entry::skill)
                .filter(skill -> categories.containsKey(skill.id()))
                .sorted(Comparator.comparing(SkillDictionary.Skill::id))
                .forEach(skill -> {
                    switch (categories.get(skill.id())) {
                        case REQUIRED -> required.add(skill);
                        case PREFERRED -> preferred.add(skill);
                        case MENTIONED -> mentioned.add(skill);
                    }
                });

        if (required.size() + preferred.size() + mentioned.size()
                > NormalizationPolicy.MAX_UNIQUE_SKILLS) {
            throw new IllegalStateException("Extracted skill bound was exceeded");
        }
        return new SkillMatches(required, preferred, mentioned);
    }

    public String dictionaryVersion() {
        return dictionary.version();
    }

    private static Category categoryForLine(String line, Category section) {
        String lower = line.toLowerCase(Locale.ROOT);
        if (REQUIRED_CUE.matcher(lower).find()) {
            return Category.REQUIRED;
        }
        if (PREFERRED_CUE.matcher(lower).find()) {
            return Category.PREFERRED;
        }
        return section;
    }

    private enum Category {
        MENTIONED(0),
        PREFERRED(1),
        REQUIRED(2);

        private final int priority;

        Category(int priority) {
            this.priority = priority;
        }

        static Category stronger(Category first, Category second) {
            return first.priority >= second.priority ? first : second;
        }
    }

    public record SkillMatches(
            List<SkillDictionary.Skill> required,
            List<SkillDictionary.Skill> preferred,
            List<SkillDictionary.Skill> mentioned) {

        public SkillMatches {
            required = List.copyOf(required);
            preferred = List.copyOf(preferred);
            mentioned = List.copyOf(mentioned);
        }
    }
}
