#!/usr/bin/env bash
# Trigger one CronJob run and follow its logs.
set -euo pipefail

NAMESPACE="${NAMESPACE:-aiops}"
RELEASE="${RELEASE:-aiops-agent}"
JOB="${RELEASE}-manual-$(date +%s)"

kubectl create job --from="cronjob/$RELEASE" "$JOB" -n "$NAMESPACE"
echo "Waiting for pod..."
kubectl wait --for=condition=ready pod -l "job-name=$JOB" -n "$NAMESPACE" --timeout=90s \
  || echo "(pod not ready - showing whatever logs exist)"
kubectl logs -n "$NAMESPACE" -l "job-name=$JOB" --tail=-1 -f
