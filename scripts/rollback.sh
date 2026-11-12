#!/usr/bin/env bash
# Usage: scripts/rollback.sh <rolling|canary|blue-green>
set -euo pipefail
case "${1:?strategy required}" in
  rolling)    kubectl rollout undo deployment/aceest-rolling
              kubectl rollout status deployment/aceest-rolling --timeout=120s ;;
  canary)     kubectl scale deployment/aceest-canary --replicas=0
              kubectl scale deployment/aceest-stable --replicas=10 ;;
  blue-green) "$(dirname "$0")/switch-blue-green.sh" blue ;;
  *) echo "unknown strategy"; exit 1 ;;
esac
