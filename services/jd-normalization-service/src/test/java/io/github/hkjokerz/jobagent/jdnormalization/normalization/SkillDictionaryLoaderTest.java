package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.ByteArrayResource;

class SkillDictionaryLoaderTest {

    private final SkillDictionaryLoader loader =
            new SkillDictionaryLoader(new ObjectMapper());

    @Test
    void loadsReviewedDictionaryInCanonicalIdOrder() {
        SkillDictionary dictionary = loader.load(
                new ClassPathResource("skills/skills-v1.json"),
                NormalizationPolicy.MAX_UNIQUE_SKILLS);

        assertThat(dictionary.version()).isEqualTo("skills-v1");
        assertThat(dictionary.entries())
                .hasSizeBetween(20, 64)
                .extracting(entry -> entry.skill().id())
                .isSorted()
                .contains(
                        "java",
                        "spring-boot",
                        "c-plus-plus",
                        "c-sharp",
                        "dotnet",
                        "nodejs");
    }

    @Test
    void failsStartupOnNormalizedDuplicateAlias() {
        assertThatThrownBy(() -> loader.load(
                        new ClassPathResource("skills/invalid-duplicate-aliases.json"),
                        NormalizationPolicy.MAX_UNIQUE_SKILLS))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Skill dictionary aliases must be unique");
    }

    @Test
    void failsOnDuplicateIdMissingFieldsUnsupportedTypeAndBound() {
        assertInvalid(
                """
                {"version":"skills-v1","skills":[
                  {"id":"java","name":"Java","aliases":["java"],"match_type":"TOKEN"},
                  {"id":"java","name":"Other","aliases":["other"],"match_type":"TOKEN"}
                ]}
                """,
                256);
        assertInvalid(
                """
                {"version":"skills-v1","skills":[
                  {"id":"java","aliases":["java"],"match_type":"TOKEN"}
                ]}
                """,
                256);
        assertInvalid(
                """
                {"version":"skills-v1","skills":[
                  {"id":"java","name":"Java","aliases":["java"],"match_type":"REGEX"}
                ]}
                """,
                256);
        assertInvalid(
                """
                {"version":"skills-v1","skills":[
                  {"id":"java","name":"Java","aliases":["java"],"match_type":"TOKEN"}
                ]}
                """,
                0);
    }

    @Test
    void dictionaryValuesAreQuotedRatherThanExecutedAsRegex() {
        SkillDictionary dictionary = loader.load(
                new ByteArrayResource(
                        """
                        {"version":"skills-v1","skills":[
                          {"id":"cpp","name":"C++","aliases":["c++"],"match_type":"TOKEN"}
                        ]}
                        """.getBytes(java.nio.charset.StandardCharsets.UTF_8)),
                1);

        assertThat(dictionary.entries().getFirst().patterns().getFirst().matcher("C++").find())
                .isTrue();
        assertThat(dictionary.entries().getFirst().patterns().getFirst().matcher("CCC").find())
                .isFalse();
    }

    private void assertInvalid(String json, int maximum) {
        assertThatThrownBy(() -> loader.load(
                        new ByteArrayResource(
                                json.getBytes(java.nio.charset.StandardCharsets.UTF_8)),
                        maximum))
                .isInstanceOf(IllegalStateException.class);
    }
}
