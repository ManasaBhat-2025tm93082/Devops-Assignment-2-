# ACEest Fitness & Gym - DevOps Assignment 2

This repository contains a Flask fitness and gym management application and
the configuration for a CI/CD workflow using GitHub Actions, Jenkins, Pytest,
SonarQube, Docker, Docker Hub, and Kubernetes. The Kubernetes examples cover
rolling update, blue-green, canary, A/B, and shadow deployments.

Repository: https://github.com/ManasaBhat-2025tm93082/Devops-Assignment-2-

> The repository provides the application and pipeline configuration. Running
> Jenkins, publishing to Docker Hub, and deploying to Kubernetes require your
> own account credentials and a configured machine or cluster.

---

## 1. Architecture

```
 Developer -> git push -> GitHub  --(poll SCM every 2 min)-->  Jenkins
                            |                                     |
                     GitHub Actions                 Checkout -> venv -> compile -> flake8
                  (lint, docker build,              -> pytest + coverage -> SonarQube + Quality Gate
                   pytest in container)             -> package artifact -> docker build/test
                                                    -> push image to Docker Hub (1.0.0, build-N, latest)
                                                    -> deploy to Kubernetes (chosen strategy)
                                                    -> automatic rollback for failed rolling updates
                                                                   |
                                          Minikube: rolling | blue-green | canary | A/B | shadow
```
Jenkins automatically rolls back failed rolling updates. Blue-green and canary
rollback are shown as explicit script commands in section 9.

## 2. Project Structure

```
app.py                    Flask app (app factory, routes, business logic, /version endpoint)
templates/index.html      Web UI (shows the running version)
tests/test_app.py         Pytest suite
VERSION                   Application version used for image tags and artifacts
Dockerfile                Multi-stage: base (runtime) and test (pytest) - build arg APP_VERSION
Jenkinsfile               Jenkins pipeline (Linux agent)
sonar-project.properties  SonarQube configuration
k8s/                      Kubernetes manifests, one file per deployment strategy
scripts/                  deploy.sh, switch-blue-green.sh, rollback.sh
.github/workflows/main.yml  GitHub Actions CI (build, lint, docker build, tests in container)
legacy_versions/          Original ACEest versions 1.0 - 3.2.4
```

## 3. Run the application locally

From the repository root, create a virtual environment and install the
development requirements:

Linux/macOS:
```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt
python app.py
```

Windows PowerShell:
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python app.py
```

Open http://localhost:5000. To display a different version in the UI and
`/version` response, set `APP_VERSION` before starting the app (for example,
`APP_VERSION=2.0.0 python app.py` on Linux/macOS, or
`$env:APP_VERSION="2.0.0"; python app.py` in PowerShell).

## 4. Tests and Code Quality

```bash
python -m pytest -v --cov=app --cov-report=term-missing --cov-report=xml
python -m flake8 .
```
The coverage command writes `coverage.xml`, which is read by the SonarQube
configuration.

## 5. Docker and Docker Hub

To publish images, replace `<your-dockerhub-username>` with your Docker Hub
username. These commands tag the current checkout with each version; if the
versions must contain different application code, check out the corresponding
source revision before building that version.

```bash
export DH=<your-dockerhub-username>
docker login
for v in 1.0.0 1.1.0 2.0.0; do
  docker build --target base --build-arg APP_VERSION=$v -t $DH/aceest-fitness:$v .
  docker push $DH/aceest-fitness:$v
