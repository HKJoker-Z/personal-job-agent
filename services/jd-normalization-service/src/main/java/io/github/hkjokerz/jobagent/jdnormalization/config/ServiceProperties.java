package io.github.hkjokerz.jobagent.jdnormalization.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jd-normalization")
public class ServiceProperties {

    private String dictionaryResource = "classpath:skills/skills-v1.json";
    private int dictionaryMaxEntries = 256;
    private final Security security = new Security();

    public String getDictionaryResource() {
        return dictionaryResource;
    }

    public void setDictionaryResource(String dictionaryResource) {
        this.dictionaryResource = dictionaryResource;
    }

    public int getDictionaryMaxEntries() {
        return dictionaryMaxEntries;
    }

    public void setDictionaryMaxEntries(int dictionaryMaxEntries) {
        this.dictionaryMaxEntries = dictionaryMaxEntries;
    }

    public Security getSecurity() {
        return security;
    }

    public static final class Security {

        private String apiKey = "";
        private boolean authenticationDisabled;

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey == null ? "" : apiKey;
        }

        public boolean isAuthenticationDisabled() {
            return authenticationDisabled;
        }

        public void setAuthenticationDisabled(boolean authenticationDisabled) {
            this.authenticationDisabled = authenticationDisabled;
        }

        public void clearApiKey() {
            apiKey = "";
        }
    }
}
