// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║        CRICKET BIOMECHANICS AI — JENKINS CI/CD PIPELINE                     ║
// ║        Project  : Cricket AI Biomechanics & Speed Analyzer                  ║
// ║        Stack    : Spring Boot 4 (Java 21) + FastAPI (Python) + Docker       ║
// ║        Version  : 3.0  (Phase 3 — Docker Hub Push Integrated)               ║
// ║                                                                              ║
// ║  PIPELINE FLOW                                                               ║
// ║  ─────────────────────────────────────────────────────────────────────────  ║
// ║  Stage 1  : Checkout source from GitHub                                     ║
// ║  Stage 2  : Verify Java 21 + Maven environment                              ║
// ║  Stage 3  : Maven clean package (compile → JAR)                             ║
// ║  Stage 4  : Run JUnit tests + publish report                                ║
// ║  Stage 5  : Build Docker image (--no-cache)                                 ║
// ║  Stage 6  : Docker Hub login (withCredentials — dockerhub-creds)            ║
// ║  Stage 7  : Tag and push image to Docker Hub                                ║
// ║  Stage 8  : Stop old container → remove → start new container               ║
// ║  Stage 9  : HTTP health check (retry loop until app is ready)               ║
// ║  Stage 10 : Archive JAR artefact with fingerprint                           ║
// ║                                                                              ║
// ║  PHASE ROADMAP                                                               ║
// ║  ─────────────────────────────────────────────────────────────────────────  ║
// ║  Phase 1 (done) : Checkout → Verify → Build → Test → Archive               ║
// ║  Phase 2 (done) : + Docker build → Local container deploy → Health check    ║
// ║  Phase 3 (this) : + Docker Hub login → Tag → Push to registry               ║
// ║  Phase 4 (next) : Deploy on AWS EC2 via SSH using pushed image              ║
// ║  Phase 5 (next) : Kubernetes (EKS) rolling deployment                       ║
// ║  Phase 6 (future): Blue-Green / canary / Slack notifications                ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