done
docker tag $DH/aceest-fitness:2.0.0 $DH/aceest-fitness:latest && docker push $DH/aceest-fitness:latest
```
Run the tests inside a container:
```bash
docker build --target test -t aceest-fitness:test .
docker run --rm aceest-fitness:test
```
Podman works the same way: replace `docker` with `podman`.

## 6. Git Workflow and Tags

Push `assignment` and open a GitHub pull request with `main` as the base.
Merge the pull request on GitHub, then create and push the release tag from
the updated `main` branch.

```bash
git switch assignment
# ... changes ...
git status
git add README.md app.py tests/test_app.py  # example; use paths for your changed files
git commit -m "feat: describe the change"
git push -u origin assignment
# Open and merge the assignment -> main pull request on GitHub.
git fetch origin
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```

At the time these instructions were written, GitHub had an `assignment`
branch but no `main` branch. A pull request needs a base branch. From a fresh
clone, create and publish `main` at the intended starting commit before
opening the PR. For this repository's current history, that base commit is
`6e85b4a`:

```bash
git clone --branch assignment https://github.com/ManasaBhat-2025tm93082/Devops-Assignment-2-.git
cd Devops-Assignment-2-
git switch -c main 6e85b4a
git push -u origin main
git switch assignment
```

After creating `main`, open the PR and follow the merge-and-tag steps above.
Use release tags such as `v1.0.0`, `v1.1.0`, and `v2.0.0` for the corresponding
source releases.

## 7. SonarQube

### SonarQube Cloud

Create or select the project in SonarQube Cloud and use the matching
organization and project key from `sonar-project.properties`. Add the
SonarQube token as the `SONAR_TOKEN` secret in GitHub Actions. For Jenkins,
configure a SonarQube installation named `SonarQube` with server URL
`https://sonarcloud.io` and store the token as a Jenkins credential. Do not
commit tokens to the repository.

Configure the project webhook to point to
`https://<jenkins-host>/sonarqube-webhook/` if Jenkins must receive the quality
gate result. The Jenkins quality-gate stage waits for this result.

### Optional local SonarQube server

Use this option only if you want to run SonarQube locally instead of using
SonarQube Cloud:

```bash
docker run -d --name sonarqube -p 9000:9000 sonarqube:community
```

Open http://localhost:9000, change the initial administrator password, then
create a project and token. Configure the Jenkins server URL and webhook to
match this local server.

## 8. Jenkins Configuration

Plugins: Pipeline, Git, JUnit, Credentials Binding, **SonarQube Scanner**.

| Where | Setting |
|-------|---------|
| Manage Jenkins -> Tools | SonarQube Scanner installation named `SonarScanner` |
| Manage Jenkins -> System | SonarQube server named `SonarQube` (URL + token as a credential) |
| Credentials | `dockerhub-creds` (username/password) and `kubeconfig` (secret file) |
| Agent machine | Python 3 with venv, Docker (jenkins user in the `docker` group), kubectl |
| Job | Pipeline from SCM -> Git -> this repo -> branch `*/main` after merge -> script path `Jenkinsfile` |

The Jenkinsfile currently has a placeholder for `DOCKERHUB_USER`; replace it
with your Docker Hub namespace before enabling image publishing. The pipeline
polls SCM approximately every two minutes. Its parameters are `RUN_SONAR`,
`PUSH_IMAGE`, `DEPLOY`, and `STRATEGY`; by default, deployment is disabled.
Each build can archive a versioned `.tar.gz` artifact, `coverage.xml`, and
`pytest-report.xml`. Docker build/push requires Docker on the agent.
Deployment requires the configured `kubeconfig` credential and a reachable
cluster. The Jenkinsfile's automatic rollout undo applies to the
`rolling-update` strategy; use the rollback scripts below for manual
blue-green or canary rollback.

## 9. Kubernetes Deployment (Minikube)

### 9.0 Prepare local images and Minikube

Run these commands in a VDI with Docker installed and running, Start from the
directory where you want the repository cloned. The commands clone the
repository, build three tags from the same `assignment` checkout, install
Minikube and kubectl in the repository directory, start the cluster, and load
the images into Minikube. They do **not** publish images to Docker Hub; use
section 5 for that. The three tags identify the image's `APP_VERSION`; they
will contain the same application source unless you build from different
revisions.

