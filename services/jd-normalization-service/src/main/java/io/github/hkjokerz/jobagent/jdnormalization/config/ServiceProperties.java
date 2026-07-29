package io.github.hkjokerz.jobagent.jdnormalization.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jd-normalization")
public class ServiceProperties {

    private String dictionaryResource = "classpath:skills/skills-v1.json";
    private int dictionaryMaxEntries = 256;
    private final Security security = new Security();
    private final Idempotency idempotency = new Idempotency();

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

    public Idempotency getIdempotency() {
        return idempotency;
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

    public static final class Idempotency {

        private Duration processingLease = Duration.ofSeconds(30);
        private Duration completedRetention = Duration.ofHours(24);
        private int cleanupBatchSize = 100;
        private int maximumResponseBytes = 262_144;

        public Duration getProcessingLease() {
            return processingLease;
        }

        public void setProcessingLease(Duration processingLease) {
            this.processingLease = processingLease;
        }

        public Duration getCompletedRetention() {
            return completedRetention;
        }

        public void setCompletedRetention(Duration completedRetention) {
            this.completedRetention = completedRetention;
        }

        public int getCleanupBatchSize() {
            return cleanupBatchSize;
        }

        public void setCleanupBatchSize(int cleanupBatchSize) {
            this.cleanupBatchSize = cleanupBatchSize;
        }

        public int getMaximumResponseBytes() {
            return maximumResponseBytes;
        }

        public void setMaximumResponseBytes(int maximumResponseBytes) {
            this.maximumResponseBytes = maximumResponseBytes;
        }
    }
}