pipeline {

    // ──────────────────────────────────────────────────────────────────────────
    // AGENT
    // ──────────────────────────────────────────────────────────────────────────
    // 'agent any' → Run on ANY available Jenkins node.
    // For Windows local Jenkins this is the Jenkins controller itself.
    // Docker CLI must be installed and accessible on the PATH of this agent.
    //
    // PHASE 3 UPGRADE (Linux EC2):
    //   agent { label 'ec2-linux' }
    //   Replace every  bat '...'  with  sh '...'
    //   Replace  %VARIABLE%  with  $VARIABLE
    // ──────────────────────────────────────────────────────────────────────────
    agent any

    // ──────────────────────────────────────────────────────────────────────────
    // ENVIRONMENT VARIABLES
    // ──────────────────────────────────────────────────────────────────────────
    // Single source of truth. Change a value here and every stage picks it up.
    // ──────────────────────────────────────────────────────────────────────────
    environment {

        // ── Application identity ──────────────────────────────────────────────
        APP_NAME       = 'cricket-biomechanics-ai'
        APP_VERSION    = '0.0.1-SNAPSHOT'

        // JAR filename derived from pom.xml  <artifactId>-<version>.jar
        JAR_NAME       = "demobowling-analysis-backend-${APP_VERSION}.jar"

        // ── Maven wrapper ─────────────────────────────────────────────────────
        // mvnw.cmd = Windows batch wrapper bundled with the project.
        // Using the wrapper guarantees the project-pinned Maven version is used.
        // LINUX equivalent: ./mvnw
        MAVEN_CMD      = 'mvnw.cmd'

        // Suppress AWT errors in headless CI server environments.
        MAVEN_OPTS     = '-Djava.awt.headless=true'

        // ── Docker configuration ──────────────────────────────────────────────
        // All Docker-related constants live here so Stages 5-10 stay DRY.

        // The Docker image tag that gets built locally and deployed.
        DOCKER_IMAGE   = 'cricket-ai:latest'

        // The fully-qualified Docker Hub image name used in Stage 6 and Stage 7.
        // Format: <dockerhub-username>/<repository-name>:<tag>
        // credentialsId 'dockerhub-creds' must be created in Jenkins → Manage
        // Jenkins → Credentials before running the pipeline.
        DOCKER_HUB_IMAGE = 'gowtham2709/cricket-biomechanics-ai:latest'

        // The container name used in stop / rm / run commands.
        CONTAINER_NAME = 'cricket-ai'

        // Port inside the container Spring Boot listens on (application.properties).
        CONTAINER_PORT = '8080'

        // Port exposed on the Windows host machine.
        HOST_PORT      = '8081'

        // Health check URL — hit this to confirm the app is alive after deploy.
        // Uses the host port because Jenkins runs on the host, not inside Docker.
        HEALTH_URL     = "http://localhost:${HOST_PORT}"

        // Maximum number of health-check retry attempts before failing.
        // Each attempt waits HEALTH_WAIT_SECS seconds between retries.
        HEALTH_RETRIES = '15'

        // Seconds to wait between each health-check retry.
        HEALTH_WAIT_SECS = '6'

        // ── Python AI Microservice ────────────────────────────────────────────
        // Container name and image for the FastAPI Python AI service.
        // These must be kept in sync with Dockerfile.python and docker-compose.yml.
        PYTHON_AI_CONTAINER = 'python-ai'
        PYTHON_AI_IMAGE     = 'cricket-ai-python:latest'

        // The URL Spring Boot uses to reach the Python AI service.
        // When both run as plain 'docker run' containers (not docker-compose),
        // host.docker.internal resolves to the Windows host machine IP from
        // inside any Docker container — allowing the Spring Boot container to
        // reach the Python container via the host-published port 8000.
        AI_SERVICE_URL = 'http://host.docker.internal:8000'

        // ── Future variables (Phase 4 — AWS EC2 SSH deploy) ───────────────────
        // EC2_HOST         = credentials('ec2-host')
        // EC2_USER         = 'ubuntu'
    }

    // ──────────────────────────────────────────────────────────────────────────
    // PIPELINE-WIDE OPTIONS
    // ──────────────────────────────────────────────────────────────────────────
    options {

        // Keep only the last 10 builds + artefacts. Prevents unbounded disk growth.
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '10'))

        // Kill the entire pipeline if it runs longer than 45 minutes.
        // Phase 2 takes longer than Phase 1 because of Docker build time.
        timeout(time: 45, unit: 'MINUTES')

        // Prepend a timestamp to every console log line.
        // Essential for measuring stage durations and correlating failures.
        timestamps()

        // Prevent two builds from running at the same time.
        // Avoids race conditions where two builds fight over the same
        // container name or workspace directory.
        disableConcurrentBuilds()
    }

    // ──────────────────────────────────────────────────────────────────────────
    // STAGES
    // ──────────────────────────────────────────────────────────────────────────
    stages {

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 1 — CHECKOUT
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Jenkins workspaces start empty. This stage pulls the exact Git commit
        //   that triggered this build so every later stage has source to work with.
        //
        //   'checkout scm' reads the repo URL, branch, and credentials from the
        //   Jenkins job's "Pipeline from SCM" configuration — zero hardcoding.
        //
        //   The git log command burns the SHA and author into the console log,
        //   giving perfect traceability: which code produced which artefact.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 1 — Checkout Source Code') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 1 : Checking out source code from GitHub'
                echo '═══════════════════════════════════════════════════════'

                checkout scm

                // %% escapes the % character inside a bat string in Jenkins.
                bat 'git log -1 --format="Commit: %%H | Author: %%an | Date: %%ad | Msg: %%s"'

                // LINUX EC2 equivalent:
                // sh 'git log -1 --format="Commit: %H | Author: %an | Date: %ad | Msg: %s"'

                echo '✅  Source code checked out successfully.'
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 2 — VERIFY ENVIRONMENT
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Fails fast with a meaningful message if Java 21, Maven, or Docker
        //   CLI are missing from the agent — before wasting time on compilation.
        //
        //   Printing JAVA_HOME catches the silent mistake of Maven picking up a
        //   different JDK than the one the project requires.
        //
        //   'docker info' confirms Docker Desktop is running and the daemon is
        //   reachable. If Docker is not running, Stage 5 would fail with a
        //   confusing error; this surfaces it here with a clear label.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 2 — Verify Environment') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 2 : Verifying Java 21, Maven, and Docker CLI'
                echo '═══════════════════════════════════════════════════════'

                bat 'java -version'
                bat 'javac -version'
                bat "${MAVEN_CMD} --version"
                bat 'echo JAVA_HOME=%JAVA_HOME%'

                // Verify Docker daemon is running and CLI is on PATH.
                // 'docker info' exits non-zero if Docker Desktop is not running.
                bat 'docker info'
                bat 'docker --version'

                // LINUX EC2 equivalents:
                // sh 'java -version'
                // sh './mvnw --version'
                // sh 'docker info'

                echo '✅  Java 21 + Maven + Docker CLI all verified.'
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 3 — MAVEN CLEAN & BUILD
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Compile every Java source file and package them into a single
        //   executable fat-JAR (Spring Boot uber-JAR with embedded Tomcat).
        //
        //   -DskipTests  → Tests run in their own dedicated Stage 4, which
        //                   captures and publishes a proper JUnit XML report.
        //                   Skipping them here keeps Stage 3 fast and focused.
        //   clean        → Always delete target/ first — never compile against
        //                   stale .class files from a previous build.
        //   -B           → Batch mode: no ANSI progress bars cluttering CI logs.
        //   -e           → Full stack-trace on any Maven failure (not just summary).
        //
        // OUTPUT: target/demobowling-analysis-backend-0.0.1-SNAPSHOT.jar
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 3 — Maven Clean & Build') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 3 : mvnw clean package -DskipTests'
                echo '═══════════════════════════════════════════════════════'

                bat "${MAVEN_CMD} clean package -DskipTests -B -e"

                // LINUX EC2:
                // sh "./mvnw clean package -DskipTests -B -e"

                // Hard-fail if the JAR was not produced.
                // Without this check a broken Maven build could silently fall
                // through to the Docker stage, which would then fail on COPY.
                bat "if not exist target\\${JAR_NAME} (echo ❌ JAR missing: target\\${JAR_NAME} && exit /b 1)"

                echo "✅  JAR built: ${JAR_NAME}"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 4 — RUN TESTS
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   The quality gate. No code reaches a Docker container without passing
        //   every JUnit test.
        //
        //   The 'post { always }' block publishes the Surefire XML report even
        //   when some tests fail. Without 'always', a failed test aborts the
        //   stage before the report is written, and the Jenkins Test Results tab
        //   shows nothing — hiding the root cause.
        //
        //   Build state on test failure:
        //     • UNSTABLE (yellow) — tests ran but some failed.
        //     • The pipeline does NOT continue to Docker stages when UNSTABLE
        //       because subsequent stages check currentBuild.result.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 4 — Run Tests') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 4 : Running JUnit / Spring Boot tests'
                echo '═══════════════════════════════════════════════════════'

                bat "${MAVEN_CMD} test -B -e"

                // LINUX EC2:
                // sh "./mvnw test -B -e"
            }

            post {
                // Publish JUnit XML report regardless of pass / fail.
                always {
                    junit allowEmptyResults: true,
                          testResults: 'target/surefire-reports/*.xml'

                    echo '✅  JUnit report published → Jenkins Test Results tab.'
                }
                success {
                    echo '✅  All tests passed. Proceeding to Docker build.'
                }
                failure {
                    echo '❌  Test failures detected. Docker stages will be skipped.'
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 5 — BUILD DOCKER IMAGE
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Package the already-compiled JAR into a lightweight Docker runtime
        //   image. This stage does NOT compile anything — that was Stage 3's job.
        //
        //   ARCHITECTURE — why Maven no longer runs inside Docker:
        //     Old approach (multi-stage Dockerfile):
        //       docker build → RUN mvn dependency:go-offline  (~5 min, downloads ~300 MB)
        //                    → RUN mvn clean package           (~3-8 min)
        //       Total: 8-15 minutes. Maven ran TWICE per build (Stage 3 + inside Docker).
        //       With --no-cache the layer cache never saved us anything.
        //
        //     New approach (runtime-only Dockerfile):
        //       docker build → COPY target/*.jar app.jar       (< 1 second)
        //       Total: < 30 seconds. Maven runs ONCE (Stage 3). Docker only packages.
        //
        //   WHY this is the industry standard:
        //     The Jenkins pipeline is the CI system. Its job is to compile, test,
        //     and produce a verified artifact (the JAR). Docker's job is to package
        //     and ship that artifact — not to build it again.
        //     The JAR inside the image is the EXACT artifact Jenkins tested in Stage 4.
        //     This guarantees "what we tested is what we ship."
        //
        //   WHY --no-cache is still used:
        //     --no-cache ensures the COPY target/*.jar instruction always picks up
        //     the freshly compiled JAR from Stage 3 rather than a stale cached layer.
        //     With a pure COPY, --no-cache is nearly instant (< 1 s) because there
        //     is no download or compilation — just a file copy.
        //
        //   WHY tagged 'cricket-ai:latest':
        //     Stage 8 references this exact tag when starting the container.
        //     Stage 6 (Docker Hub login) and Stage 7 (push) also use DOCKER_IMAGE
        //     as the local source tag before pushing DOCKER_HUB_IMAGE.
        //
        //   The stage fails immediately if 'docker build' exits non-zero.
        //   There is no risk of deploying a broken image.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 5 — Build Docker Image') {
            // Skip this stage if an earlier stage marked the build UNSTABLE
            // (e.g., test failures). We never deploy from a broken build.
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 5 : Building Docker image → ${DOCKER_IMAGE}"
                echo '          (packaging pre-built JAR — no Maven inside Docker)'
                echo '═══════════════════════════════════════════════════════'

                // --no-cache  : Always picks up the freshly compiled JAR from target/.
                //               With a pure COPY Dockerfile this takes < 1 second.
                // -t          : Tag the image with the name defined in environment{}.
                // .           : Build context is the project root (Dockerfile + target/).
                //
                // WINDOWS bat:
                bat "docker build --no-cache -t ${DOCKER_IMAGE} ."

                // LINUX EC2 equivalent:
                // sh "docker build --no-cache -t ${DOCKER_IMAGE} ."

                // Confirm the image now exists in the local Docker daemon.
                bat "docker image inspect ${DOCKER_IMAGE} > nul 2>&1 && echo ✅ Image verified: ${DOCKER_IMAGE} || (echo ❌ Image not found after build && exit /b 1)"

                echo "✅  Docker image built and verified: ${DOCKER_IMAGE}"
                echo "    Build time target: < 30 seconds (COPY only — no Maven)"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 6 — DOCKER HUB LOGIN
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Authenticate the Jenkins agent with Docker Hub before Stage 7 can
        //   push the image to the remote registry.
        //
        //   WHY withCredentials:
        //     Storing credentials as plain-text environment variables exposes
        //     them in the console log and in 'env' output from child processes.
        //     withCredentials(usernamePassword(...)) binds the Jenkins secret to
        //     %DOCKER_USER% and %DOCKER_PASS% ONLY for the duration of the inner
        //     block. Jenkins automatically redacts these values in console output.
        //
        //   CREDENTIAL SETUP (one-time, in Jenkins UI):
        //     Jenkins → Manage Jenkins → Credentials → (global) → Add Credential
        //       Kind     : Username with password
        //       Username : your-dockerhub-username
        //       Password : your-dockerhub-access-token (NOT your account password)
        //       ID       : dockerhub-creds              ← must match credentialsId below
        //
        //   WHY --password-stdin:
        //     Passing the password via stdin avoids it appearing in the process
        //     argument list (visible in Task Manager / ps aux on Linux), which
        //     is a security best practice recommended by Docker and the CIS
        //     Docker Benchmark.
        //
        //   NOTE: 'echo %DOCKER_PASS% | docker login' is the Windows-compatible
        //   equivalent of 'echo $DOCKER_PASS | docker login' on Linux.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 6 — Docker Hub Login') {
            // Skip if an earlier stage failed — do not attempt to push from
            // a broken build.
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 6 : Logging in to Docker Hub'
                echo "            Registry image : ${DOCKER_HUB_IMAGE}"
                echo '═══════════════════════════════════════════════════════'

                // withCredentials injects %DOCKER_USER% and %DOCKER_PASS% from
                // the Jenkins secret identified by credentialsId = 'dockerhub-creds'.
                // Both variables are automatically masked in the console log.
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-creds',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    // ── ROOT CAUSE FIX: Windows CMD echo CRLF contamination ──────
                    //
                    // OLD (broken):
                    //   bat 'echo %DOCKER_PASS% | docker login -u %DOCKER_USER% --password-stdin'
                    //
                    //   Windows CMD 'echo' appends \r\n (CRLF) to every line.
                    //   'docker login --password-stdin' reads raw stdin bytes and strips
                    //   the trailing \n — but NOT the \r (carriage return).
                    //   Docker Hub therefore received:  <PAT>\r  (corrupted)
                    //   Result: "unauthorized: incorrect username or password" ❌
                    //
                    // NEW (fixed — PowerShell Write-Output):
                    //   PowerShell pipes strings to external (native) processes as a
                    //   UTF-8 byte stream WITHOUT a trailing \r.
                    //   'docker login --password-stdin' strips the final \n and receives
                    //   the clean PAT with no extra bytes.
                    //   Result: Login Succeeded ✅
                    //
                    // WHY $Env:DOCKER_PASS is safe here:
                    //   • The outer Groovy string uses single quotes → Groovy does NOT
                    //     interpolate $Env:DOCKER_PASS.  PowerShell expands it at runtime.
                    //   • Jenkins withCredentials automatically masks the value in the
                    //     console log regardless of which process reads the env var.
                    //   • The PAT never appears as a command-line argument (process list).
                    //
                    // WINDOWS bat (PowerShell):
                    bat 'powershell -NoProfile -NonInteractive -Command "Write-Output $Env:DOCKER_PASS | docker login -u $Env:DOCKER_USER --password-stdin"'

                    // LINUX EC2 equivalent (no CRLF issue on Linux — original form is fine):
                    // sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'
                }

                echo '✅  Docker Hub login successful.'
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 7 — PUSH DOCKER IMAGE
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Tag the locally-built image with its Docker Hub name and push it to
        //   the remote registry so it is:
        //     • Available to any machine that can reach Docker Hub.
        //     • Permanently versioned in the registry for rollback.
        //     • Ready to pull on AWS EC2 in Phase 4 without transferring the
        //       image out-of-band.
        //
        //   WHY docker tag first:
        //     docker build in Stage 5 produced 'cricket-ai:latest' — a local
        //     short name. Docker Hub requires the full registry path:
        //       <username>/<repository>:<tag>
        //     docker tag creates a second name pointing to the SAME image layers;
        //     no data is duplicated on disk.
        //
        //   WHY DOCKER_HUB_IMAGE from environment{}:
        //     Using the env var instead of a hardcoded string means changing
        //     the repository name or tag requires editing exactly one line
        //     (the environment{} block) — not hunting through stage bodies.
        //
        //   FAILURE BEHAVIOUR:
        //     If docker push fails (network error, auth expired, quota exceeded)
        //     this stage exits non-zero and Jenkins marks the build FAILURE.
        //     Stages 8-10 are guarded by when{} checks and will be skipped,
        //     protecting the running container from being replaced by an image
        //     that failed to push.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 7 — Push Docker Image') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 7 : Tagging  ${DOCKER_IMAGE} → ${DOCKER_HUB_IMAGE}"
                echo "            Pushing  ${DOCKER_HUB_IMAGE}"
                echo '═══════════════════════════════════════════════════════'

                // ── Step 7a: Tag the local image with its Docker Hub name ──────
                // This does NOT copy image data — it just adds a second name
                // (alias) to the image that already exists in the local daemon.
                echo '  → Step 7a: Tagging image for Docker Hub...'
                bat "docker tag ${DOCKER_IMAGE} ${DOCKER_HUB_IMAGE}"

                // LINUX EC2 equivalent:
                // sh "docker tag ${DOCKER_IMAGE} ${DOCKER_HUB_IMAGE}"

                // ── Step 7b: Push the tagged image to Docker Hub ──────────────
                // Uploads only the layers that are not already present in the
                // registry (layer de-duplication). Subsequent pushes of the same
                // base layers are near-instant.
                echo '  → Step 7b: Pushing image to Docker Hub...'
                bat "docker push ${DOCKER_HUB_IMAGE}"

                // LINUX EC2 equivalent:
                // sh "docker push ${DOCKER_HUB_IMAGE}"

                echo "✅  Image pushed to Docker Hub: ${DOCKER_HUB_IMAGE}"
                echo "    View : https://hub.docker.com/r/gowtham2709/cricket-biomechanics-ai"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 8 — DEPLOY DOCKER CONTAINER
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Replace the currently running container with a fresh one from the
        //   image built in Stage 5. This is the actual "deployment" step.
        //
        //   STEP-BY-STEP:
        //     1. docker stop   → Gracefully send SIGTERM to the running container.
        //                        The '|| echo ...' suffix prevents the pipeline
        //                        from failing if no container is running (first run).
        //     2. docker rm     → Remove the stopped container record so 'docker run'
        //                        can reuse the same --name.
        //                        Safe to call even if stop failed (container gone).
        //     3. docker rmi    → Delete the previous image to free disk space.
        //                        This is optional but prevents image accumulation.
        //                        'cricket-ai:latest' will still exist because
        //                        Stage 5 just built the new one with the same tag —
        //                        Docker retags automatically.
        //                        NOTE: we remove the IMAGE first, then run with
        //                        the newly built one that already exists.
        //     4. docker run -d → Start the new container in detached mode
        //                        (background). Jenkins does NOT wait for the app
        //                        to be ready here — that is Stage 7's job.
        //
        //   PORT MAPPING:
        //     -p 8081:8080 → Host:Container
        //     Browser/Jenkins hits localhost:8081 → Docker routes to container:8080
        //     → Spring Boot (server.port=8080) handles the request.
        //
        //   --restart unless-stopped:
        //     If Docker Desktop restarts (e.g., after a Windows reboot) the
        //     container will automatically come back up without manual intervention.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 8 — Deploy Docker Container') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 8 : Deploying container → ${CONTAINER_NAME}"
                echo "            Image        : ${DOCKER_IMAGE}"
                echo "            Port mapping : ${HOST_PORT}:${CONTAINER_PORT}"
                echo '═══════════════════════════════════════════════════════'

                // ── Step 8a: Stop the running container ───────────────────────
                // '|| echo' absorbs the error exit code when no container exists.
                // Without this, the pipeline would FAIL on the very first run.
                echo '  → Step 8a: Stopping existing container (if running)...'
                bat "docker stop ${CONTAINER_NAME} || echo No container named ${CONTAINER_NAME} to stop."

                // ── Step 8b: Remove the stopped container record ──────────────
                // Must remove before 'docker run --name' can reuse the same name.
                echo '  → Step 8b: Removing old container record (if present)...'
                bat "docker rm ${CONTAINER_NAME} || echo No container named ${CONTAINER_NAME} to remove."

                // ── Step 8c: Remove the old image to reclaim disk space ───────
                // The new image already exists (built in Stage 5).
                // '|| echo' absorbs error when image does not exist (first run).
                echo '  → Step 8c: Pruning old dangling image layers...'
                bat "docker image prune -f || echo No dangling images to prune."

                // ── Step 8d: Start the Python AI service container ────────────
                //
                // ROOT CAUSE FIX — why the AI service was unreachable:
                //   The Spring Boot container called http://localhost:8000/...
                //   Inside a Docker container, 'localhost' refers to the container
                //   itself — NOT the host machine and NOT other containers.
                //   The Python AI service was never started by Jenkins, and even if
                //   it were, localhost would still be the wrong address.
                //
                // SOLUTION — two parts:
                //   1. Jenkins explicitly builds and starts the python-ai container.
                //   2. The Spring Boot container receives AI_SERVICE_URL set to
                //      http://host.docker.internal:8000 — a special DNS name that
                //      Docker for Windows automatically resolves to the host machine
                //      IP (gateway), allowing any container to reach any service
                //      published on the host's port 8000.
                //
                // NETWORKING DIAGRAM:
                //   [Browser] → localhost:8081
                //       → [cricket-ai container : 8080]
                //             → AI_SERVICE_URL = http://host.docker.internal:8000
                //                   → [host machine port 8000]
                //                         → [python-ai container : 8000]
                //
                // Stop + remove the old Python AI container (first run: no-op).
                echo '  → Step 8d-i: Stopping old Python AI container (if running)...'
                bat "docker stop ${PYTHON_AI_CONTAINER} || echo No container named ${PYTHON_AI_CONTAINER} to stop."
                bat "docker rm   ${PYTHON_AI_CONTAINER} || echo No container named ${PYTHON_AI_CONTAINER} to remove."

                // Build the Python AI image from Dockerfile.python.
                // --no-cache ensures the latest main.py and analysis scripts are used.
                echo '  → Step 8d-ii: Building Python AI image from Dockerfile.python...'
                bat "docker build --no-cache -f Dockerfile.python -t ${PYTHON_AI_IMAGE} ."

                // Start the Python AI container.
                // -p 8000:8000  : Publishes port 8000 on the host so host.docker.internal
                //                 can route traffic from the Spring Boot container to it.
                // PYTHONUNBUFFERED=1 : Ensures FastAPI/uvicorn logs appear immediately.
                echo '  → Step 8d-iii: Starting Python AI container on port 8000...'
                bat "docker run -d ^" +
                    " -p 8000:8000 ^" +
                    " --name ${PYTHON_AI_CONTAINER} ^" +
                    " -v cricket_uploads:/tmp/uploads ^" +
                    " -e PYTHONUNBUFFERED=1 ^" +
                    " --restart unless-stopped ^" +
                    " ${PYTHON_AI_IMAGE}"

                // Wait for uvicorn to bind port 8000 before starting Spring Boot.
                // Without this, Spring Boot might start and fail its first health-check
                // call to the Python service before uvicorn is ready.
                echo '  → Step 8d-iv: Waiting 15s for uvicorn to start...'
                bat 'powershell -Command "Start-Sleep -Seconds 15"'

                // ── Step 8e: Start the Spring Boot container ──────────────────
                // -e AI_SERVICE_URL : Overrides the localhost default hardcoded in
                //                     VideoUploadController.java line 56.
                //                     host.docker.internal resolves to the host
                //                     machine IP from inside any Docker container.
                // -v cricket_uploads: Shared volume so both containers access the
                //                     same /tmp/uploads directory — Spring Boot writes
                //                     the uploaded video, Python reads it by path.
                echo '  → Step 8e: Starting Spring Boot container...'
                bat "docker run -d ^" +
                    " -p ${HOST_PORT}:${CONTAINER_PORT} ^" +
                    " --name ${CONTAINER_NAME} ^" +
                    " -e AI_SERVICE_URL=${AI_SERVICE_URL} ^" +
                    " -e UPLOAD_DIR=/tmp/uploads ^" +
                    " -e SPRING_SERVLET_MULTIPART_LOCATION=/tmp/uploads ^" +
                    " -e SERVER_PORT=${CONTAINER_PORT} ^" +
                    " -v cricket_uploads:/tmp/uploads ^" +
                    " --restart unless-stopped ^" +
                    " ${DOCKER_IMAGE}"

                // LINUX EC2 equivalent:
                // sh """
                //   docker stop  ${PYTHON_AI_CONTAINER} || true
                //   docker rm    ${PYTHON_AI_CONTAINER} || true
                //   docker build --no-cache -f Dockerfile.python -t ${PYTHON_AI_IMAGE} .
                //   docker run -d -p 8000:8000 --name ${PYTHON_AI_CONTAINER} \\
                //     -v cricket_uploads:/tmp/uploads \\
                //     -e PYTHONUNBUFFERED=1 --restart unless-stopped ${PYTHON_AI_IMAGE}
                //   sleep 15
                //   docker stop  ${CONTAINER_NAME} || true
                //   docker rm    ${CONTAINER_NAME} || true
                //   docker run -d -p ${HOST_PORT}:${CONTAINER_PORT} \\
                //     --name ${CONTAINER_NAME} \\
                //     -e AI_SERVICE_URL=http://host.docker.internal:8000 \\
                //     -e UPLOAD_DIR=/tmp/uploads \\
                //     -v cricket_uploads:/tmp/uploads \\
                //     --restart unless-stopped ${DOCKER_IMAGE}
                // """

                echo "✅  Both containers started:"
                echo "    python-ai  → localhost:8000  (FastAPI / uvicorn)"
                echo "    ${CONTAINER_NAME} → localhost:${HOST_PORT} (Spring Boot)"
                echo "    Spring Boot → AI via host.docker.internal:8000"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 9 — HTTP HEALTH CHECK
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   The build should only be marked SUCCESS when the application is
        //   actually serving HTTP traffic — not just because the container
        //   started. Spring Boot takes 3-8 seconds to initialise Tomcat, load
        //   the application context, and register routes. This stage bridges
        //   that gap with a retry loop.
        //
        //   ALGORITHM:
        //     1. Wait 10 s for Spring Boot to initialise Tomcat.
        //     2. Try  curl --fail localhost:8081  (exits 0 on 2xx/3xx response).
        //     3. If it fails, sleep HEALTH_WAIT_SECS seconds and retry.
        //     4. After HEALTH_RETRIES attempts, call error() → FAILURE.
        //
        //   WHY script{} instead of bat + PowerShell:
        //     Embedding a PowerShell loop inside a Groovy GString ("""...""")
        //     requires escaping every PowerShell $ variable with \$ to stop
        //     Groovy from interpolating them. That is error-prone and caused the
        //     "unexpected token: false" parse error.
        //
        //     The idiomatic Jenkins solution is a Groovy script{} block:
        //       • All loop state ($i, $healthy, etc.) is plain Groovy — no $ clash.
        //       • bat(returnStatus: true) captures curl's exit code without
        //         immediately failing the step, giving us retry control.
        //       • sleep() is a built-in Jenkins step — no PowerShell needed.
        //       • Jenkins env vars (HEALTH_RETRIES, HEALTH_URL, etc.) are read
        //         via env.VARIABLE — clear and explicit.
        //
        //   WHAT COUNTS AS HEALTHY:
        //     Any HTTP 2xx or 3xx from localhost:8081 (the index.html welcome page).
        //     To use /actuator/health instead, add spring-boot-starter-actuator to
        //     pom.xml and set HEALTH_URL = "http://localhost:${HOST_PORT}/actuator/health".
        //
        //   curl flags:
        //     --fail        Exit code 1 on HTTP 4xx/5xx responses.
        //     --silent      No download progress bars in the log.
        //     --max-time 5  Each probe times out after 5 s (avoids blocking a retry slot).
        //     --output NUL  Discard body — we only care about the exit code.
        //
        //   TIMEOUT SAFETY:
        //     The outer pipeline timeout(45 MINUTES) prevents an infinite hang
        //     if something goes catastrophically wrong.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 9 — Health Check') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 9 : Health check → ${HEALTH_URL}"
                echo "            Max retries : ${HEALTH_RETRIES}"
                echo "            Wait between: ${HEALTH_WAIT_SECS}s"
                echo '═══════════════════════════════════════════════════════'

                // ── Pure Groovy retry loop — zero PowerShell $ escaping needed ──
                script {
                    // Read Jenkins env vars into typed Groovy locals.
                    // env.* is always a String; toInteger() converts for numeric ops.
                    int  maxRetries = env.HEALTH_RETRIES.toInteger()   // 15
                    int  waitSecs   = env.HEALTH_WAIT_SECS.toInteger() // 6
                    String healthUrl = env.HEALTH_URL                  // http://localhost:8081

                    // Give Spring Boot time to bind the port before the first probe.
                    // Without this head-start the first attempt hits connection-refused
                    // while Tomcat is still starting, wasting a retry slot.
                    echo '  → Waiting 10 seconds for Spring Boot to initialise...'
                    sleep(time: 10, unit: 'SECONDS')

                    boolean healthy = false

                    for (int attempt = 1; attempt <= maxRetries; attempt++) {
                        echo "[Health Check] Attempt ${attempt} of ${maxRetries} → ${healthUrl}"

                        // bat(returnStatus: true) runs the command and returns the
                        // OS exit code as an integer WITHOUT failing the pipeline step.
                        // This gives us full retry control in Groovy.
                        int exitCode = bat(
                            script: "curl --fail --silent --max-time 5 --output NUL ${healthUrl}",
                            returnStatus: true
                        )

                        if (exitCode == 0) {
                            // curl exited 0 → HTTP 2xx/3xx received → app is up.
                            echo '[Health Check] ✅ Application is UP and healthy!'
                            healthy = true
                            break
                        }

                        // curl exited non-zero → app not ready yet.
                        echo "[Health Check] ⏳ Not ready (exit ${exitCode}). Waiting ${waitSecs}s..."
                        sleep(time: waitSecs, unit: 'SECONDS')
                    }

                    if (!healthy) {
                        // Dump the last 30 log lines to help diagnose startup failures.
                        echo '[Health Check] ❌ Application did not respond. Dumping container logs:'
                        bat "docker logs --tail=30 ${CONTAINER_NAME}"

                        // error() sets the build to FAILURE and throws an exception
                        // that stops the pipeline immediately — clean and explicit.
                        error("[Health Check] Application at ${healthUrl} did not respond after ${maxRetries} retries.")
                    }
                }

                // Print the final container status table in the console log.
                echo '  → Final container status:'
                bat "docker ps --filter name=${CONTAINER_NAME} --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\""

                echo "✅  Health check PASSED. Application is live at ${HEALTH_URL}"
            }
        }


        // ══════════════════════════════════════════════════════════════════════
        // STAGE 10 — ARCHIVE JAR ARTEFACT
        // ══════════════════════════════════════════════════════════════════════
        // PURPOSE:
        //   Save a permanent copy of the deployable JAR in Jenkins' own storage.
        //
        //   This enables:
        //     • Downloading the exact JAR that is running in the container.
        //     • Rolling back: redeploy a previous build's JAR by re-running it.
        //     • Traceability: fingerprint links this JAR to every build that used it.
        //
        //   Archive happens AFTER health check so only a JAR that produced a
        //   healthy container gets archived. Failed deployments are not preserved.
        //
        //   fingerprint: true
        //     Jenkins hashes the JAR (MD5) and records the hash in build metadata.
        //     Clickable in the Jenkins UI: "which builds used this exact file?"
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 10 — Archive JAR Artefact') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 10 : Archiving ${JAR_NAME}"
                echo '═══════════════════════════════════════════════════════'

                archiveArtifacts artifacts: "target/${JAR_NAME}",
                                 fingerprint: true,
                                 allowEmptyArchive: false

                echo "✅  Artefact archived: ${JAR_NAME}"
                echo "    Download: Jenkins → Build #${BUILD_NUMBER} → Artefacts"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // ── PHASE 3 STUB: DockerHub Push + AWS EC2 SSH Deploy ─────────────────
        // Uncomment the entire block when Phase 3 work begins.
        // ══════════════════════════════════════════════════════════════════════
        /*
        stage('Stage 9 — Push Image to DockerHub') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-creds',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS')]) {

                    // Tag locally-built image with remote name before pushing.
                    bat "docker tag ${DOCKER_IMAGE} %DOCKER_USER%/${APP_NAME}:${BUILD_NUMBER}"
                    bat "docker tag ${DOCKER_IMAGE} %DOCKER_USER%/${APP_NAME}:latest"
                    bat "echo %DOCKER_PASS% | docker login -u %DOCKER_USER% --password-stdin"
                    bat "docker push %DOCKER_USER%/${APP_NAME}:${BUILD_NUMBER}"
                    bat "docker push %DOCKER_USER%/${APP_NAME}:latest"
                }
                echo "✅  Image pushed to DockerHub: ${APP_NAME}:${BUILD_NUMBER}"
            }
        }

        stage('Stage 10 — Deploy to AWS EC2') {
            steps {
                sshagent(['ec2-ssh-key']) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} '
                          docker pull ${DOCKER_IMAGE}
                          docker stop ${CONTAINER_NAME}  || true
                          docker rm   ${CONTAINER_NAME}  || true
                          docker run -d -p ${HOST_PORT}:${CONTAINER_PORT} \\
                            --name ${CONTAINER_NAME} \\
                            --restart unless-stopped \\
                            ${DOCKER_IMAGE}
                        '
                    """
                }
                echo "✅  Deployed to EC2: ${EC2_HOST}:${HOST_PORT}"
            }
        }

        stage('Stage 11 — EC2 Smoke Test') {
            steps {
                sh "curl -f http://${EC2_HOST}:${HOST_PORT} || exit 1"
                echo "✅  EC2 smoke test passed."
            }
        }
        */

        // ── PHASE 4 STUB: Kubernetes (EKS) ─────────────────────────────────
        /*
        stage('Stage 12 — EKS Rolling Deploy') {
            steps {
                sh """
                    kubectl set image deployment/${APP_NAME} \\
                        ${APP_NAME}=${DOCKER_IMAGE} -n production
                    kubectl rollout status deployment/${APP_NAME} -n production
                """
            }
        }
        */

    } // ── end stages ──────────────────────────────────────────────────────────

    // ──────────────────────────────────────────────────────────────────────────
    // POST-PIPELINE ACTIONS
    // ──────────────────────────────────────────────────────────────────────────
    // These blocks always execute after all stages — like a Java finally{} block.
    // Order of evaluation: success | failure | unstable | aborted → then always.
    // ──────────────────────────────────────────────────────────────────────────
    post {

        success {
            echo ''
            echo '╔══════════════════════════════════════════════════════════╗'
            echo '║  ✅  PIPELINE COMPLETED SUCCESSFULLY                     ║'
            echo "║  App       : ${APP_NAME}                                 ║"
            echo "║  Build     : #${BUILD_NUMBER}                            ║"
            echo "║  Local img : ${DOCKER_IMAGE}                             ║"
            echo "║  Hub image : ${DOCKER_HUB_IMAGE}                         ║"
            echo "║  Container : ${CONTAINER_NAME}                           ║"
            echo "║  Live URL  : ${HEALTH_URL}                               ║"
            echo '╚══════════════════════════════════════════════════════════╝'

            // PHASE 3: Uncomment to send Slack success notification.
            // slackSend channel: '#cricket-ai-ci',
            //             color: 'good',
            //             message: "✅ Build #${BUILD_NUMBER} deployed — ${APP_NAME}\nURL: ${HEALTH_URL}\n${BUILD_URL}"
        }

        failure {
            echo ''
            echo '╔══════════════════════════════════════════════════════════╗'
            echo '║  ❌  PIPELINE FAILED                                      ║'
            echo "║  Build     : #${BUILD_NUMBER}                            ║"
            echo '║  Action    : Check Console Output for the root cause.    ║'
            echo "║  Container : docker logs ${CONTAINER_NAME}               ║"
            echo '╚══════════════════════════════════════════════════════════╝'

            // On failure, print the last 50 lines of container logs to help
            // diagnose whether the failure was a Spring Boot startup crash.
            // '|| echo' prevents this from masking the original failure exit code.
            bat "docker logs --tail=50 ${CONTAINER_NAME} || echo (container not running)"

            // PHASE 3: Uncomment to send email/Slack failure alert.
            // emailext subject: "❌ Jenkins FAILED — ${APP_NAME} #${BUILD_NUMBER}",
            //          body: "Pipeline failed.\nSee: ${BUILD_URL}console",
            //          to: 'your-email@example.com'
        }

        unstable {
            echo '⚠️   PIPELINE UNSTABLE — test failures detected.'
            echo '     Docker stages were skipped to protect the running container.'
            echo '     Fix the failing tests and rebuild.'
        }

        aborted {
            echo '⏹️   PIPELINE ABORTED — manually cancelled or timed out.'
            echo "     Container state: run 'docker ps -a' to inspect."
        }

        always {
            echo "─── Pipeline finished | Duration: ${currentBuild.durationString} ───"

            // Clean the Jenkins workspace to free disk space.
            // archiveArtifacts has already saved the JAR to Jenkins storage,
            // so cleaning here does NOT lose any build output.
            //
            // The running Docker container is NOT affected by cleanWs().
            // It continues running independently of the Jenkins workspace.
            //
            // Comment this out if you need to inspect workspace files post-failure.
            cleanWs()
        }
    }

} // ── end pipeline ────────────────────────────────────────────────────────────
