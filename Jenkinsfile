// ACEest Fitness & Gym - CI/CD pipeline (Linux Jenkins agent)
// Stages: checkout -> build env -> compile -> lint -> pytest(+coverage) -> SonarQube + quality gate
//         -> package artifact -> Docker build/test -> push to Docker Hub -> deploy to Kubernetes.
// Docker / Kubernetes stages are skipped automatically if the agent cannot use them.
pipeline {
    agent any

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    // Poll GitHub every ~2 minutes and build when there is a new commit
    triggers { pollSCM('H/2 * * * *') }

    parameters {
        booleanParam(name: 'RUN_SONAR', defaultValue: true, description: 'Run SonarQube analysis + quality gate')
        booleanParam(name: 'PUSH_IMAGE', defaultValue: true, description: 'Push image to Docker Hub')
        booleanParam(name: 'DEPLOY', defaultValue: false, description: 'Deploy to Kubernetes')
        choice(name: 'STRATEGY', choices: ['rolling-update', 'blue-green', 'canary', 'ab-testing', 'shadow'],
               description: 'Deployment strategy used when DEPLOY is ticked')
    }

    environment {
        DOCKERHUB_USER = 'YOUR_DOCKERHUB_USERNAME'      // <-- change this
        IMAGE          = "${DOCKERHUB_USER}/aceest-fitness"
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

        stage('SonarQube Analysis') {
            when { expression { params.RUN_SONAR } }
            steps {
                script { env.SCANNER_HOME = tool 'SonarScanner' }
                withSonarQubeEnv('SonarQube') {
                    sh '${SCANNER_HOME}/bin/sonar-scanner -Dsonar.projectVersion=${APP_VERSION}'
                }
            }
        }

        stage('Quality Gate') {
            when { expression { params.RUN_SONAR } }
            steps {
                timeout(time: 5, unit: 'MINUTES') { waitForQualityGate abortPipeline: true }
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
                    docker build --target base --build-arg APP_VERSION=${APP_VERSION} \
                        -t ${IMAGE}:${APP_VERSION} -t ${IMAGE}:build-${BUILD_NUMBER} -t ${IMAGE}:latest .
                    docker build --target test -t aceest-fitness:test .
                    docker run --rm aceest-fitness:test
                '''
            }
        }

        stage('Push to Docker Hub') {
            when {
                allOf {
                    expression { params.PUSH_IMAGE }
                    expression { sh(script: 'docker info > /dev/null 2>&1', returnStatus: true) == 0 }
                }
            }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-creds',
                                                  usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
                    sh '''
                        echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                        docker push ${IMAGE}:${APP_VERSION}
                        docker push ${IMAGE}:build-${BUILD_NUMBER}
                        docker push ${IMAGE}:latest
                        docker logout
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when { expression { params.DEPLOY } }
            steps {
                withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
                    script { env.DEPLOY_STARTED = 'true' }
                    sh 'scripts/deploy.sh ${STRATEGY}'
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
        }
    }

    post {
        failure {
            script {
                // Automatic rollback to the last stable ReplicaSet if a rolling deployment fails
                if (env.DEPLOY_STARTED == 'true' && params.STRATEGY == 'rolling-update') {
                    withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
                        sh 'kubectl rollout undo deployment/aceest-rolling'
                    }
                    echo 'Deployment failed - rolled back to the previous stable version'
                }
            }
            echo 'BUILD FAILED'
        }
        success { echo 'BUILD SUCCESSFUL' }
    }
}
