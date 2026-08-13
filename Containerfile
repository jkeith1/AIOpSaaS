# Containerfile — hardened, minimal AIOpS Agent runtime

# 1. Use a slim, actively maintained Python base
FROM python:3.13-slim AS base

# 2. Set up non-root user early
RUN useradd -m -u 10001 aiops

# 3. Install only what we truly need, no recommends
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# 4. Install kubectl (pinned to a specific version for reproducibility)
ARG KUBECTL_VERSION=v1.30.3
RUN curl -sSL https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl \
    -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# 5. Create working directory and set permissions
WORKDIR /app
RUN chown -R aiops:aiops /app

# 6. Copy only what’s needed
COPY orchestrator/ ./orchestrator/
COPY scripts/ ./scripts/
COPY requirements.txt .

# 7. Install Python deps with no cache
RUN pip install --no-cache-dir -r requirements.txt

# 8. Ensure scripts are executable
# comment out for now as nothing in scripts dir RUN chmod +x /scripts/*.sh

# 9. Drop privileges: run as non-root
USER aiops

# 10. Environment defaults (override at runtime)
ENV PYTHONUNBUFFERED=1 \
    AIOPS_PLATFORM="teams" \
    KUBECONFIG="/kube/config"

# 11. Volume for kubeconfig (read-only)
VOLUME ["/kube"]

# 12. Default command
CMD ["python", "-m", "orchestrator.main"]

# 13 install kubectl inside the agent container as root
USER root

RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# switch back to aiops user
USER aiops
