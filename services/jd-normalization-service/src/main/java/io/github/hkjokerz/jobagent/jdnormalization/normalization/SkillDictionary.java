package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.util.List;
import java.util.regex.Pattern;

public record SkillDictionary(String version, List<Entry> entries) {

    public SkillDictionary {
        entries = List.copyOf(entries);
    }

    public record Entry(
            Skill skill,
            List<String> aliases,
            MatchType matchType,
            List<Pattern> patterns) {

        public Entry {
            aliases = List.copyOf(aliases);
            patterns = List.copyOf(patterns);
        }
    }

    public record Skill(String id, String name) {
    }

    public enum MatchType {
        TOKEN,
        PHRASE
    }
}
