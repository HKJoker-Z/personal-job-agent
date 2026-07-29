# syntax=docker/dockerfile:1

ARG JAVA_BUILDER_IMAGE=eclipse-temurin:21-jdk-jammy@sha256:9d8dcf999b0bce2453e913823595a5ff2a4e8e9e5d5241b45280d0ff069818ec
ARG JAVA_RUNTIME_IMAGE=eclipse-temurin:21-jre-jammy@sha256:d63bd8d9b171999cbed8576f2c76e874dd4856791a358536e5c4d407e77edc13
ARG FLYWAY_IMAGE=flyway/flyway:11.7.2-alpine@sha256:a493a5ef0700f6d1ef4f7b83320f79601071b20749c2eca1d73dd2e352948656

FROM ${JAVA_BUILDER_IMAGE} AS builder

WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

COPY src/ src/
RUN ./mvnw \
        -B \
        -ntp \
        -Dmaven.test.skip=true \
        -Dmaven.wagon.http.retryHandler.count=3 \
        package \
    && test -f target/jd-normalization-service-0.1.0-SNAPSHOT.jar

FROM ${JAVA_RUNTIME_IMAGE} AS application

ARG OCI_SOURCE=https://github.com/HKJoker-Z/personal-job-agent
ARG OCI_REVISION=unknown

LABEL org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.title="JD Normalization Service" \
      org.opencontainers.image.description="Independent internal JD normalization API"

RUN groupadd --gid 10001 jdnormalization \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --shell /usr/sbin/nologin \
        jdnormalization

WORKDIR /opt/jd-normalization

COPY --from=builder \
    --chown=10001:10001 \
    /workspace/target/jd-normalization-service-0.1.0-SNAPSHOT.jar \
    /opt/jd-normalization/application.jar

ENV JD_NORMALIZATION_BIND_ADDRESS=0.0.0.0 \
    JD_NORMALIZATION_PORT=8080

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD ["curl", "--fail", "--silent", "--show-error", "--max-time", "2", "http://127.0.0.1:8080/actuator/health/readiness"]

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-Djava.io.tmpdir=/tmp", "-jar", "/opt/jd-normalization/application.jar"]

FROM ${FLYWAY_IMAGE} AS migration

ARG OCI_SOURCE=https://github.com/HKJoker-Z/personal-job-agent
ARG OCI_REVISION=unknown

LABEL org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.title="JD Normalization Service migrations" \
      org.opencontainers.image.description="One-shot Flyway V1 and V2 migration runner"

USER root

RUN addgroup -g 10002 flywayrunner \
    && adduser \
        -D \
        -H \
        -u 10002 \
        -G flywayrunner \
        flywayrunner

COPY --chown=10002:10002 \
    src/main/resources/db/migration/ \
    /flyway/sql/
COPY --chown=0:0 \
    docker/migrate-and-validate.sh \
    /usr/local/bin/migrate-and-validate

RUN chmod 0555 /usr/local/bin/migrate-and-validate \
    && find /flyway/sql -type f -exec chmod 0444 {} \;

USER 10002:10002

ENTRYPOINT ["/usr/local/bin/migrate-and-validate"]
