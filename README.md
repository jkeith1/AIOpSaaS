# AIOpSaaS - AI Operations Agent for Kubernetes

> Intelligent Kubernetes operations using LLMs (OpenAI, Claude, GitHub Copilot)

![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Status](https://img.shields.io/badge/status-Beta-yellow)

## 🚀 Overview

AIOpSaaS is a production-ready Kubernetes operations agent that leverages AI/LLMs to analyze cluster health, diagnose issues, and suggest optimizations. It's designed as a **platform-agnostic**, **provider-agnostic** solution that works with any Kubernetes distribution (Kind, EKS, GKE, AKS, on-prem) and any LLM (GitHub Copilot via your subscription, OpenAI, Anthropic Claude, or custom providers).

### Key Features

✅ **Multi-LLM Support** — GitHub Copilot (recommended if you have subscription), OpenAI GPT-4, Claude 3.5, easy to extend  
✅ **Zero Vendor Lock-in** — Add/swap providers with environment variables, no code changes  
✅ **Kubernetes Native** — Runs as CronJob in any K8s cluster, reads actual cluster state via kubectl  
✅ **GitOps Ready** — Helm + Helmfile deployment, works in CI/CD pipelines (GitLab Runner, GitHub Actions, etc)  
✅ **Security First** — Non-root container, read-only RBAC, API keys in secrets, no sensitive data in logs  
✅ **Production Hardened** — Structured logging, error handling, graceful timeouts, resource limits  

---

## 📋 Prerequisites

### For Local Development
- Python 3.9+
- `pip` and `virtualenv`
- One of:
  - **GitHub account with Copilot subscription** + Personal Access Token (PAT)
  - **OpenAI API key** (ChatGPT)
  - **Anthropic API key** (Claude)

### For Kubernetes Deployment
- Kubernetes 1.20+
- Helm 3.0+
- Helmfile (optional, for GitOps workflow)

---

## 🏃 Quick Start

### Option 1: Local Development (Fastest)

#### With GitHub Copilot (easiest if you have GitHub subscription)
```bash
# 1. Clone and setup
git clone https://github.com/jkeith1/AIOpSaaS.git
cd AIOpSaaS
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your GitHub token (Personal Access Token with 'copilot' scope)
export GITHUB_TOKEN="ghp_..."

# 4. Run it
python -m orchestrator.main
```

#### With OpenAI (ChatGPT)
```bash
export OPENAI_API_KEY="sk-..."
python -m orchestrator.main
```

#### With Anthropic (Claude)
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python -m orchestrator.main
```

### Option 2: Docker (for testing in Kind cluster)

```bash
# Build container
podman build -t aiops-agent:latest .

# Tag for local registry
podman tag aiops-agent:latest localhost:5001/aiops-agent:latest

# Push to local registry
podman push localhost:5001/aiops-agent:latest

# Load into Kind
kind load image-archive --name aiops <(podman save localhost:5001/aiops-agent:latest)
```

### Option 3: Kubernetes Deployment (Recommended for Production)

See [Kubernetes Deployment](#kubernetes-deployment) section below.

---

## 🔧 Configuration

### Environment Variables

**LLM Provider Selection** (auto-detected in priority order):
```bash
# 1. GitHub Copilot (recommended if you have GitHub subscription)
export GITHUB_TOKEN="ghp_..."
# Optional: override model (default: gpt-4-turbo)
export GITHUB_COPILOT_MODEL="gpt-4-turbo"

# 2. OpenAI
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o"  # or gpt-4-turbo, gpt-3.5-turbo

# 3. Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
export CLAUDE_MODEL="claude-3-5-sonnet-20241022"  # or claude-3-opus, claude-3-haiku

# 4. Explicit provider selection (optional)
export LLM_PROVIDER="github-copilot"  # github-copilot, openai, anthropic
```

**LLM Parameters**:
```bash
# Temperature (0-2): Lower = deterministic, Higher = creative
export OPENAI_TEMPERATURE=0.7
export CLAUDE_TEMPERATURE=0.7

# Max tokens: Max output length
export OPENAI_MAX_TOKENS=2048
export CLAUDE_MAX_TOKENS=2048
```

---

## 🐳 Kubernetes Deployment

### Architecture

```
┌─────────────────────────────────────────┐
│         Your Kubernetes Cluster         │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  CronJob: aiops-agent             │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ Container: aiops-agent      │  │  │
│  │  │ Image: aiops-agent:latest   │  │  │
│  │  │ RunAsUser: 10001 (non-root) │  │  │
│  │  └─────────────────────────────┘  │  │
│  │                                   │  │
│  │  ServiceAccount: aiops-agent      │  │
│  │  RBAC: ClusterRole (read-only)    │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Secrets: aiops-secrets           │  │
│  │  - llm-api-key (API key)          │  │
│  │  - github-token (GitHub PAT)      │  │
│  └───────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
        │                          ▲
        │ Read cluster state       │ Send analysis reports
        ▼                          │
   kubectl API                 LLM API
   (internal)            (OpenAI/Claude/GitHub)
```

### Deployment Methods

#### Method 1: Helmfile (Recommended for GitOps)

```bash
# 1. Create namespace and secrets
kubectl create namespace aiops
kubectl create secret generic aiops-secrets \
  --namespace aiops \
  --from-literal=github-token="ghp_..." \
  --from-literal=llm-api-key="ghp_..."  # Usually same as github-token for Copilot

# 2. Deploy using helmfile
helmfile -e dev sync

# For production (3 replicas)
helmfile -e prod sync
```

#### Method 2: Helm Only

```bash
# Create namespace and secret
kubectl create namespace aiops
kubectl create secret generic aiops-secrets \
  --namespace aiops \
  --from-literal=github-token="ghp_..." \
  --from-literal=llm-api-key="ghp_..."

# Deploy with Helm
helm install aiops-agent ./helm/aiops-agent \
  --namespace aiops \
  --set llmProvider=github-copilot
```

#### Method 3: kubectl (Direct YAML)

```bash
# Create namespace
kubectl create namespace aiops

# Create secrets
kubectl create secret generic aiops-secrets \
  --namespace aiops \
  --from-literal=github-token="ghp_..." \
  --from-literal=llm-api-key="ghp_..."

# Apply YAML manifests
kubectl apply -f kubernetes/
```

### Verify Deployment

```bash
# Check CronJob
kubectl get cronjob -n aiops

# View recent job runs
kubectl get jobs -n aiops

# Check pod logs
kubectl logs -n aiops -l app=aiops-agent --tail=100

# Trigger manual run (for testing)
kubectl create job --from=cronjob/aiops-agent manual-run -n aiops
```

---

## 📊 Analysis Features

### 1. Cluster Status Analysis

Analyzes overall cluster health including:
- Node status and resource utilization
- Pod distribution and health
- Recent events and errors
- Network and storage issues

```python
analysis = analyzer.analyze_cluster_status(cluster_info)
```

### 2. Pod Diagnostics

Diagnoses specific pod issues:
- Root cause analysis
- Severity assessment
- Remediation recommendations

```python
diagnosis = analyzer.diagnose_pod_issues(pod_info)
```

### 3. Optimization Suggestions

Recommends cluster optimizations for:
- Cost reduction
- Performance improvement
- Reliability enhancement

```python
suggestions = analyzer.suggest_optimizations(cluster_config)
```

---

## 🔌 Adding New LLM Providers

The architecture is designed for easy extensibility. To add a new provider (Bedrock, Cohere, Ollama, etc):

### Step 1: Create Provider Class

```python
# orchestrator/models/my_provider.py
from .base import ModelProvider, ModelConfig, Message

class MyProvider(ModelProvider):
    def validate_config(self, config: ModelConfig) -> bool:
        # Validate configuration
        return True
    
    def complete(self, messages: list[Message]) -> str:
        # Call your LLM API
        return response_text
    
    def get_model_name(self) -> str:
        return self.config.model_name or "my-model"
    
    @staticmethod
    def from_env() -> "MyProvider":
        # Load from environment variables
        return MyProvider(config)
```

### Step 2: Register Provider

```python
# In your code or orchestrator.main
from orchestrator.models.factory import ModelProviderFactory
from orchestrator.models.my_provider import MyProvider

ModelProviderFactory.register_provider("myprovider", MyProvider)
```

### Step 3: Use It

```bash
export LLM_PROVIDER="myprovider"
export MY_PROVIDER_API_KEY="..."
python -m orchestrator.main
```

---

## 🚀 Integration Examples

### GitLab CI Pipeline

```yaml
analyze_cluster:
  stage: analyze
  image: python:3.11-slim
  script:
    - pip install -r requirements.txt
    - export GITHUB_TOKEN="$GITHUB_TOKEN"
    - python -m orchestrator.main
  only:
    - schedules  # Run on schedule
```

### GitHub Actions Workflow

```yaml
name: AIOps Analysis
on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m orchestrator.main
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## 📝 Architecture

### Model Provider Abstraction

```
┌─────────────────────────────────────────┐
│     ModelProviderFactory                │
│  (Auto-detects provider from env)       │
└─────────────────────────────────────────┘
                    │
     ┌──────────────┼──────────────┬──────────────┐
     ▼              ▼              ▼              ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐
│  GitHub     │ │ OpenAI   │ │ Anthropic│ │ Custom        │
│  Copilot    │ │ Provider │ │ Provider │ │ Provider      │
│  Provider   │ │          │ │          │ │               │
└─────────────┘ └──────────┘ └──────────┘ └───────────────┘
        │              │              │              │
        └──────────────┴──────────────┴──────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   ┌─────────────┐      ┌──────────────┐
   │  Message    │      │ ModelConfig  │
   │  (abstraction)     │              │
   └─────────────┘      └──────────────┘
        │
        ▼
   ┌──────────────────────┐
   │ KubernetesAnalyzer   │
   │ (LLM-agnostic)       │
   └──────────────────────┘
```

---

## 🔐 Security

- **Container**: Runs as non-root user (uid 10001), read-only root filesystem
- **RBAC**: Read-only ClusterRole, minimal permissions (get, list, watch)
- **Secrets**: API keys stored in Kubernetes secrets, never in code/config
- **Logs**: Structured JSON logging, no sensitive data logged
- **Network**: TLS for all external API calls (GitHub, OpenAI, Anthropic)
- **Pod Security**: SecurityContext enforces non-root, no privilege escalation

---

## 📈 Monitoring & Logging

### View Logs

```bash
# Latest logs
kubectl logs -n aiops -l app=aiops-agent -f

# Specific job run
kubectl logs -n aiops <pod-name>

# Previous runs (last 10)
kubectl logs -n aiops -l app=aiops-agent --tail=1000 --timestamps=true
```

### Prometheus Metrics (Optional)

The CronJob includes Prometheus scrape annotations:
```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8080"
```

Metrics available at `/metrics` endpoint (future enhancement).

---

## 🛠️ Development

### Project Structure

```
AIOpSaaS/
├── orchestrator/
│   ├── models/
│   │   ├── base.py                    # Abstract ModelProvider
│   │   ├── github_copilot_provider.py # GitHub Copilot implementation
│   │   ├── openai_provider.py         # OpenAI GPT implementation
│   │   ├── claude_provider.py         # Anthropic Claude implementation
│   │   ├── factory.py                 # Provider factory & auto-detection
│   │   └── __init__.py
│   ├── main.py                        # Main orchestrator & KubernetesAnalyzer
│   └── __init__.py
├── helm/
│   └── aiops-agent/                   # Helm chart
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── helmfile.yaml                      # Helmfile (GitOps)
├── Containerfile                      # Podman/Docker build
├── requirements.txt                   # Python dependencies
└── README.md
```

### Running Tests

```bash
# (Tests TBD - contributions welcome!)
python -m pytest tests/
```

### Contributing

Contributions welcome! Areas to help:
- Real Kubernetes introspection (kubectl calls)
- Prometheus metrics exporter
- Alert routing (Slack, PagerDuty, etc)
- Additional LLM providers (Bedrock, Cohere, Ollama)
- Unit & integration tests

---

## ⚠️ Limitations

- **Real K8s integration**: Currently uses sample data. To read actual cluster state, implement kubectl client.
- **Stateless analysis**: Each run is independent. Future: add history/trends.
- **No remediation actions**: Currently suggests fixes. Future: auto-remediate (with approval gates).
- **Minimal monitoring**: Logs work. Future: Prometheus/OpenTelemetry metrics.

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 🤝 Support & Questions

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Docs**: See README.md and inline code comments

---

## 🎯 Roadmap

- [ ] Real Kubernetes API introspection (kubectl client)
- [ ] Prometheus metrics exporter
- [ ] Alert routing (Slack, PagerDuty, OpsGenie)
- [ ] Remediation actions (with approval)
- [ ] Trend analysis & historical comparisons
- [ ] Web UI for viewing analysis results
- [ ] AWS/Azure/GCP cost optimization specific analysis
- [ ] Integration with FluxCD/ArgoCD for GitOps alerts

---

**Made with ❤️ for Kubernetes operators**
