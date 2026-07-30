# ═══════════════════════════════════════════════════════════════════════════
# Cricket AI — Java Spring Boot Backend  (multi-stage, optimized)
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Build ─────────────────────────────────────────────────────────
FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app

# Cache Maven dependencies independently of source code changes.
# Only re-downloads when pom.xml changes.
COPY pom.xml .
RUN mvn dependency:go-offline -B -q

# Now copy source and build
COPY src ./src
RUN mvn clean package -DskipTests -B -q

# ── Stage 2: Runtime ───────────────────────────────────────────────────────
# Alpine JRE = ~200 MB vs ~500 MB for full JDK.
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Create upload dir inside image (volume mount will overlay at runtime)
RUN mkdir -p /tmp/uploads

# Environment defaults — docker-compose.yml can override these.
# SERVER_PORT is the Spring Boot env-var equivalent of server.port.
# Declaring it here makes the port self-documenting and prevents any
# external env override from silently changing it.
ENV UPLOAD_DIR=/tmp/uploads
ENV SPRING_SERVLET_MULTIPART_LOCATION=/tmp/uploads
ENV SERVER_PORT=8080
ENV JAVA_OPTS="-Xms128m -Xmx512m -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"

# EXPOSE documents the port the container listens on.
# Must match server.port in application.properties (8080).
EXPOSE 8080

COPY --from=build /app/target/*.jar app.jar

# Use JAVA_OPTS so memory limits are respected in Docker
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
