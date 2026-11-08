# AIOpSaaS - AI Operations Agent for Kubernetes

> Intelligent Kubernetes operations using LLMs (Claude, OpenAI, GitHub Copilot)

![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Status](https://img.shields.io/badge/status-Beta-yellow)

## 🚀 Overview

AIOpSaaS is a production-ready Kubernetes operations agent that leverages AI/LLMs to analyze cluster health, diagnose issues, and suggest optimizations. It's designed as a **platform-agnostic**, **zero vendor lock-in** system that works with Anthropic Claude (default), OpenAI, GitHub Copilot, and more.

### Key Features

✅ **Multi-LLM Support** — Anthropic Claude (default), Claude Agent SDK (Claude drives kubectl itself), OpenAI, GitHub Copilot; easy to extend  
✅ **Lazy Provider Loading** — A missing optional SDK disables only that provider, never the whole agent  
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
  - **Anthropic API key** (Claude) — the default provider
  - **OpenAI API key** (ChatGPT)
  - **GitHub account with Copilot subscription** + Personal Access Token (PAT)

### For Kubernetes Deployment
- Kubernetes 1.20+
- Helm 3.0+
- Helmfile (optional, for GitOps workflow)

---

## 🏃 Quick Start

### Option 1: Local Development (Fastest)

#### With Anthropic Claude (default)
```bash
# 1. Clone and setup
git clone https://github.com/jkeith1/AIOpSaaS.git
cd AIOpSaaS
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Triage a namespace
python -m orchestrator.main --namespace default

# See exactly what would be sent to the model, without spending tokens
python -m orchestrator.main --namespace default --dry-run
```

#### With the Claude Agent SDK (Claude calls kubectl itself)
```bash
pip install claude-agent-sdk     # also needs Node.js + the Claude Code CLI
export ANTHROPIC_API_KEY="sk-ant-..."
export LLM_PROVIDER="claude-agent"
python -m orchestrator.main --namespace default
```

#### With OpenAI (ChatGPT)
```bash
pip install -r requirements-optional.txt
export OPENAI_API_KEY="sk-..."
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
# 1. Anthropic Claude (default)
export ANTHROPIC_API_KEY="sk-ant-..."
# Optional model override. Aliases opus/sonnet/haiku are expanded for you.
export CLAUDE_MODEL="claude-sonnet-5"   # or claude-opus-5, claude-haiku-4-5-20251001

# 2. OpenAI
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o"

# 3. GitHub Copilot
export GITHUB_TOKEN="ghp_..."

# 4. Explicit provider selection (always wins over auto-detection)
export LLM_PROVIDER="claude"   # claude, claude-agent, openai, copilot-sdk
```

**Generic `LLM_*` variables.** The Helm chart injects `LLM_API_KEY`, `LLM_MODEL`,
`LLM_TEMPERATURE`, `LLM_MAX_TOKENS` and `LLM_TIMEOUT` rather than per-provider
names, so one Secret and one ConfigMap work for every provider. Provider-specific
names (`ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, ...) take precedence when both are set.

**LLM Parameters**:
```bash
# Temperature: lower = deterministic. Triage defaults to 0.2, not 0.7 -
# you want the same evidence to produce the same diagnosis.
export CLAUDE_TEMPERATURE=0.2
export OPENAI_TEMPERATURE=0.7

# Max output tokens
export CLAUDE_MAX_TOKENS=4096

# Max tool-use round trips (claude-agent provider only)
export AGENT_MAX_TURNS=20
```

---

## 🧪 Testing

The test suite runs fully offline — the `anthropic` SDK is stubbed and a fake
`kubectl` on `PATH` serves canned cluster data, so no cluster and no API key are
needed:

```bash
python -m unittest discover -s tests -t .
```

It covers the provider (system-prompt handling, retries, env precedence),
the factory (lazy loading, detection order), the collectors and summarizers,
and the full triage path end to end.

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
   (internal)            (Claude/OpenAI/GitHub)
```

### Deployment Methods

#### Method 1: Helmfile (Recommended for GitOps)

```bash
# 1. Create namespace and secrets
kubectl create namespace aiops
kubectl create secret generic aiops-secrets \
  --namespace aiops \
  --from-literal=llm-api-key="sk-ant-..."   # your Anthropic API key

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
  --from-literal=llm-api-key="sk-ant-..."

# Deploy with Helm
helm upgrade --install aiops-agent ./helm/aiops-agent \
  --namespace aiops \
  --set llmConfig.provider=claude \
  --set llmConfig.model=claude-sonnet-5

# Or let the script do build + push + secret + deploy in one go:
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   ./scripts/build-and-deploy.sh
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
│  SDK        │ │          │ │          │ │               │
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
│   │   ├── copilot_sdk_provider.py    # Official Copilot SDK implementation
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
├── SESSION_SUMMARY.md                 # Session bookmark for continuing work
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

## 🏁 Local Development Shutdown

When you're done with local development, shut down resources to avoid burning system resources:

### Quick Shutdown (Preserves venv)

```bash
# Deactivate Python virtual environment
deactivate

# Delete Kind cluster (removes all containers, services, etc.)
kind delete cluster --name aiops

# Stop Podman registry
podman stop registry

# Verify everything is stopped
kind get clusters
podman ps
```

### Full Cleanup (Removes everything)

```bash
# Deactivate and remove venv
deactivate
rm -rf venv/

# Delete Kind cluster
kind delete cluster --name aiops

# Stop and remove registry container
podman stop registry
podman rm registry

# Verify cleanup
kind get clusters
podman ps
```

### Notes

- **Python venv**: Safe to keep if you plan to continue work soon (saves reinstall time). Takes ~200MB disk space.
- **Kind cluster**: Safely deleted. Can be recreated anytime with `kind create cluster --name aiops`.
- **Podman registry**: Can be recreated if needed. Images remain in Podman.
- **SESSION_SUMMARY.md**: Keep in repo for quick reference when resuming work.

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
