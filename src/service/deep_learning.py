"""Fine-tune an ImageNet-pretrained ResNet18 with split-leakage checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def validate_splits(root: Path) -> list[str]:
    splits = {}
    hashes = {}
    for split in ("train", "val"):
        folder = root / split
        classes = sorted(path.name for path in folder.iterdir() if path.is_dir()) if folder.exists() else []
        if len(classes) < 2:
            raise ValueError(f"{split} must have at least two class directories")
        splits[split] = classes
        hashes[split] = set()
        for name in classes:
            images = sorted(path for path in (folder / name).rglob("*")
                            if path.is_file() and path.suffix.lower() in SUFFIXES)
            if not images:
                raise ValueError(f"No images in {split}/{name}")
            for image in images:
                hashes[split].add(hashlib.sha256(image.read_bytes()).hexdigest())
    if splits["train"] != splits["val"]:
        raise ValueError("Train and validation class names differ")
    if hashes["train"] & hashes["val"]:
        raise ValueError("The same image appears in both splits")
    return splits["train"]


def train(root: Path, output: Path, epochs: int = 15, batch_size: int = 32,
          patience: int = 4, seed: int = 42) -> dict:
    if epochs < 1 or batch_size < 1 or patience < 1:
        raise ValueError("Training parameters must be positive")
    classes = validate_splits(root)
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms
    from torchvision.models import ResNet18_Weights, resnet18

    torch.manual_seed(seed)
    weights = ResNet18_Weights.DEFAULT
    transform_train = transforms.Compose([transforms.Resize((256, 256)),
                                          transforms.RandomResizedCrop(224), transforms.RandomHorizontalFlip(),
                                          transforms.ToTensor(),
                                          transforms.Normalize(weights.meta.get("mean", (0.485, 0.456, 0.406)),
                                                               weights.meta.get("std", (0.229, 0.224, 0.225)))])
    transform_val = weights.transforms()
    training = datasets.ImageFolder(root / "train", transform=transform_train)
    validation = datasets.ImageFolder(root / "val", transform=transform_val)
    train_loader = DataLoader(training, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(validation, batch_size=batch_size)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = resnet18(weights=weights)
    for parameter in model.parameters():
        parameter.requires_grad = False
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.fc.parameters(), lr=1e-3, weight_decay=1e-2)
    criterion = nn.CrossEntropyLoss()
    best_loss, stale = float("inf"), 0
    history = []
    output.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, epochs + 1):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
        model.eval()
        total_loss = correct = samples = 0
        with torch.inference_mode():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                logits = model(images)
                total_loss += criterion(logits, labels).item() * len(labels)
                correct += (logits.argmax(1) == labels).sum().item()
                samples += len(labels)
        val_loss = total_loss / samples
        history.append({"epoch": epoch, "val_loss": val_loss, "val_accuracy": correct / samples})
        if val_loss < best_loss - 1e-4:
            best_loss, stale = val_loss, 0
            torch.save({"model_state": model.state_dict(), "classes": classes,
                        "architecture": "resnet18", "epoch": epoch, "seed": seed}, output)
        else:
            stale += 1
            if stale >= patience:
                break
    report = {"classes": classes, "device": device, "best_val_loss": best_loss,
              "epochs_ran": len(history), "history": history, "checkpoint": str(output)}
    output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/vision-model.pt"))
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()
    print(json.dumps(train(args.dataset, args.output, args.epochs), indent=2))


if __name__ == "__main__":
    main()
