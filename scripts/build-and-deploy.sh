#!/usr/bin/env bash
# Build, push and deploy the AIOps agent to the local kind cluster.
#
#   ./scripts/build-and-deploy.sh                 # build + deploy (claude)
#   PROVIDER=claude-agent ./scripts/build-and-deploy.sh   # Agent SDK image
#   SKIP_BUILD=1 ./scripts/build-and-deploy.sh    # redeploy current image
#
# Requires: podman, kind, helm, kubectl, and ANTHROPIC_API_KEY in the env.

set -euo pipefail

REGISTRY="${REGISTRY:-localhost:5001}"
IMAGE="${IMAGE:-aiops-agent}"
TAG="${TAG:-latest}"
NAMESPACE="${NAMESPACE:-aiops}"
RELEASE="${RELEASE:-aiops-agent}"
PROVIDER="${PROVIDER:-claude}"
MODEL="${MODEL:-claude-sonnet-5}"
KIND_CLUSTER="${KIND_CLUSTER:-aiops}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The Agent SDK provider needs Node + the Claude Code CLI baked in.
INSTALL_AGENT_SDK=false
[[ "$PROVIDER" == claude-agent* || "$PROVIDER" == "claude-code" ]] && INSTALL_AGENT_SDK=true

# Match the image arch to the machine (Apple Silicon builds arm64).
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  *)             ARCH=amd64 ;;
esac

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

for tool in podman kind helm kubectl; do
  command -v "$tool" >/dev/null || die "$tool not found on PATH"
done

[[ -n "${ANTHROPIC_API_KEY:-}" ]] || die \
  "ANTHROPIC_API_KEY is not set. export ANTHROPIC_API_KEY='sk-ant-...' first."

kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER" \
  || die "kind cluster '$KIND_CLUSTER' not found. Create it, or set KIND_CLUSTER."

say "Config: provider=$PROVIDER model=$MODEL arch=$ARCH agent-sdk=$INSTALL_AGENT_SDK"

# ---------------------------------------------------------------------------
if [[ -z "${SKIP_BUILD:-}" ]]; then
  say "Building $REGISTRY/$IMAGE:$TAG"
  podman build \
    --build-arg "TARGETARCH=$ARCH" \
    --build-arg "INSTALL_AGENT_SDK=$INSTALL_AGENT_SDK" \
    -t "$REGISTRY/$IMAGE:$TAG" \
    -f Containerfile .

  say "Pushing to the local registry"
  # The kind-local registry is plain HTTP.
  podman push --tls-verify=false "$REGISTRY/$IMAGE:$TAG" \
    || die "Push failed. Is the local registry running on ${REGISTRY##*:}?
  Start it with: podman run -d -p 5001:5000 --name kind-registry registry:2"
fi

# ---------------------------------------------------------------------------
say "Ensuring namespace '$NAMESPACE' and the API key secret exist"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic aiops-secrets \
  --from-literal=llm-api-key="$ANTHROPIC_API_KEY" \
  --namespace "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
say "Deploying the Helm release '$RELEASE'"
helm upgrade --install "$RELEASE" ./helm/aiops-agent \
  --namespace "$NAMESPACE" \
  --set "image.repository=$REGISTRY/$IMAGE" \
  --set "image.tag=$TAG" \
  --set "llmConfig.provider=$PROVIDER" \
  --set "llmConfig.model=$MODEL" \
  --wait --timeout 2m

say "Deployed. Trigger a run now with:"
cat <<TRIGGER

  kubectl create job --from=cronjob/$RELEASE ${RELEASE}-manual-\$(date +%s) -n $NAMESPACE
  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=aiops-agent --tail=200 -f

TRIGGER
