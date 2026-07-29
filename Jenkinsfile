// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║        CRICKET BIOMECHANICS AI — JENKINS CI/CD PIPELINE                     ║
// ║        Project  : Cricket AI Biomechanics & Speed Analyzer                  ║
// ║        Stack    : Spring Boot 4 (Java 21) + FastAPI (Python) + Docker       ║
// ║        Version  : 1.0  (Phase 1 — Build & Test)                             ║
// ║                                                                              ║
// ║  PHASE ROADMAP                                                               ║
// ║  ─────────────────────────────────────────────────────────────────────────  ║
// ║  Phase 1 (this file) : Checkout → Verify → Build → Test → Archive          ║
// ║  Phase 2 (next)      : Docker image build & push to DockerHub/ECR           ║
// ║  Phase 3 (next)      : Docker Compose deploy to AWS EC2 via SSH             ║
// ║  Phase 4 (future)    : Kubernetes (EKS) deployment                          ║
// ║  Phase 5 (future)    : Full CD with blue-green / canary rollouts            ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

pipeline {

    // ──────────────────────────────────────────────────────────────────────────
    // AGENT DECLARATION
    // ──────────────────────────────────────────────────────────────────────────
    // 'agent any' → Run this pipeline on ANY available Jenkins node/agent.
    // For Phase 1 this is fine because we only need Java 21 + Maven, which are
    // already installed on your local Windows Jenkins instance.
    //
    // FUTURE UPGRADE (Phase 3, Linux EC2):
    //   agent { label 'ec2-linux' }        ← target a specific labelled agent
    //   — OR use a Docker agent —
    //   agent { docker { image 'maven:3.9.6-eclipse-temurin-21' } }
    // ──────────────────────────────────────────────────────────────────────────
    agent any

    // ──────────────────────────────────────────────────────────────────────────
    // ENVIRONMENT VARIABLES
    // ──────────────────────────────────────────────────────────────────────────
    // Centralise all tuneable values here.
    // Changing a value once automatically updates every stage that uses it.
    // ──────────────────────────────────────────────────────────────────────────
    environment {

        // Human-readable application name used in logs and future notifications.
        APP_NAME    = 'cricket-biomechanics-ai'

        // Must match the <version> tag in pom.xml exactly.
        APP_VERSION = '0.0.1-SNAPSHOT'

        // Derived final JAR filename:
        //   demobowling-analysis-backend-0.0.1-SNAPSHOT.jar
        JAR_NAME    = "demobowling-analysis-backend-${APP_VERSION}.jar"

        // ── Maven wrapper commands ────────────────────────────────────────────
        // Using the project-bundled mvnw wrapper guarantees the exact Maven
        // version the project was built with, regardless of what is globally
        // installed on the agent.
        //
        // WINDOWS : mvnw.cmd   (Windows batch file wrapper)
        // LINUX   : ./mvnw     (Shell script wrapper — Phase 3 change)
        MAVEN_CMD = 'mvnw.cmd'

        // Suppress AWT errors in headless CI environments (no display).
        MAVEN_OPTS = '-Djava.awt.headless=true'

        // ── Future variables (enable in Phase 2 & 3) ─────────────────────────
        // DOCKERHUB_USER  = 'your-dockerhub-username'
        // DOCKER_IMG_JAVA = "${DOCKERHUB_USER}/${APP_NAME}-java"
        // DOCKER_IMG_PY   = "${DOCKERHUB_USER}/${APP_NAME}-python"
        // DOCKER_TAG      = "${BUILD_NUMBER}"
        // EC2_HOST        = credentials('ec2-host')
        // EC2_USER        = 'ubuntu'
    }

    // ──────────────────────────────────────────────────────────────────────────
    // PIPELINE-WIDE OPTIONS
    // ──────────────────────────────────────────────────────────────────────────
    options {

        // Rotate logs & artefacts — keep only the last 10 builds.
        // Prevents unbounded disk growth on the Jenkins master.
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '10'))

        // Hard timeout for the entire pipeline.
        // If the build hangs (e.g., frozen test, stuck download) Jenkins kills
        // it automatically after 30 minutes.
        timeout(time: 30, unit: 'MINUTES')

        // Prepend every console line with a timestamp — essential for spotting
        // slow stages and correlating logs with external systems (CloudWatch, etc.)
        timestamps()

        // Prevent two builds of the same branch from running simultaneously.
        // Avoids race conditions on shared workspace directories.
        disableConcurrentBuilds()

       
    }

    // ──────────────────────────────────────────────────────────────────────────
    // STAGES
    // ──────────────────────────────────────────────────────────────────────────
    stages {

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 1 — CHECKOUT
        // ══════════════════════════════════════════════════════════════════════
        // WHY NEEDED:
        //   The Jenkins workspace is initially empty. This stage pulls the
        //   exact commit that triggered the build from GitHub into the workspace
        //   so that every subsequent stage can access the source code.
        //
        // HOW 'checkout scm' WORKS:
        //   'scm' is a Jenkins magic variable that refers to the SCM settings
        //   you configure in the Pipeline job's "Pipeline script from SCM"
        //   section (branch, repository URL, credentials, etc.).
        //   Jenkins automatically records the Git SHA, branch, and author in
        //   the build metadata — enabling full traceability.
        //
        // MULTI-BRANCH BENEFIT:
        //   In a MultiBranch Pipeline, Jenkins detects every branch and PR in
        //   GitHub automatically. 'checkout scm' always checks out the correct
        //   branch without any hardcoding.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 1 — Checkout Source Code') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 1 : Checking out source code from GitHub'
                echo '═══════════════════════════════════════════════════════'

                // Pull source from the SCM defined in the Jenkins job config.
                checkout scm

                // Print the checked-out commit for build traceability.
                // %% is how you escape % inside a Jenkins bat string.
                //
                // WINDOWS:
                bat 'git log -1 --format="Commit: %%H | Author: %%an | Date: %%ad | Msg: %%s"'

                // LINUX EC2 (replace the bat line above):
                // sh 'git log -1 --format="Commit: %H | Author: %an | Date: %ad | Msg: %s"'

                echo '✅  Checkout complete.'
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 2 — VERIFY ENVIRONMENT
        // ══════════════════════════════════════════════════════════════════════
        // WHY NEEDED:
        //   Jenkins can run on ANY agent. This stage fails FAST with a clear
        //   error message if Java 21 or Maven is missing — rather than letting
        //   it produce a cryptic compile error 10 minutes later.
        //
        //   It also prints version info into the console log, making it easy
        //   to reproduce a build exactly if something goes wrong weeks later.
        //
        // COMMON CATCH:
        //   If JAVA_HOME is not set on the agent, Maven will silently pick up
        //   a wrong JDK from the PATH. Printing JAVA_HOME here exposes that.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 2 — Verify Java & Maven') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 2 : Verifying Java 21 and Maven (mvnw)'
                echo '═══════════════════════════════════════════════════════'

                // WINDOWS bat commands:
                bat 'java -version'
                bat 'javac -version'
                bat "${MAVEN_CMD} --version"
                bat 'echo JAVA_HOME=%JAVA_HOME%'
                bat 'echo M2_HOME=%M2_HOME%'
                bat 'echo PATH=%PATH%'

                // LINUX EC2 equivalents (replace bat → sh):
                // sh 'java -version'
                // sh 'javac -version'
                // sh './mvnw --version'
                // sh 'echo "JAVA_HOME=$JAVA_HOME"'

                echo '✅  Environment verified: Java 21 + Maven ready.'
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 3 — CLEAN & BUILD (Maven package)
        // ══════════════════════════════════════════════════════════════════════
        // WHY NEEDED:
        //   This is the core compilation step. Maven cleans the previous build
        //   output, recompiles all Java sources, processes resources, and
        //   packages everything into a single executable fat-JAR.
        //
        // FLAG BREAKDOWN:
        //   clean        → Deletes target/ so stale .class files never
        //                  contaminate the new build. ALWAYS use in CI.
        //   package      → Runs: validate → compile → test-compile → package.
        //   -DskipTests  → Tests are intentionally skipped HERE because Stage 4
        //                  runs them separately with a proper JUnit report.
        //                  Skipping them here gives a fast compile-only check.
        //   -B           → Batch mode: removes interactive progress bars from
        //                  Maven output. Keeps the CI log clean and readable.
        //   -e           → Print full exception stack traces on failure.
        //                  Without this, Maven often prints a one-line summary
        //                  that hides the real cause.
        //
        // OUTPUT FILE:
        //   target/demobowling-analysis-backend-0.0.1-SNAPSHOT.jar  (~50-80 MB)
        //   This is the runnable Spring Boot fat-JAR.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 3 — Maven Clean & Build') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 3 : mvnw clean package -DskipTests'
                echo '═══════════════════════════════════════════════════════'

                // WINDOWS:
                bat "${MAVEN_CMD} clean package -DskipTests -B -e"

                // LINUX EC2:
                // sh "./mvnw clean package -DskipTests -B -e"

                // Verify the JAR file was actually produced.
                // 'if not exist ... exit 1' causes the stage to fail with a
                // meaningful message instead of a silent pass.
                bat "if not exist target\\${JAR_NAME} (echo ❌ JAR not found at target\\${JAR_NAME} && exit /b 1)"

                echo "✅  JAR built successfully: ${JAR_NAME}"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 4 — RUN TESTS
        // ══════════════════════════════════════════════════════════════════════
        // WHY NEEDED:
        //   Tests are the quality gate of every CI/CD pipeline. This stage:
        //     • Runs all JUnit tests in src/test/java/
        //     • Publishes test results to Jenkins' Test Results panel
        //     • Shows a trend chart across builds (pass/fail/skip history)
        //     • Marks the build UNSTABLE (yellow) if tests fail, rather than
        //       FAILURE — meaning the JAR is still archived for inspection.
        //
        // WHY SEPARATE FROM STAGE 3:
        //   • Independent timing visibility in the Stage View.
        //   • Tests can be skipped easily in emergencies by commenting out
        //     this single stage (never skip them in production!).
        //   • The 'post { always }' block ensures test reports are published
        //     even when the tests themselves fail.
        //
        // SUREFIRE REPORT:
        //   Maven Surefire plugin writes XML reports to target/surefire-reports/.
        //   Jenkins' junit() step reads these and builds the interactive report.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 4 — Run Tests') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo '  STAGE 4 : Running JUnit / Spring Boot tests'
                echo '═══════════════════════════════════════════════════════'

                // WINDOWS:
                bat "${MAVEN_CMD} test -B -e"

                // LINUX EC2:
                // sh "./mvnw test -B -e"
            }

            post {
                // 'always' guarantees the test report is published even if
                // some tests failed. Without this, a failed test would abort
                // the stage before the report is generated.
                always {
                    junit allowEmptyResults: true,
                          testResults: 'target/surefire-reports/*.xml'

                    echo '✅  Test report published to Jenkins Test Results tab.'
                }

                success {
                    echo '✅  All tests passed.'
                }

                failure {
                    echo '❌  One or more tests FAILED. Review the Test Results tab.'
                }
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // STAGE 5 — ARCHIVE JAR ARTEFACT
        // ══════════════════════════════════════════════════════════════════════
        // WHY NEEDED:
        //   Without archiving, the JAR only exists inside the temporary
        //   workspace directory and is deleted when the workspace is cleaned.
        //
        //   archiveArtifacts saves a copy inside Jenkins' own storage so it:
        //     • Can be downloaded from the Jenkins Build page by any team member.
        //     • Can be consumed by downstream Jenkins jobs (e.g., Docker build).
        //     • Provides a rollback artefact: if a new deployment breaks
        //       production you can re-deploy a previous known-good build's JAR.
        //
        // fingerprint: true
        //   Jenkins computes an MD5 hash of the JAR and records it.
        //   This creates a chain: build #N → JAR hash → downstream jobs.
        //   You can click the "fingerprint" in any build to see everywhere
        //   the same JAR was used.
        //
        // allowEmptyArchive: false
        //   Fail the pipeline if the JAR pattern matches nothing.
        //   Ensures you never silently archive an empty build.
        //
        // INDUSTRY NOTE:
        //   Production teams also push artefacts to Nexus / Artifactory / AWS S3
        //   here. We will add 'mvn deploy' in a later phase.
        // ══════════════════════════════════════════════════════════════════════
        stage('Stage 5 — Archive JAR Artefact') {
            steps {
                echo '═══════════════════════════════════════════════════════'
                echo "  STAGE 5 : Archiving ${JAR_NAME}"
                echo '═══════════════════════════════════════════════════════'

                archiveArtifacts artifacts: "target/${JAR_NAME}",
                                 fingerprint: true,
                                 allowEmptyArchive: false

                echo "✅  Artefact archived: ${JAR_NAME}"
                echo "    → Access: Jenkins → Build #${BUILD_NUMBER} → Artefacts"
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // ── PHASE 2 STUB: Docker Build & Push ─────────────────────────────────
        // Uncomment this entire stage when Phase 2 work begins.
        // ══════════════════════════════════════════════════════════════════════
        /*
        stage('Stage 6 — Build Docker Images') {
            steps {
                echo '  STAGE 6 : Building Java + Python Docker images'
                // Uses docker-compose.yml to build both services consistently.
                // LINUX: sh  'docker compose build --no-cache'
                // WINDOWS: bat 'docker compose build --no-cache'
            }
        }

        stage('Stage 7 — Push to DockerHub / ECR') {
            steps {
                echo '  STAGE 7 : Pushing images to container registry'
                // withCredentials([usernamePassword(
                //     credentialsId: 'dockerhub-creds',
                //     usernameVariable: 'DOCKER_USER',
                //     passwordVariable: 'DOCKER_PASS')]) {
                //   sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'
                //   sh "docker push ${DOCKER_IMG_JAVA}:${DOCKER_TAG}"
                //   sh "docker push ${DOCKER_IMG_PY}:${DOCKER_TAG}"
                // }
            }
        }
        */

        // ══════════════════════════════════════════════════════════════════════
        // ── PHASE 3 STUB: AWS EC2 Deployment ──────────────────────────────────
        // ══════════════════════════════════════════════════════════════════════
        /*
        stage('Stage 8 — Deploy to AWS EC2') {
            steps {
                echo '  STAGE 8 : SSH into EC2 and docker compose up'
                // sshagent(['ec2-ssh-key']) {
                //   sh """
                //     ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} '
                //       cd /home/ubuntu/cricket-ai &&
                //       docker compose pull &&
                //       docker compose up -d --remove-orphans
                //     '
                //   """
                // }
            }
        }

        stage('Stage 9 — Smoke Test') {
            steps {
                echo '  STAGE 9 : Verifying deployment health endpoint'
                // sh "curl -f http://${EC2_HOST}:9090/actuator/health || exit 1"
            }
        }
        */

        // ══════════════════════════════════════════════════════════════════════
        // ── PHASE 4 STUB: Kubernetes (EKS) ────────────────────────────────────
        // ══════════════════════════════════════════════════════════════════════
        /*
        stage('Stage 10 — Deploy to EKS') {
            steps {
                echo '  STAGE 10 : Rolling update on EKS cluster'
                // sh "kubectl set image deployment/cricket-backend cricket-backend=${DOCKER_IMG_JAVA}:${DOCKER_TAG} -n production"
                // sh "kubectl rollout status deployment/cricket-backend -n production"
            }
        }
        */

    } // ── end stages ──────────────────────────────────────────────────────────

    // ──────────────────────────────────────────────────────────────────────────
    // POST-PIPELINE ACTIONS
    // ──────────────────────────────────────────────────────────────────────────
    // These blocks run AFTER all stages, regardless of the pipeline's result.
    // Think of them as a finally{} block in Java — they always execute.
    // ──────────────────────────────────────────────────────────────────────────
    post {

        success {
            echo ''
            echo '╔════════════════════════════════════════════════════╗'
            echo '║  ✅  PIPELINE COMPLETED SUCCESSFULLY               ║'
            echo "║  App     : ${APP_NAME}                             ║"
            echo "║  Build   : #${BUILD_NUMBER}                        ║"
            echo "║  JAR     : ${JAR_NAME}                             ║"
            echo '╚════════════════════════════════════════════════════╝'

            // ── Phase 2: Uncomment to send Slack success notification ──────
            // slackSend channel: '#cricket-ai-ci',
            //             color: 'good',
            //             message: "✅ Build #${BUILD_NUMBER} passed — ${APP_NAME} (${BRANCH_NAME})\n${BUILD_URL}"
        }

        failure {
            echo ''
            echo '╔════════════════════════════════════════════════════╗'
            echo '║  ❌  PIPELINE FAILED                               ║'
            echo "║  Build   : #${BUILD_NUMBER}                        ║"
            echo '║  Check the Console Output for the root cause.      ║'
            echo '╚════════════════════════════════════════════════════╝'

            // ── Phase 2: Uncomment to send email/Slack failure alert ───────
            // emailext subject: "❌ Jenkins FAILED — ${APP_NAME} #${BUILD_NUMBER}",
            //          body: "Pipeline failed. See: ${BUILD_URL}console",
            //          to: 'your-email@example.com'
        }

        unstable {
            echo '⚠️   PIPELINE UNSTABLE — some tests failed.'
            echo '     Review the Test Results tab for failing test cases.'
        }

        aborted {
            echo '⏹️   PIPELINE ABORTED manually or by timeout.'
        }

        always {
            echo "─── Pipeline finished. Total duration: ${currentBuild.durationString} ───"

            // Clean the workspace after the build to free disk space.
            // Jenkins already stored the JAR via archiveArtifacts, so this
            // does NOT delete the saved artefact — only the local workspace copy.
            //
            // Comment out cleanWs() if you need to inspect workspace files
            // after a failed build for debugging purposes.
            cleanWs()
        }
    }

} // ── end pipeline ────────────────────────────────────────────────────────────
