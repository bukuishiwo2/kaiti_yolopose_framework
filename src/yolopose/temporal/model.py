from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import nn


@dataclass
class PoseFallModelConfig:
    feature_dim: int
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.2
    bidirectional: bool = False


class PoseFallLSTM(nn.Module):
    def __init__(self, cfg: PoseFallModelConfig):
        super().__init__()
        self.cfg = cfg
        lstm_dropout = cfg.dropout if cfg.num_layers > 1 else 0.0
        self.lstm = nn.LSTM(
            input_size=cfg.feature_dim,
            hidden_size=cfg.hidden_dim,
            num_layers=cfg.num_layers,
            dropout=lstm_dropout,
            batch_first=True,
            bidirectional=cfg.bidirectional,
        )
        out_dim = cfg.hidden_dim * (2 if cfg.bidirectional else 1)
        self.classifier = nn.Sequential(
            nn.LayerNorm(out_dim),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(cfg.dropout),
            nn.Linear(out_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        seq_out, _ = self.lstm(x)
        last = seq_out[:, -1, :]
        logits = self.classifier(last)
        return logits.squeeze(-1)

    @classmethod
    def from_checkpoint(cls, checkpoint: dict[str, Any]) -> 'PoseFallLSTM':
        model_cfg = PoseFallModelConfig(**checkpoint['model_cfg'])
        model = cls(model_cfg)
        model.load_state_dict(checkpoint['model_state'])
        return model
