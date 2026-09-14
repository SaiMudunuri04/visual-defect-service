
import pytest
from fastapi.testclient import TestClient

from service import app, deep_learning


def test_duplicate_image_split_rejected(tmp_path):
    for split in ("train", "val"):
        for label in ("good", "defect"):
            path = tmp_path / split / label / "image.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(label.encode())
    with pytest.raises(ValueError, match="same image"):
        deep_learning.validate_splits(tmp_path)


def test_missing_model_not_ready(monkeypatch):
    monkeypatch.setenv("MODEL_PATH", "/does-not-exist/model.pt")
    app.model_bundle.cache_clear()
    assert TestClient(app.app).get("/health/ready").status_code == 503


def test_invalid_image_rejected_before_model_load(monkeypatch):
    monkeypatch.setenv("MODEL_PATH", "/does-not-exist/model.pt")
    app.model_bundle.cache_clear()
    response = TestClient(app.app).post("/predict", files={"file": ("bad.png", b"not an image", "image/png")})
    assert response.status_code == 422
