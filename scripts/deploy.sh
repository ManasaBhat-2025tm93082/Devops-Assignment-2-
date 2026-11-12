#!/usr/bin/env bash
# Usage: DOCKERHUB_USER=<name> scripts/deploy.sh <rolling-update|blue-green|canary|ab-testing|shadow|all>
set -euo pipefail
: "${DOCKERHUB_USER:?Set DOCKERHUB_USER to your Docker Hub username}"
cd "$(dirname "$0")/.."
targets="${1:?strategy required}"
[ "$targets" = "all" ] && targets="rolling-update blue-green canary ab-testing shadow"
for t in $targets; do
  echo ">>> Deploying $t"
  sed "s/DOCKERHUB_USER/${DOCKERHUB_USER}/g" "k8s/${t}.yaml" | kubectl apply -f -
done
kubectl get deployments,services
