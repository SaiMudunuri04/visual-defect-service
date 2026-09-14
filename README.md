# Visual defect classification

[Architecture](docs/architecture.md) · [Operations runbook](docs/operations.md) · [Helm chart](k8s/helm/visual-defect-service/) · [Argo CD application](k8s/argocd/application.yaml)

An independent service for PyTorch transfer learning and image inference. This repository contains executable source, tests,
a container, Helm release, Argo CD application, and a CI workflow that builds an
immutable GHCR image after tests pass. It is a reference implementation; it has not
been deployed to a user's AWS account or Kubernetes cluster.

## Start here

**Problem:** classify visual defects with a reproducible image-inference path. **What this demonstrates:** ResNet18 transfer learning, split checks, early stopping, checkpointing, validation history, and bounded image inference. **Inspect first:** [`docs/architecture.md`](docs/architecture.md), [`src/service/app.py`](src/service/app.py), and the inference tests.

## Run

```sh
python -m pip install -e '.[test]'
python -m pytest -q
ruff check .
helm lint k8s/helm/visual-defect-service --strict
uvicorn service.app:app --reload
```

`/health/live` checks the process. `/health/ready` checks required local resources. Responses include a request ID and no-store/nosniff headers; JSON request logs omit bodies and query strings.
Configure data, model artifacts, and inference endpoints before serving traffic.

## Delivery

The workflow tests pull requests, then builds/pushes an image to GHCR on `main` and
updates the Helm image tag to the tested commit. Argo CD follows the single chart at [`k8s/helm/visual-defect-service/`](k8s/helm/visual-defect-service/).
Install `k8s/argocd/application.yaml` in a cluster with Argo CD, set environment-specific
Helm values, provide secrets through a cluster secret manager, and make the package
pullable by the cluster. Model/data volumes are configured through `volumes` and
`volumeMounts`; use `envFromSecretName` for credentials. The workflow does not
provision AWS or a cluster.

`.env.example` contains placeholders only. Never commit credentials or private data.

## Train and serve

Provide `train/<class>/*.png` and `val/<class>/*.png` under one dataset directory. Class sets must match, and byte-identical images across splits are rejected. Training downloads ImageNet ResNet18 weights, freezes the backbone, fine-tunes the classifier, and saves the best validation-loss checkpoint.

```sh
python -m service.deep_learning /path/to/dataset --output artifacts/vision-model.pt
MODEL_PATH=artifacts/vision-model.pt uvicorn service.app:app --host 127.0.0.1
```

Mount the reviewed checkpoint at `/models/vision-model.pt` and set `MODEL_PATH`. The API limits uploads to 8 MiB and decoded images to 20 million pixels; it accepts PNG, JPEG, or WebP and rejects malformed images before loading the model. A domain-specific evaluation set and GPU/CPU sizing are required before a real deployment. No image data or quality claim is bundled.
