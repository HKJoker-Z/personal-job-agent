package io.github.hkjokerz.jobagent.jdnormalization.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class SkillExtractorTest {

    private SkillExtractor extractor;

    @BeforeEach
    void setUp() {
        SkillDictionary dictionary = new SkillDictionaryLoader(new ObjectMapper()).load(
                new ClassPathResource("skills/skills-v1.json"),
                NormalizationPolicy.MAX_UNIQUE_SKILLS);
        extractor = new SkillExtractor(dictionary);
    }

    @Test
    void classifiesRequiredPreferredAndMentionedByLexicalRules() {
        SkillExtractor.SkillMatches matches = extractor.extract(
                """
                Requirements:
                - Java 21
                - Spring Boot
                - C++
                Nice to have:
                - Python
                - C#
                - .NET
                - Node.js
                Responsibilities:
                Use Docker.
                """);

        assertThat(ids(matches.required()))
                .containsExactly("c-plus-plus", "java", "spring-boot");
        assertThat(ids(matches.preferred()))
                .containsExactly("c-sharp", "dotnet", "nodejs", "python");
        assertThat(ids(matches.mentioned())).containsExactly("docker");
    }

    @Test
    void strongestDuplicateCategoryWinsAndOutputsRemainDeterministic() {
        String text = """
                Java
                Preferred:
                - JAVA
                Requirements:
                - java 21
                """;

        for (int iteration = 0; iteration < 10; iteration++) {
            SkillExtractor.SkillMatches matches = extractor.extract(text);
            assertThat(ids(matches.required())).containsExactly("java");
            assertThat(matches.preferred()).isEmpty();
            assertThat(matches.mentioned()).isEmpty();
        }
    }

    @Test
    void supportsAliasesUnicodeCaseAndSpecialTechnologyNames() {
        String normalized = new TextNormalizer().normalizeJobDescription(
                "Must have SPRING\u00a0BOOT, c plus plus, CSHARP, DOTNET, NODEJS and AMAZON WEB SERVICES");

        SkillExtractor.SkillMatches matches = extractor.extract(normalized);

        assertThat(ids(matches.required()))
                .containsExactly(
                        "aws",
                        "c-plus-plus",
                        "c-sharp",
                        "dotnet",
                        "nodejs",
                        "spring-boot");
    }

    @Test
    void preventsOrdinaryWordAndEmbeddedTokenFalsePositives() {
        SkillExtractor.SkillMatches matches = extractor.extract(
                "JavaScript github cargo object.node.jsx springbooted restful");

        assertThat(ids(matches.mentioned())).containsExactly("javascript");
        assertThat(ids(matches.mentioned()))
                .doesNotContain("java", "git", "nodejs", "spring-boot", "rest");
    }

    @Test
    void sortsEveryCategoryByCanonicalSkillId() {
        SkillExtractor.SkillMatches matches =
                extractor.extract("Redis, Java, Docker, FastAPI, PostgreSQL");

        assertThat(ids(matches.mentioned()))
                .containsExactly("docker", "fastapi", "java", "postgresql", "redis");
    }

    private static java.util.List<String> ids(
            java.util.List<SkillDictionary.Skill> skills) {
        return skills.stream().map(SkillDictionary.Skill::id).toList();
    }
}
