#!/usr/bin/env bash
# Usage: scripts/switch-blue-green.sh <blue|green>   (also the rollback: switch back to the old slot)
set -euo pipefail
slot="${1:?blue or green}"
kubectl rollout status "deployment/aceest-${slot}" --timeout=120s
kubectl patch service aceest-bg -p "{\"spec\":{\"selector\":{\"app\":\"aceest-bg\",\"slot\":\"${slot}\"}}}"
echo "Traffic now served by ${slot}"
