pipeline {
    agent any

    // These environment variables are available to all stages
    environment {
        // Docker Hub image name — replace YOUR_DOCKERHUB_USERNAME
        APP_IMAGE     = "yrathod30/market-regime-app"
        TRAINER_IMAGE = "yrathod30/market-regime-trainer"

        // Git repo URLs
        APP_REPO      = "https://github.com/Yash-Rathod/market-regime-detector.git"
        GITOPS_REPO   = "https://github.com/Yash-Rathod/market-regime-k8s.git"

        // Image tag — use the short git commit SHA for traceability
        // Every image pushed is tagged with the exact commit that built it
        IMAGE_TAG     = "${env.GIT_COMMIT?.take(7) ?: 'latest'}"
    }

    options {
        // Keep only the last 10 builds to save disk space
        buildDiscarder(logRotator(numToKeepStr: "10"))

        // Fail the build if it runs longer than 30 minutes
        timeout(time: 30, unit: "MINUTES")

        // Don't run concurrent builds on the same branch
        disableConcurrentBuilds()
    }

    stages {

        // ── Stage 1: Checkout ───────────────────────────────────────────────
        stage("Checkout") {
            steps {
                checkout scm
                script {
                    // Print build context for debugging
                    sh "echo 'Branch: ${env.BRANCH_NAME ?: \"unknown\"}'"
                    sh "echo 'Commit: ${env.GIT_COMMIT?.take(7) ?: \"unknown\"}'"
                    sh "echo 'Build:  ${env.BUILD_NUMBER}'"
                }
            }
        }

        // ── Stage 2: Test ───────────────────────────────────────────────────
        stage("Test") {
            steps {
                script {
                    // Run tests inside a Python container so Jenkins doesn't
                    // need Python installed — the container provides it
                    docker.image("python:3.11-slim").inside(
                        "--user root -v ${env.WORKSPACE}:/app -w /app"
                    ) {
                        sh """
                            pip install --quiet --no-cache-dir \
                                fastapi uvicorn pydantic \
                                prometheus-client python-dotenv \
                                pytest httpx sqlalchemy psycopg2-binary \
                                scikit-learn numpy pandas
                            PYTHONPATH=/app pytest tests/ -v \
                                --tb=short \
                                --junit-xml=test-results.xml
                        """
                    }
                }
            }
            post {
                always {
                    // Publish test results in Jenkins UI regardless of pass/fail
                    junit allowEmptyResults: true,
                          testResults: "test-results.xml"
                }
            }
        }

        // ── Stage 3: Build images ───────────────────────────────────────────
        stage("Build") {
            steps {
                script {
                    docker.withRegistry("https://index.docker.io/v1/",
                                        "dockerhub-credentials") {

                        // Build app image — tagged with commit SHA and 'latest'
                        def appImage = docker.build(
                            "${APP_IMAGE}:${IMAGE_TAG}",
                            "-f docker/Dockerfile.app ."
                        )
                        // Also tag as latest for convenience
                        appImage.tag("latest")

                        // Build trainer image
                        def trainerImage = docker.build(
                            "${TRAINER_IMAGE}:${IMAGE_TAG}",
                            "-f docker/Dockerfile.trainer ."
                        )
                        trainerImage.tag("latest")

                        // Store images in script scope for next stage
                        env.APP_IMAGE_FULL     = "${APP_IMAGE}:${IMAGE_TAG}"
                        env.TRAINER_IMAGE_FULL = "${TRAINER_IMAGE}:${IMAGE_TAG}"
                    }
                }
            }
        }

        // ── Stage 4: Push images ────────────────────────────────────────────
        stage("Push") {
            // Only push images from the main branch
            // Feature branches build and test but don't push
            when {
                branch "main"
            }
            steps {
                script {
                    docker.withRegistry("https://index.docker.io/v1/",
                                        "dockerhub-credentials") {

                        docker.image("${APP_IMAGE}:${IMAGE_TAG}").push()
                        docker.image("${APP_IMAGE}:latest").push()

                        docker.image("${TRAINER_IMAGE}:${IMAGE_TAG}").push()
                        docker.image("${TRAINER_IMAGE}:latest").push()

                        echo "Pushed images:"
                        echo "  ${APP_IMAGE}:${IMAGE_TAG}"
                        echo "  ${TRAINER_IMAGE}:${IMAGE_TAG}"
                    }
                }
            }
        }

        // ── Stage 5: Update GitOps manifest ─────────────────────────────────
        stage("Update Manifest") {
            // Only update the k8s manifest repo after a successful push
            when {
                branch "main"
            }
            steps {
                script {
                    withCredentials([string(credentialsId: "github-token",
                                           variable: "GH_TOKEN")]) {
                        sh """
                            # Configure git identity for this automated commit
                            git config --global user.email "jenkins@ci.local"
                            git config --global user.name  "Jenkins CI"

                            # Clone the GitOps manifests repo
                            rm -rf gitops-repo
                            git clone https://${GH_TOKEN}@github.com/Yash-Rathod/market-regime-k8s.git gitops-repo

                            cd gitops-repo

                            # Update the image tag in the deployment manifest
                            # sed finds the line with the image name and replaces the tag
                            sed -i 's|${APP_IMAGE}:.*|${APP_IMAGE}:${IMAGE_TAG}|g' \
                                k8s/app-deployment.yaml

                            # Check if anything actually changed
                            if git diff --quiet; then
                                echo "No manifest changes — image tag already up to date"
                                exit 0
                            fi

                            # Commit and push the tag update
                            git add k8s/app-deployment.yaml
                            git commit -m "ci: update app image to ${IMAGE_TAG} [skip ci]"
                            git push origin main

                            echo "Manifest updated to tag: ${IMAGE_TAG}"
                        """
                    }
                }
            }
        }
    }

    // ── Post-pipeline actions ────────────────────────────────────────────────
    post {
        success {
            echo """
            ============================================
            BUILD SUCCEEDED
            Image : ${env.APP_IMAGE}:${env.IMAGE_TAG}
            Commit: ${env.GIT_COMMIT?.take(7)}
            ============================================
            """
        }
        failure {
            echo """
            ============================================
            BUILD FAILED at stage: check logs above
            Branch: ${env.BRANCH_NAME}
            Commit: ${env.GIT_COMMIT?.take(7)}
            ============================================
            """
        }
        cleanup {
            // Always clean up dangling Docker images after build
            // This prevents disk exhaustion on the Jenkins host
            sh "docker image prune -f || true"
        }
    }
}