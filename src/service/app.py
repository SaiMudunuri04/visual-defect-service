"""Image classification API with artifact-checked readiness."""

import io
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from .observability import RequestLoggingMiddleware

app = FastAPI(title="Visual defect classifier", version="0.1.0")
app.add_middleware(RequestLoggingMiddleware)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


@lru_cache(maxsize=1)
def model_bundle():
    path = Path(os.getenv("MODEL_PATH", "artifacts/vision-model.pt"))
    if not path.is_file():
        raise FileNotFoundError(path)
    import torch
    from torch import nn
    from torchvision.models import ResNet18_Weights, resnet18

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("architecture") != "resnet18" or not checkpoint.get("classes"):
        raise ValueError("Unsupported checkpoint")
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(checkpoint["classes"]))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model, checkpoint["classes"], ResNet18_Weights.DEFAULT.transforms()


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        model_bundle()
    except (FileNotFoundError, ValueError, RuntimeError):
        raise HTTPException(503, "Model artifact unavailable")
    return {"status": "ready"}


@app.post("/predict")
async def predict(file: Annotated[UploadFile, File()]):
    from PIL import Image, UnidentifiedImageError

    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "Expected PNG, JPEG or WebP")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image too large")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise HTTPException(413, "Image dimensions too large")
            image = opened.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Invalid image")
    import torch
    try:
        model, classes, transform = model_bundle()
        with torch.inference_mode():
            probabilities = torch.softmax(model(transform(image).unsqueeze(0)), dim=1)[0]
    except (FileNotFoundError, ValueError, RuntimeError):
        raise HTTPException(503, "Model artifact unavailable")
    index = int(probabilities.argmax())
    return {"class": classes[index], "confidence": float(probabilities[index]),
            "scores": {name: float(probabilities[i]) for i, name in enumerate(classes)}}
