# ═══════════════════════════════════════════════════════════════════════════
# Cricket AI — Java Spring Boot Backend
# ─────────────────────────────────────────────────────────────────────────
# ARCHITECTURE: Single-stage runtime-only image.
#
#   WHY NOT multi-stage (Maven inside Docker)?
#     Multi-stage builds run 'mvn clean package' INSIDE Docker on every CI
#     run. That means:
#       • Maven downloads the entire internet (~300 MB of dependencies) on
#         every build because Docker's layer cache is invalidated by --no-cache.
#       • The compilation duplicates work already done by Stage 3 of Jenkins.
#       • Build time: 8-15 minutes for a dependency download that adds zero value.
#
#   INDUSTRY STANDARD — Separation of concerns:
#     ┌──────────────┐        ┌─────────────────────────────────┐
#     │  Jenkins CI  │        │  Docker (runtime packaging only) │
#     │ ─────────── │        │ ─────────────────────────────── │
#     │  Stage 3:   │        │  COPY the JAR that Jenkins       │
#     │  mvn package │──JAR──▶│  already compiled and tested.   │
#     │  Stage 4:   │        │  No Maven. No JDK. No internet.  │
#     │  JUnit tests │        │  Build time: < 30 seconds.       │
#     └──────────────┘        └─────────────────────────────────┘
#
#   RESULT:
#     • Docker build time: 8-15 min → < 30 seconds.
#     • Image size: same (~200 MB) — JRE-only, no JDK, no Maven.
#     • The JAR inside the image is the EXACT same artifact Jenkins tested.
#       No risk of Docker compiling slightly different code.
# ═══════════════════════════════════════════════════════════════════════════

# ── Runtime image ───────────────────────────────────────────────────────────
# eclipse-temurin:21-jre-alpine:
#   • JRE only   — no compiler (javac), no Maven. ~200 MB vs ~500 MB JDK.
#   • Alpine base — minimal Linux, smaller attack surface, faster pull.
#   • temurin 21 — Eclipse Adoptium LTS build; same JVM the Spring Boot app
#                  was compiled and tested against in Jenkins Stage 3 & 4.
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Create the upload directory the application expects at runtime.
# A Docker volume (configured in docker-compose.yml) overlays this path;
# this RUN ensures the directory exists even when no volume is mounted.
RUN mkdir -p /tmp/uploads

# ── Environment variables ────────────────────────────────────────────────────
# These become JVM-visible system env vars inside the container.
# docker-compose.yml or 'docker run -e' can override any of them.
#
# SERVER_PORT:
#   Spring Boot reads this env var as the override for server.port.
#   Set explicitly here so the port is self-documenting in the image and
#   cannot silently drift if application.properties is ever regenerated.
#
# JAVA_OPTS:
#   -XX:+UseContainerSupport   : Tells the JVM to read memory limits from
#                                Docker cgroups instead of the host RAM.
#   -XX:MaxRAMPercentage=75.0  : Use at most 75 % of the container's memory
#                                limit for the heap. Prevents OOM kills.
#   -Xms128m                   : Start with 128 MB heap to avoid slow startup
#                                on machines where the JVM is slow to grow.
ENV UPLOAD_DIR=/tmp/uploads
ENV SPRING_SERVLET_MULTIPART_LOCATION=/tmp/uploads
ENV SERVER_PORT=8080
ENV JAVA_OPTS="-Xms128m -Xmx512m -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"

# EXPOSE is documentation — it tells Docker (and humans) which port the
# process inside the container binds. Must match server.port / SERVER_PORT.
# The actual host-to-container mapping (-p 8081:8080) is set at 'docker run'
# time (Stage 8 of the Jenkinsfile) or in docker-compose.yml.
EXPOSE 8080

# ── Copy the pre-built JAR from the Jenkins workspace ───────────────────────
# Jenkins Stage 3 ran 'mvn clean package -DskipTests' and produced:
#   target/demobowling-analysis-backend-0.0.1-SNAPSHOT.jar
#
# The wildcard *.jar future-proofs against version number changes in pom.xml.
# If pom.xml artifactId or version changes, no Dockerfile edit is needed.
#
# This COPY instruction is the ONLY build step — it takes < 1 second.
COPY target/*.jar app.jar

# ── Entrypoint ───────────────────────────────────────────────────────────────
# Use 'sh -c' so the shell expands $JAVA_OPTS (ENV vars are not expanded
# inside JSON-array ENTRYPOINT ["java", "$JAVA_OPTS", "-jar", ...]).
# The sh process is PID 1 and forwards signals (SIGTERM) to the Java process.
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
