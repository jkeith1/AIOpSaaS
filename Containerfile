# Containerfile — hardened, minimal AIOpS Agent runtime

FROM python:3.13-slim AS base

# Build-time knobs
ARG KUBECTL_VERSION=v1.31.1
# Set to "true" to install Node.js + the Claude Agent SDK (needed only for the
# 'claude-agent' provider, which lets Claude drive the kubectl tools itself).
# The default 'claude' provider talks to the Messages API and needs none of it.
ARG INSTALL_AGENT_SDK=false
# Populated automatically by buildah/podman/docker buildx: amd64 | arm64.
# Without this, an Apple Silicon build pulls an x86 kubectl that cannot run.
ARG TARGETARCH=amd64

# 1. Non-root user, created early
RUN useradd -m -u 10001 aiops

# 2. Minimal OS packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/*

# 3. kubectl, matching the image architecture
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
        -o /usr/local/bin/kubectl \
    && chmod 0755 /usr/local/bin/kubectl \
    && kubectl version --client=true

# 4. Optional: Node.js + Claude Code CLI, required by claude-agent-sdk
RUN if [ "${INSTALL_AGENT_SDK}" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends nodejs npm \
        && npm install -g @anthropic-ai/claude-code \
        && npm cache clean --force \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app

# 5. Python deps first, so code edits do not bust the dependency layer
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "${INSTALL_AGENT_SDK}" = "true" ]; then \
           pip install --no-cache-dir "claude-agent-sdk>=0.1.0"; \
       fi

# 6. Application code
COPY orchestrator/ ./orchestrator/
RUN chown -R aiops:aiops /app

# 7. Drop privileges
USER aiops

# 8. Runtime environment
#    KUBECONFIG is deliberately NOT set: unset, kubectl uses the in-cluster
#    ServiceAccount token. Setting it to a path that is not mounted makes every
#    kubectl call fail. Mount a kubeconfig and set KUBECONFIG only for local runs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/aiops \
    KUBECACHEDIR=/tmp/.kube-cache \
    LLM_PROVIDER=claude \
    AIOPS_PLATFORM=teams

# 9. Default command: triage every namespace in WATCH_NAMESPACES
CMD ["python", "-m", "orchestrator.main"]
