pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
    }
    environment {
        IMAGE_NAME      = 'mafia-network-analyzer'
        APP_CONTAINER   = 'mafia-app'
        DB_CONTAINER    = 'mafia-mongo'
        APP_NETWORK     = 'mafia-network'
        DB_VOLUME       = 'mafia-mongo-data'
        APP_PORT        = '5000'

        ZAP_IMAGE       = 'ghcr.io/zaproxy/zaproxy:stable'
        ZAP_REPORT_DIR  = 'zap-reports'
    }

    stages {

        stage('1. Checkout') {
            steps {
                echo 'Downloading the project from GitHub...'

                checkout scm

                sh '''
                    echo "Repository files:"
                    ls -la

                    test -f app.py
                    test -f requirements.txt
                    test -f Dockerfile
                    test -f sonar-project.properties
                    test -f Jenkinsfile

                    echo "Required project files are available."
                '''
            }
        }

        stage('2. Validate Python') {
            steps {
                echo 'Checking Python syntax...'

                sh '''
                    python3 --version
                    python3 -m py_compile app.py
                    echo "Python syntax is valid."
                '''
            }
        }

        stage('3. SonarQube Analysis') {
            steps {
                echo 'Sending the source code to SonarQube...'

                script {
                    def scannerHome = tool 'SonarScanner'

                    withSonarQubeEnv('SonarQube') {
                        sh "${scannerHome}/bin/sonar-scanner"
                    }
                }
            }
        }

        stage('4. Quality Gate') {
            steps {
                echo 'Waiting for the SonarQube Quality Gate result...'

                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('5. Build Docker Image') {
            steps {
                echo 'Building the Mafia Network Analyzer Docker image...'

                sh '''
                    docker build --pull \
                        -t "$IMAGE_NAME:$BUILD_NUMBER" \
                        -t "$IMAGE_NAME:latest" \
                        .
                '''
            }
        }

        stage('6. Deploy MongoDB') {
            steps {
                echo 'Creating the Docker network, volume and MongoDB container...'

                sh '''
                    set -eu

                    docker network inspect "$APP_NETWORK" \
                        >/dev/null 2>&1 \
                        || docker network create "$APP_NETWORK"

                    docker volume inspect "$DB_VOLUME" \
                        >/dev/null 2>&1 \
                        || docker volume create "$DB_VOLUME"

                    docker rm -f "$DB_CONTAINER" \
                        >/dev/null 2>&1 || true

                    docker pull mongo:7

                    docker run -d \
                        --name "$DB_CONTAINER" \
                        --network "$APP_NETWORK" \
                        --restart unless-stopped \
                        -v "$DB_VOLUME:/data/db" \
                        mongo:7

                    echo "Waiting for MongoDB to become ready..."

                    for attempt in $(seq 1 30); do
                        if docker exec "$DB_CONTAINER" \
                            mongosh --quiet \
                            --eval "db.adminCommand({ ping: 1 }).ok" \
                            2>/dev/null | grep -q 1; then

                            echo "MongoDB is ready."
                            exit 0
                        fi

                        echo "MongoDB check attempt: $attempt"
                        sleep 2
                    done

                    echo "MongoDB failed to start."

                    docker logs "$DB_CONTAINER" --tail 100

                    exit 1
                '''
            }
        }

        stage('7. Deploy Application') {
            steps {
                echo 'Deploying the Mafia Network Analyzer application...'

                withCredentials([
                    string(
                        credentialsId: 'mafia-secret-key',
                        variable: 'APP_SECRET_KEY'
                    )
                ]) {
                    sh '''
                        set -eu

                        docker rm -f "$APP_CONTAINER" \
                            >/dev/null 2>&1 || true

                        docker run -d \
                            --name "$APP_CONTAINER" \
                            --network "$APP_NETWORK" \
                            --restart unless-stopped \
                            -p "$APP_PORT:5000" \
                            -e "MONGO_URI=mongodb://$DB_CONTAINER:27017/" \
                            -e "SECRET_KEY=$APP_SECRET_KEY" \
                            "$IMAGE_NAME:$BUILD_NUMBER"

                        # Jenkins needs this network connection to verify
                        # the application by its container name.
                        docker network connect "$APP_NETWORK" jenkins \
                            >/dev/null 2>&1 || true

                        echo "Application container has been created."
                    '''
                }
            }
        }

        stage('8. Verify Deployment') {
            steps {
                echo 'Checking whether the deployed application is responding...'

                sh '''
                    set -u

                    for attempt in $(seq 1 30); do
                        STATUS=$(curl -s \
                            -o /dev/null \
                            -w "%{http_code}" \
                            "http://$APP_CONTAINER:5000/login" || true)

                        if [ "$STATUS" = "200" ] || \
                           [ "$STATUS" = "301" ] || \
                           [ "$STATUS" = "302" ]; then

                            echo "Application is working."
                            echo "HTTP status: $STATUS"
                            exit 0
                        fi

                        echo "Attempt $attempt: application is not ready."
                        echo "Current HTTP status: $STATUS"

                        sleep 2
                    done

                    echo "Application verification failed."

                    docker logs "$APP_CONTAINER" --tail 100

                    exit 1
                '''
            }
        }

       stage('9. OWASP ZAP DAST') {
    steps {
        echo 'Running OWASP ZAP against the deployed application...'

        sh '''
            set -u

            ZAP_CONTAINER="zap-scan-$BUILD_NUMBER"
            ZAP_VOLUME="zap-work-$BUILD_NUMBER"
            TARGET_URL="http://$APP_CONTAINER:5000/login"

            echo "Preparing OWASP ZAP scan..."

            rm -rf "$ZAP_REPORT_DIR"
            mkdir -p "$ZAP_REPORT_DIR"

            # Remove resources from an earlier failed build.
            docker rm -f "$ZAP_CONTAINER" \
                >/dev/null 2>&1 || true

            docker volume rm "$ZAP_VOLUME" \
                >/dev/null 2>&1 || true

            cleanup_zap() {
                echo "Cleaning temporary ZAP resources..."

                docker rm -f "$ZAP_CONTAINER" \
                    >/dev/null 2>&1 || true

                docker volume rm "$ZAP_VOLUME" \
                    >/dev/null 2>&1 || true
            }

            trap cleanup_zap EXIT

            echo "Pulling the official OWASP ZAP image..."

            docker pull "$ZAP_IMAGE"

            echo "Testing whether ZAP can access the application..."

            docker run --rm \
                --network "$APP_NETWORK" \
                "$ZAP_IMAGE" \
                curl -fsS "$TARGET_URL" \
                >/dev/null

            echo "ZAP can access the deployed application."

            echo "Creating a temporary volume for ZAP reports..."

            docker volume create "$ZAP_VOLUME" \
                >/dev/null

            # Give the ZAP user permission to create reports.
            docker run --rm \
                --user root \
                --volume "$ZAP_VOLUME:/zap/wrk" \
                --entrypoint sh \
                "$ZAP_IMAGE" \
                -c 'chmod 777 /zap/wrk'

            echo "Starting OWASP ZAP baseline security scan..."
            echo "Target URL: $TARGET_URL"

            set +e

            docker run \
                --name "$ZAP_CONTAINER" \
                --network "$APP_NETWORK" \
                --volume "$ZAP_VOLUME:/zap/wrk:rw" \
                "$ZAP_IMAGE" \
                zap-baseline.py \
                -t "$TARGET_URL" \
                -m 1 \
                -T 10 \
                -r zap-report.html \
                -J zap-report.json \
                -x zap-report.xml \
                -I

            ZAP_EXIT_CODE=$?

            set -e

            echo "$ZAP_EXIT_CODE" \
                > "$ZAP_REPORT_DIR/zap-exit-code.txt"

            echo "ZAP exit code: $ZAP_EXIT_CODE"
            echo "Copying reports into the Jenkins workspace..."

            COPY_FAILED=0

            for REPORT_FILE in \
                zap-report.html \
                zap-report.json \
                zap-report.xml
            do
                if docker cp \
                    "$ZAP_CONTAINER:/zap/wrk/$REPORT_FILE" \
                    "$ZAP_REPORT_DIR/$REPORT_FILE"
                then
                    echo "Copied: $REPORT_FILE"
                else
                    echo "Failed to copy: $REPORT_FILE"
                    COPY_FAILED=1
                fi
            done

            echo ""
            echo "Generated OWASP ZAP files:"

            ls -lh "$ZAP_REPORT_DIR"

            if [ "$COPY_FAILED" -ne 0 ]; then
                echo "One or more ZAP reports were not generated."
                exit 1
            fi

            if [ ! -s "$ZAP_REPORT_DIR/zap-report.html" ]; then
                echo "The HTML security report is missing or empty."
                exit 1
            fi

            echo "OWASP ZAP scan and report generation completed."

            # Stage 10 will evaluate the recorded exit code
            # after archiving the reports.
            exit 0
        '''
    }
}

        stage('10. Archive ZAP Reports') {
            steps {
                echo 'Saving the OWASP ZAP reports as Jenkins build artifacts...'

                archiveArtifacts(
                    artifacts: 'zap-reports/*',
                    fingerprint: true,
                    allowEmptyArchive: false
                )

                script {
                    def zapExitCode = readFile(
                        'zap-reports/zap-exit-code.txt'
                    ).trim()

                    echo "Recorded OWASP ZAP exit code: ${zapExitCode}"

                    if (zapExitCode == '0') {
                        echo 'OWASP ZAP scan completed successfully.'
                    }
                    else if (zapExitCode == '1') {
                        unstable(
                            'OWASP ZAP found one or more alerts configured as FAIL. Review zap-report.html.'
                        )
                    }
                    else if (zapExitCode == '2') {
                        echo 'OWASP ZAP found warnings. Review zap-report.html.'
                    }
                    else {
                        error(
                            "OWASP ZAP could not complete the scan. Exit code: ${zapExitCode}"
                        )
                    }
                }
            }
        }

        stage('11. Deployment Summary') {
            steps {
                sh '''
                    echo "========================================"
                    echo "Running application containers"
                    echo "========================================"

                    docker ps \
                        --filter "name=$APP_CONTAINER" \
                        --filter "name=$DB_CONTAINER"

                    echo ""
                    echo "========================================"
                    echo "Application Docker images"
                    echo "========================================"

                    docker images "$IMAGE_NAME"

                    echo ""
                    echo "========================================"
                    echo "OWASP ZAP Docker image"
                    echo "========================================"

                    docker images "$ZAP_IMAGE"

                    echo ""
                    echo "========================================"
                    echo "OWASP ZAP security reports"
                    echo "========================================"

                    ls -lh "$ZAP_REPORT_DIR"

                    echo ""
                    echo "Application URL:"
                    echo "http://SERVER-IP:$APP_PORT"
                '''
            }
        }
    }

    post {
        success {
            echo 'Pipeline completed successfully.'
            echo 'SonarQube Quality Gate passed.'
            echo 'Mafia Network Analyzer has been deployed.'
            echo 'OWASP ZAP dynamic security scan has been completed.'
            echo 'The ZAP reports are available in Jenkins build artifacts.'
        }

        unstable {
            echo 'The application was deployed, but OWASP ZAP reported security findings.'
            echo 'Open the Jenkins build artifacts and review zap-report.html.'
        }

        failure {
            echo 'Pipeline failed.'
            echo 'Open the first red stage and inspect its logs.'
        }

        always {
            echo 'Cleaning the Jenkins workspace...'
            cleanWs()
        }
    }
}