```bash
git clone https://github.com/ManasaBhat-2025tm93082/Devops-Assignment-2-.git
cd Devops-Assignment-2-
git checkout assignment

docker build --target base --build-arg APP_VERSION=1.0.0 -t localhost:5001/aceest-fitness:1.0.0 .
docker build --target base --build-arg APP_VERSION=1.1.0 -t localhost:5001/aceest-fitness:1.1.0 .
docker build --target base --build-arg APP_VERSION=2.0.0 -t localhost:5001/aceest-fitness:2.0.0 .

curl -Lo minikube https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
curl -Lo kubectl "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x minikube kubectl
export PATH=$PWD:$PATH

minikube start --driver=docker --cpus=2 --memory=3072
minikube addons enable ingress

minikube image load localhost:5001/aceest-fitness:1.0.0
minikube image load localhost:5001/aceest-fitness:1.1.0
minikube image load localhost:5001/aceest-fitness:2.0.0

chmod +x scripts/*.sh
export DOCKERHUB_USER=localhost:5001
kubectl get nodes
```

`scripts/deploy.sh` replaces the literal `DOCKERHUB_USER` in each Kubernetes
manifest with the value of the environment variable. Here it is set to
`localhost:5001` so the manifests refer to the locally built image names. The
images have been loaded into Minikube, so this workflow does not require a
registry listening on port 5001. Keep this value for the local-image workflow;
for images pulled from Docker Hub, set it to your Docker Hub username instead.
Run the deployment examples below in the same shell so that this environment
variable remains set. If you open a new shell, export it again first.

### 9.1 Rolling Update (zero downtime, rollback)

```bash
scripts/deploy.sh rolling-update
URL=$(minikube service aceest-rolling --url); curl $URL/version        # 1.0.0
kubectl set image deployment/aceest-rolling aceest=$DOCKERHUB_USER/aceest-fitness:1.1.0
kubectl rollout status deployment/aceest-rolling
curl $URL/version                                                      # 1.1.0
scripts/rollback.sh rolling                                            # back to 1.0.0
```
`maxUnavailable: 0` and readiness probes keep the old pods serving until new pods are ready.

### 9.2 Blue-Green
```bash
scripts/deploy.sh blue-green
URL=$(minikube service aceest-bg --url); curl $URL/version             # blue = 1.0.0
scripts/switch-blue-green.sh green; curl $URL/version                  # green = 2.0.0
scripts/rollback.sh blue-green; curl $URL/version                      # instant rollback
```

### 9.3 Canary (about 10 percent of traffic)
```bash
scripts/deploy.sh canary
URL=$(minikube service aceest-canary --url)
for i in $(seq 1 30); do curl -s $URL/version; echo; done | sort | uniq -c
scripts/rollback.sh canary                  # canary scaled to 0, stable back to 10 pods
```

### 9.4 A/B Testing (header based)
```bash
scripts/deploy.sh ab-testing
curl --resolve ab.aceest.local:80:$(minikube ip) http://ab.aceest.local/version
curl --resolve ab.aceest.local:80:$(minikube ip) -H "X-Variant: B" http://ab.aceest.local/version
```
Users without the header get 1.0.0; requests with `X-Variant: B` get 2.0.0.

### 9.5 Shadow Deployment (traffic mirroring)
```bash
scripts/deploy.sh shadow
curl --resolve shadow.aceest.local:80:$(minikube ip) http://shadow.aceest.local/version   # 1.0.0
```
The ingress controller forwards a copy of each request to the shadow service
and discards the shadow response; clients receive only the live response.
The application image does not enable HTTP access logging by default, so
`kubectl logs deployment/aceest-shadow` will not necessarily show each copied
request. To observe the mirrored requests, enable request logging or inspect
the traffic with an appropriate test/debug tool.

On macOS or Windows with the Docker driver, run `minikube tunnel` in another terminal for ingress access.
Deploy everything at once with `scripts/deploy.sh all`. Check state with `kubectl get all`.

## 10. GitHub Actions

`.github/workflows/main.yml` runs on every push and pull request. It checks
Python syntax, runs Flake8, builds the Docker runtime and test images, and runs
Pytest in the test container. It also runs SonarQube analysis; configure the
`SONAR_TOKEN` repository secret before relying on that job.

## 11. Author

**Manasa Bhat** - Introduction to DevOps (CSIZG514 / SEZG514), Assignment 2.
