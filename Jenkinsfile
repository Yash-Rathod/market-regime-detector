pipeline {
    agent any

    environment {
        APP_IMAGE     = "yrathod30/market-regime-app"
        TRAINER_IMAGE = "yrathod30/market-regime-trainer"
        APP_REPO      = "https://github.com/Yash-Rathod/market-regime-detector.git"
        GITOPS_REPO   = "https://github.com/Yash-Rathod/market-regime-k8s.git"
        // IMAGE_TAG is set in the Checkout stage after GIT_COMMIT is populated
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: "10"))
        timeout(time: 30, unit: "MINUTES")
        disableConcurrentBuilds()
    }

    stages {

        // ── Stage 1: Checkout ───────────────────────────────────────────────
        stage("Checkout") {
            steps {
                checkout scm
                script {
                    // GIT_COMMIT is now available after checkout
                    env.IMAGE_TAG = env.GIT_COMMIT?.take(7) ?: 'latest'
                    echo "Branch: ${env.BRANCH_NAME ?: 'unknown'}"
                    echo "Commit: ${env.IMAGE_TAG}"
                    echo "Build:  ${env.BUILD_NUMBER}"
                }
            }
        }

        // ── Stage 2: Test ───────────────────────────────────────────────────
        stage("Test") {
            steps {
                script {
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

                        def appImage = docker.build(
                            "${APP_IMAGE}:${env.IMAGE_TAG}",
                            "-f docker/Dockerfile.app ."
                        )
                        appImage.tag("latest")

                        def trainerImage = docker.build(
                            "${TRAINER_IMAGE}:${env.IMAGE_TAG}",
                            "-f docker/Dockerfile.trainer ."
                        )
                        trainerImage.tag("latest")

                        env.APP_IMAGE_FULL     = "${APP_IMAGE}:${env.IMAGE_TAG}"
                        env.TRAINER_IMAGE_FULL = "${TRAINER_IMAGE}:${env.IMAGE_TAG}"
                    }
                }
            }
        }

        // ── Stage 4: Push images ────────────────────────────────────────────
        stage("Push") {
            // Only push from the main branch
            when {
                expression { env.BRANCH_NAME == 'main' }
            }
            steps {
                script {
                    docker.withRegistry("https://index.docker.io/v1/",
                                        "dockerhub-credentials") {

                        docker.image("${APP_IMAGE}:${env.IMAGE_TAG}").push()
                        docker.image("${APP_IMAGE}:latest").push()

                        docker.image("${TRAINER_IMAGE}:${env.IMAGE_TAG}").push()
                        docker.image("${TRAINER_IMAGE}:latest").push()

                        echo "Pushed: ${APP_IMAGE}:${env.IMAGE_TAG}"
                        echo "Pushed: ${TRAINER_IMAGE}:${env.IMAGE_TAG}"
                    }
                }
            }
        }

        // ── Stage 5: Update GitOps manifest ─────────────────────────────────
        stage("Update Manifest") {
            when {
                expression { env.BRANCH_NAME == 'main' }
            }
            steps {
                script {
                    withCredentials([string(credentialsId: "github-token",
                                           variable: "GH_TOKEN")]) {
                        sh """
                            git config --global user.email "jenkins@ci.local"
                            git config --global user.name  "Jenkins CI"

                            rm -rf gitops-repo
                            git clone https://${GH_TOKEN}@github.com/Yash-Rathod/market-regime-k8s.git gitops-repo

                            cd gitops-repo

                            sed -i 's|${APP_IMAGE}:.*|${APP_IMAGE}:${IMAGE_TAG}|g' \
                                k8s/app-deployment.yaml

                            if git diff --quiet; then
                                echo "No manifest changes — image tag already up to date"
                                exit 0
                            fi

                            git add k8s/app-deployment.yaml
                            git commit -m "ci: update app image to ${env.IMAGE_TAG} [skip ci]"
                            git push origin main

                            echo "Manifest updated to tag: ${env.IMAGE_TAG}"
                        """
                    }
                }
            }
        }
    }

    // ── Post-pipeline actions ────────────────────────────────────────────────
    post {
        success {
            echo "BUILD SUCCEEDED — Image: ${env.APP_IMAGE_FULL} — Commit: ${env.IMAGE_TAG}"
        }
        failure {
            echo "BUILD FAILED — Branch: ${env.BRANCH_NAME ?: 'unknown'} — Commit: ${env.IMAGE_TAG ?: 'unknown'}"
        }
        cleanup {
            sh "docker image prune -f || true"
        }
    }
}
