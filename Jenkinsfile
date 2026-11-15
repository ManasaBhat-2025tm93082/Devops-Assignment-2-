// ACEest Fitness & Gym - CI/CD pipeline (Linux Jenkins agent)
pipeline {
    agent any

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    // Poll GitHub every ~2 minutes and build when there is a new commit
    triggers { pollSCM('H/2 * * * *') }

    parameters {
        string(name: 'REGISTRY', defaultValue: 'localhost:5001', description: 'Image registry prefix')
        booleanParam(name: 'RUN_SONAR', defaultValue: true, description: 'Run SonarQube analysis + quality gate')
        booleanParam(name: 'PUSH_IMAGE', defaultValue: false, description: 'Push images to the registry')
        booleanParam(name: 'DEPLOY', defaultValue: false, description: 'Deploy to Kubernetes (Minikube)')
        choice(name: 'STRATEGY', choices: ['rolling-update', 'blue-green', 'canary', 'ab-testing', 'shadow'],
               description: 'Deployment strategy used when DEPLOY is ticked')
    }

    environment {
        DOCKERHUB_USER = "${params.REGISTRY}"
        IMAGE          = "${params.REGISTRY}/aceest-fitness"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script { env.APP_VERSION = readFile('VERSION').trim() }
                echo "Building ACEest version ${env.APP_VERSION}"
            }
        }

        stage('Clean Build Environment') {
            steps {
                sh '''
                    rm -rf venv
                    python3 -m venv venv
                    . venv/bin/activate
                    python -m pip install --upgrade pip
                    python -m pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Compile Check') {
            steps { sh '. venv/bin/activate && python -m py_compile app.py' }
        }

        stage('Lint') {
            steps { sh '. venv/bin/activate && python -m flake8 .' }
        }

        stage('Unit Tests') {
            steps {
                sh '. venv/bin/activate && python -m pytest -v --cov=app --cov-report=xml --junitxml=pytest-report.xml'
            }
            post { always { junit allowEmptyResults: true, testResults: 'pytest-report.xml' } }
        }

        stage('SonarQube Analysis & Quality Gate') {
            when { expression { params.RUN_SONAR } }
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        V=7.2.0.5079
                        D="$HOME/.sonar-scanner-cli/sonar-scanner-$V-linux-x64"
                        if [ ! -x "$D/bin/sonar-scanner" ]; then
                            mkdir -p "$HOME/.sonar-scanner-cli"
                            curl -fsSLo /tmp/sonar-scanner.zip "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-$V-linux-x64.zip"
                            (command -v unzip > /dev/null && unzip -q -o /tmp/sonar-scanner.zip -d "$HOME/.sonar-scanner-cli") \\
                                || python3 -m zipfile -e /tmp/sonar-scanner.zip "$HOME/.sonar-scanner-cli"
                            chmod -R u+x "$D/bin" "$D/jre/bin" 2>/dev/null || true
                        fi
                        # qualitygate.wait makes the scanner poll SonarQube Cloud and fail this stage if the gate fails
                        "$D/bin/sonar-scanner" -Dsonar.projectVersion=${APP_VERSION} -Dsonar.qualitygate.wait=true
                    '''
                }
            }
        }

        stage('Package Build Artifact') {
            steps {
                sh 'tar czf aceest-fitness-${APP_VERSION}-build${BUILD_NUMBER}.tar.gz app.py templates requirements.txt VERSION'
                archiveArtifacts artifacts: '*.tar.gz, coverage.xml, pytest-report.xml', allowEmptyArchive: true
            }
        }

        stage('Docker Build & Test') {
            when { expression { sh(script: 'docker info > /dev/null 2>&1', returnStatus: true) == 0 } }
            steps {
                sh '''
                    docker build --target base --build-arg APP_VERSION=${APP_VERSION} \\
                        -t ${IMAGE}:${APP_VERSION} -t ${IMAGE}:build-${BUILD_NUMBER} .
                    docker build --target test -t aceest-fitness:test .
                    docker run --rm aceest-fitness:test
                '''
            }
        }

        stage('Push Image') {
            when {
                allOf {
                    expression { params.PUSH_IMAGE }
                    expression { sh(script: 'docker info > /dev/null 2>&1', returnStatus: true) == 0 }
                }
            }
            steps {
                script {
                    if (params.REGISTRY.startsWith('localhost')) {
                        sh 'docker push ${IMAGE}:${APP_VERSION} && docker push ${IMAGE}:build-${BUILD_NUMBER}'
                    } else {
                        withCredentials([usernamePassword(credentialsId: 'dockerhub-creds',
                                                          usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
                            sh '''
                                echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                                docker push ${IMAGE}:${APP_VERSION}
                                docker push ${IMAGE}:build-${BUILD_NUMBER}
                                docker logout
                            '''
                        }
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when { expression { params.DEPLOY } }
            steps {
                script { env.DEPLOY_STARTED = 'true' }
                sh '''
                    chmod +x scripts/*.sh
                    minikube image load ${IMAGE}:${APP_VERSION}
                    scripts/deploy.sh ${STRATEGY}
                '''
                script {
                    if (params.STRATEGY == 'rolling-update') {
                        sh '''
                            kubectl set image deployment/aceest-rolling aceest=${IMAGE}:${APP_VERSION}
                            kubectl rollout status deployment/aceest-rolling --timeout=120s
                        '''
                    }
                }
            }
        }

        stage('Post-deploy Smoke Test') {
            when {
                allOf {
                    expression { params.DEPLOY }
                    expression { params.STRATEGY in ['rolling-update', 'blue-green', 'canary'] }
                }
            }
            steps {
                sh '''
                    case "${STRATEGY}" in
                        rolling-update) PORT=30081 ;;
                        blue-green)     PORT=30082 ;;
                        canary)         PORT=30083 ;;
                    esac
                    IP=$(minikube ip)
                    for i in 1 2 3 4 5 6; do
                        curl -fsS http://$IP:$PORT/health && break || sleep 5
                    done
                    echo; curl -fsS http://$IP:$PORT/version; echo
                '''
            }
        }
    }

    post {
        failure {
            script {
                // Automatic rollback to the last stable ReplicaSet if a rolling deployment fails
                if (env.DEPLOY_STARTED == 'true' && params.STRATEGY == 'rolling-update') {
                    sh 'kubectl rollout undo deployment/aceest-rolling'
                    echo 'Deployment failed - rolled back to the previous stable version'
                }
            }
            echo 'BUILD FAILED'
        }
        success { echo 'BUILD SUCCESSFUL' }
    }
}