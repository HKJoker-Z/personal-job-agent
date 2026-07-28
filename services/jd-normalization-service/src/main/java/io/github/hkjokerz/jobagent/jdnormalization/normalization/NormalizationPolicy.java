package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import java.util.Map;

public final class NormalizationPolicy {

    public static final String VERSION = "jd-normalization-v1";
    public static final String SKILL_DICTIONARY_VERSION = "skills-v1";
    public static final int MAX_REQUEST_BYTES = 512 * 1024;
    public static final int MAX_RAW_TEXT_CODE_POINTS = 100_000;
    public static final int MAX_METADATA_CODE_POINTS = 200;
    public static final int MAX_CANONICAL_URL_ASCII_LENGTH = 2_048;
    public static final int MAX_UNIQUE_SKILLS = 256;

    private NormalizationPolicy() {
    }

    public static final class Violation extends RuntimeException {

        private final String errorCode;
        private final String field;
        private final String rule;
        private final Map<String, Object> safeMetadata;

        public Violation(
                String errorCode,
                String field,
                String rule,
                Map<String, Object> safeMetadata) {
            super(errorCode + ":" + field + ":" + rule);
            this.errorCode = errorCode;
            this.field = field;
            this.rule = rule;
            this.safeMetadata = Map.copyOf(safeMetadata);
        }

        public String errorCode() {
            return errorCode;
        }

        public String field() {
            return field;
        }

        public String rule() {
            return rule;
        }

        public Map<String, Object> safeMetadata() {
            return safeMetadata;
        }
    }
}
