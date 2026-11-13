# ACEest Fitness & Gym - Complete CI/CD Pipeline (Assignment 2)

Flask fitness/gym management application delivered through a fully automated pipeline:
**Git/GitHub -> Jenkins -> Pytest -> SonarQube -> Docker -> Docker Hub -> Kubernetes (Minikube)**,
with Rolling Update, Blue-Green, Canary, Shadow and A/B deployment strategies and rollback.

Repository: Repository: https://github.com/ManasaBhat-2025tm93082/Devops-Assignment-2-

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
                                                    -> automatic rollback on failure
                                                                   |
                                          Minikube: rolling | blue-green | canary | A/B | shadow
```

## 2. Project Structure

```
app.py                    Flask app (app factory, routes, business logic, /version endpoint)
templates/index.html      Web UI (shows the running version)
tests/test_app.py         Pytest suite (26 tests)
VERSION                   Application version used for image tags and artifacts
Dockerfile                Multi-stage: base (runtime) and test (pytest) - build arg APP_VERSION
Jenkinsfile               Jenkins pipeline (Linux agent)
sonar-project.properties  SonarQube configuration
k8s/                      Kubernetes manifests, one file per deployment strategy
scripts/                  deploy.sh, switch-blue-green.sh, rollback.sh
.github/workflows/main.yml  GitHub Actions CI (build, lint, docker build, tests in container)
legacy_versions/          Original ACEest versions 1.0 - 3.2.4
```

## 3. Run Locally

```bash
python -m venv venv
source venv/bin/activate            # Windows CMD: venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python app.py                       # http://localhost:5000
```
Set `APP_VERSION=2.0.0` before starting to see the version-2 look (green header).
`GET /version` returns the version and pod name; every response carries an `X-App-Version` header.

## 4. Tests and Code Quality

```bash
python -m pytest -v --cov=app --cov-report=term-missing
python -m flake8 .
```
Coverage is exported to `coverage.xml` for SonarQube (`--cov-report=xml`).

## 5. Docker and Docker Hub

Build one image per application version and push them all to your Docker Hub repository
`<user>/aceest-fitness`:

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

```bash
git checkout -b feature/versioning
# ... changes ...
git commit -m "feat: add /version endpoint and version header"
git checkout main && git merge feature/versioning
git tag -a v1.0.0 -m "Release 1.0.0" && git push origin main --tags
```
Branches: `feature/*`, `bugfix/*`, `infra/*`. Commit prefixes: `feat:`, `fix:`, `test:`, `ci:`, `docker:`, `k8s:`, `docs:`.
Tags `v1.0.0`, `v1.1.0`, `v2.0.0` match the Docker image tags.

## 7. SonarQube

```bash
docker run -d --name sonarqube -p 9000:9000 sonarqube:community
```
1. Open http://localhost:9000 (login `admin` / `admin`, then change the password).
2. Create a project with key `aceest-fitness`; generate a token (My Account -> Security).
3. Add a webhook (Administration -> Configuration -> Webhooks):
   `http://<jenkins-host>:<port>/sonarqube-webhook/` so Jenkins receives the quality gate result.
4. Export the project report (screenshots of the dashboard and quality gate) for submission.

## 8. Jenkins Configuration

Plugins: Pipeline, Git, JUnit, Credentials Binding, **SonarQube Scanner**.

| Where | Setting |
|-------|---------|
| Manage Jenkins -> Tools | SonarQube Scanner installation named `SonarScanner` |
| Manage Jenkins -> System | SonarQube server named `SonarQube` (URL + token as a credential) |
| Credentials | `dockerhub-creds` (username/password) and `kubeconfig` (secret file) |
| Agent machine | Python 3 with venv, Docker (jenkins user in the `docker` group), kubectl |
| Job | Pipeline from SCM -> Git -> this repo -> branch `*/main` -> script path `Jenkinsfile` |

Edit `DOCKERHUB_USER` at the top of the `Jenkinsfile` to your Docker Hub username.
The pipeline polls GitHub every ~2 minutes (`pollSCM`) and builds on every new commit.
Build parameters: `RUN_SONAR`, `PUSH_IMAGE`, `DEPLOY` and `STRATEGY`.
Artifacts archived per build: `aceest-fitness-<version>-build<N>.tar.gz`, `coverage.xml`, `pytest-report.xml`.
Docker and Kubernetes stages are skipped automatically if the agent cannot use them.

## 9. Kubernetes Deployment (Minikube)

```bash
minikube start --driver=docker
minikube addons enable ingress          # needed for A/B testing and shadow
export DOCKERHUB_USER=<your-dockerhub-username>
```

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
kubectl logs deployment/aceest-shadow       # shows the mirrored copies of the requests
```
Users only ever see responses from the live version; the shadow version receives a copy of the traffic.

On macOS or Windows with the Docker driver, run `minikube tunnel` in another terminal for ingress access.
Deploy everything at once with `scripts/deploy.sh all`. Check state with `kubectl get all`.

## 10. GitHub Actions

`.github/workflows/main.yml` runs on every push and pull request: compile check, flake8,
Docker image build and Pytest inside the container.

## 11. Troubleshooting

| Problem | Fix |
|---------|-----|
| Jenkins: `docker: permission denied` | `sudo usermod -aG docker jenkins` and restart Jenkins |
| Quality gate stage hangs | SonarQube webhook to `/sonarqube-webhook/` is missing |
| Pods in `ImagePullBackOff` | Image not pushed, wrong `DOCKERHUB_USER`, or private repo |
| A/B or shadow returns 404 | Ingress addon not enabled: `minikube addons enable ingress` |
| Jenkins: `Cannot run program "sh"` / `Batch scripts can only be run on Windows nodes` | Use the `sh` Jenkinsfile on Linux agents, `bat` on Windows agents |

## 12. Author

**Manasa Bhat** - Introduction to DevOps (CSIZG514 / SEZG514), Assignment 2.
