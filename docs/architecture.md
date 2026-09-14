# Visual defect classification architecture

## Request and model path

Train/validation image folders → duplicate-byte split check → frozen ResNet18 backbone → early stopping → checkpoint → bounded image API

## Boundaries

- **Input:** Matching class folders in `train/` and `val/`, with no byte-identical images across splits. The API accepts PNG, JPEG, or WebP up to 8 MiB and 20 million decoded pixels.
- **Runtime:** `MODEL_PATH` points to a reviewed weights-only checkpoint with the expected architecture and class labels.
- **Failure behavior:** Missing/incompatible checkpoint makes readiness 503. Unsupported, oversized, or malformed images are rejected before inference.

The FastAPI process exposes `/health/live` for process liveness and `/health/ready` for local prerequisites. Each HTTP response carries a generated `X-Request-ID`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`. JSON request logs record method, path, status, request ID, and duration, never request bodies, query strings, credentials, or user data. Logs are local process telemetry, not a claim of production monitoring.

The [single Helm chart](../k8s/helm/visual-defect-service/) provides rolling updates, probes, resource bounds, security contexts, optional HPA and NetworkPolicy, and a PDB. [Argo CD](../k8s/argocd/application.yaml) points to that chart. Values need environment review before deployment, especially image pull access, ingress peers, external inference egress, and artifact mounts.

## Limits

ImageNet weights must be obtained for training. No domain evaluation set, production quality measure, or live inspection system is included.
