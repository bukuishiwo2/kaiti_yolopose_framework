#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from yolopose.core.config import normalize_torch_device
from yolopose.temporal.model import PoseFallModelConfig, build_pose_fall_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Train temporal fall classifier on pose sequences.')
    parser.add_argument('--config', default='configs/train_fall_sequence.yaml', help='Training config YAML')
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def compute_metrics(logits: torch.Tensor, labels: torch.Tensor, threshold: float) -> dict[str, float]:
    probs = torch.sigmoid(logits)
    preds = (probs >= threshold).long()
    tp = int(((preds == 1) & (labels == 1)).sum().item())
    fp = int(((preds == 1) & (labels == 0)).sum().item())
    fn = int(((preds == 0) & (labels == 1)).sum().item())
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    acc = safe_div(int((preds == labels).sum().item()), int(labels.numel()))
    return {
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'accuracy': acc,
    }


def evaluate(model: nn.Module, loader: DataLoader, device: str, threshold: float) -> tuple[float, dict[str, float]]:
    model.eval()
    total_loss = 0.0
    total_count = 0
    criterion = nn.BCEWithLogitsLoss()
    logits_all: list[torch.Tensor] = []
    labels_all: list[torch.Tensor] = []
    with torch.inference_mode():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb.float())
            total_loss += float(loss.item()) * int(xb.size(0))
            total_count += int(xb.size(0))
            logits_all.append(logits.cpu())
            labels_all.append(yb.cpu())
    if not logits_all:
        return 0.0, {'tp': 0, 'fp': 0, 'fn': 0, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0, 'accuracy': 0.0}
    logits_cat = torch.cat(logits_all)
    labels_cat = torch.cat(labels_all)
    metrics = compute_metrics(logits_cat, labels_cat, threshold=threshold)
    return safe_div(total_loss, total_count), metrics


def main() -> None:
    args = parse_args()
    cfg_path = (PROJECT_ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = load_yaml(cfg_path)

    data_cfg = cfg.get('data', {})
    train_cfg = cfg.get('train', {})
    model_cfg_raw = cfg.get('model', {})
    output_cfg = cfg.get('output', {})

    dataset_path = (PROJECT_ROOT / data_cfg.get('dataset', 'data/processed/urfall_pose_sequences.npz')).resolve()
    ckpt_path = (PROJECT_ROOT / output_cfg.get('checkpoint', 'models/fall_sequence_lstm.pt')).resolve()
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    history_path = ckpt_path.with_suffix('.history.json')
    init_ckpt_raw = train_cfg.get('init_checkpoint')
    init_ckpt_path = None
    if init_ckpt_raw:
        init_ckpt_path = (PROJECT_ROOT / init_ckpt_raw).resolve() if not Path(init_ckpt_raw).is_absolute() else Path(init_ckpt_raw)

    blob = np.load(dataset_path, allow_pickle=True)
    x = blob['x'].astype(np.float32)
    y = blob['y'].astype(np.int64)
    split = blob['split'].astype(str)
    seq_len = int(blob['seq_len'][0]) if 'seq_len' in blob else int(x.shape[1])

    x_train = x[split == 'train']
    y_train = y[split == 'train']
    x_val = x[split == 'val']
    y_val = y[split == 'val']
    if len(x_train) == 0 or len(x_val) == 0:
        raise SystemExit('Dataset split is empty. Rebuild dataset with both train and val samples.')

    feature_dim = int(x.shape[-1])
    device = normalize_torch_device(train_cfg.get('device', 'cpu'), cuda_available=torch.cuda.is_available())
    if device != 'cpu' and not torch.cuda.is_available():
        print('[warn] CUDA unavailable, fallback to CPU')
        device = 'cpu'

    model_cfg = PoseFallModelConfig(
        feature_dim=feature_dim,
        model_type=str(model_cfg_raw.get('type', model_cfg_raw.get('model_type', 'lstm'))),
        hidden_dim=int(model_cfg_raw.get('hidden_dim', 128)),
        num_layers=int(model_cfg_raw.get('num_layers', 2)),
        dropout=float(model_cfg_raw.get('dropout', 0.2)),
        bidirectional=bool(model_cfg_raw.get('bidirectional', False)),
        tcn_kernel_size=int(model_cfg_raw.get('tcn_kernel_size', 3)),
    )
    model = build_pose_fall_model(model_cfg).to(device)
    if init_ckpt_path is not None:
        checkpoint = torch.load(init_ckpt_path, map_location=device)
        checkpoint_cfg = dict(checkpoint.get('model_cfg', {}))
        if checkpoint_cfg and checkpoint_cfg != model_cfg.__dict__:
            raise SystemExit(
                f"Checkpoint model_cfg does not match current config: {init_ckpt_path}\n"
                f"checkpoint={checkpoint_cfg}\ncurrent={model_cfg.__dict__}"
            )
        model.load_state_dict(checkpoint['model_state'])
        print(f'[init] loaded checkpoint from {init_ckpt_path}')

    batch_size = int(train_cfg.get('batch_size', 64))
    epochs = int(train_cfg.get('epochs', 20))
    learning_rate = float(train_cfg.get('learning_rate', 1e-3))
    weight_decay = float(train_cfg.get('weight_decay', 1e-4))
    threshold = float(train_cfg.get('threshold', 0.5))

    pos_count = max(1, int((y_train == 1).sum()))
    neg_count = max(1, int((y_train == 0).sum()))
    pos_weight_value = float(train_cfg.get('pos_weight', neg_count / pos_count))

    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(x_val), torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_value], device=device))

    best_f1 = -math.inf
    history: list[dict[str, Any]] = []

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss_sum = 0.0
        train_count = 0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb.float())
            loss.backward()
            optimizer.step()
            train_loss_sum += float(loss.item()) * int(xb.size(0))
            train_count += int(xb.size(0))

        train_loss = safe_div(train_loss_sum, train_count)
        val_loss, val_metrics = evaluate(model, val_loader, device=device, threshold=threshold)
        row = {
            'epoch': epoch,
            'train_loss': train_loss,
            'val_loss': val_loss,
            **val_metrics,
        }
        history.append(row)
        print(
            f"[epoch {epoch:03d}] train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
            f"precision={val_metrics['precision']:.4f} recall={val_metrics['recall']:.4f} f1={val_metrics['f1']:.4f}"
        )

        if val_metrics['f1'] > best_f1:
            best_f1 = float(val_metrics['f1'])
            checkpoint = {
                'model_state': model.state_dict(),
                'model_cfg': model_cfg.__dict__,
                'feature_dim': feature_dim,
                'seq_len': seq_len,
                'threshold': threshold,
                'train_cfg': dict(train_cfg),
                'metrics': val_metrics,
            }
            if init_ckpt_path is not None:
                checkpoint['init_checkpoint'] = str(init_ckpt_path)
            torch.save(checkpoint, ckpt_path)
            history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'[best] checkpoint saved to {ckpt_path}')

    print(f'[done] best_f1={best_f1:.4f}')
    print(f'[done] history={history_path}')


if __name__ == '__main__':
    main()
