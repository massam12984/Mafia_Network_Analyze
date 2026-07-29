pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timestamps()
    }

    environment {
        IMAGE_NAME    = 'mafia-network-analyzer'
        APP_CONTAINER = 'mafia-app'
        DB_CONTAINER  = 'mafia-mongo'
        APP_NETWORK   = 'mafia-network'
        DB_VOLUME     = 'mafia-mongo-data'
        APP_PORT      = '5000'
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
                echo 'Waiting for SonarQube Quality Gate...'

                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('5. Build Docker Image') {
            steps {
                echo 'Building the application image...'

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
                echo 'Creating the Docker network and MongoDB container...'

                sh '''
                    set -eu

                    docker network inspect "$APP_NETWORK" >/dev/null 2>&1 \
                        || docker network create "$APP_NETWORK"

                    docker volume inspect "$DB_VOLUME" >/dev/null 2>&1 \
                        || docker volume create "$DB_VOLUME"

                    docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 || true

                    docker pull mongo:7

                    docker run -d \
                        --name "$DB_CONTAINER" \
                        --network "$APP_NETWORK" \
                        --restart unless-stopped \
                        -v "$DB_VOLUME:/data/db" \
                        mongo:7

                    echo "Waiting for MongoDB..."

                    for attempt in $(seq 1 30); do
                        if docker exec "$DB_CONTAINER" \
                            mongosh --quiet \
                            --eval "db.adminCommand({ ping: 1 }).ok" \
                            2>/dev/null | grep -q 1; then

                            echo "MongoDB is ready."
                            exit 0
                        fi

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
                echo 'Deploying the Mafia Network Analyzer...'

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

                        docker network connect "$APP_NETWORK" jenkins \
                            >/dev/null 2>&1 || true
                    '''
                }
            }
        }

        stage('8. Verify Deployment') {
            steps {
                echo 'Checking the deployed application...'

                sh '''
                    for attempt in $(seq 1 30); do
                        STATUS=$(curl -s \
                            -o /dev/null \
                            -w "%{http_code}" \
                            "http://$APP_CONTAINER:5000/login" || true)

                        if [ "$STATUS" = "200" ]; then
                            echo "Application is working."
                            echo "HTTP status: $STATUS"
                            exit 0
                        fi

                        echo "Attempt $attempt: application is not ready."
                        sleep 2
                    done

                    echo "Application verification failed."
                    docker logs "$APP_CONTAINER" --tail 100
                    exit 1
                '''
            }
        }

        stage('9. Deployment Summary') {
            steps {
                sh '''
                    echo "Running application containers:"
                    docker ps \
                        --filter "name=$APP_CONTAINER" \
                        --filter "name=$DB_CONTAINER"

                    echo ""
                    echo "Application images:"
                    docker images "$IMAGE_NAME"
                '''
            }
        }
    }

    post {
        success {
            echo 'Pipeline completed successfully.'
            echo 'Mafia Network Analyzer has been deployed.'
        }

        failure {
            echo 'Pipeline failed. Open the first red stage and inspect its logs.'
        }

        always {
            cleanWs()
        }
    }
}
