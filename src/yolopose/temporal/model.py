from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import nn


@dataclass
class PoseFallModelConfig:
    feature_dim: int
    model_type: str = 'lstm'
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.2
    bidirectional: bool = False
    tcn_kernel_size: int = 3


class Chomp1d(nn.Module):
    def __init__(self, chomp_size: int):
        super().__init__()
        self.chomp_size = int(chomp_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.chomp_size <= 0:
            return x
        return x[:, :, :-self.chomp_size].contiguous()


class TemporalBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        padding = (kernel_size - 1) * dilation
        self.net = nn.Sequential(
            nn.Conv1d(in_channels, out_channels, kernel_size, padding=padding, dilation=dilation),
            Chomp1d(padding),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Conv1d(out_channels, out_channels, kernel_size, padding=padding, dilation=dilation),
            Chomp1d(padding),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
        )
        self.downsample = nn.Conv1d(in_channels, out_channels, kernel_size=1) if in_channels != out_channels else None
        self.out_relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x if self.downsample is None else self.downsample(x)
        return self.out_relu(self.net(x) + residual)


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


class PoseFallTCN(nn.Module):
    def __init__(self, cfg: PoseFallModelConfig):
        super().__init__()
        self.cfg = cfg
        blocks: list[nn.Module] = []
        in_channels = cfg.feature_dim
        for idx in range(int(cfg.num_layers)):
            dilation = 2 ** idx
            blocks.append(
                TemporalBlock(
                    in_channels=in_channels,
                    out_channels=cfg.hidden_dim,
                    kernel_size=int(cfg.tcn_kernel_size),
                    dilation=dilation,
                    dropout=float(cfg.dropout),
                )
            )
            in_channels = cfg.hidden_dim
        self.tcn = nn.Sequential(*blocks)
        self.classifier = nn.Sequential(
            nn.LayerNorm(cfg.hidden_dim),
            nn.Linear(cfg.hidden_dim, cfg.hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.transpose(1, 2)
        seq_out = self.tcn(x)
        last = seq_out[:, :, -1]
        logits = self.classifier(last)
        return logits.squeeze(-1)


def build_pose_fall_model(cfg: PoseFallModelConfig) -> nn.Module:
    model_type = str(cfg.model_type).lower()
    if model_type == 'lstm':
        return PoseFallLSTM(cfg)
    if model_type == 'tcn':
        return PoseFallTCN(cfg)
    raise ValueError(f'Unsupported model_type: {cfg.model_type}')


def load_pose_fall_model_from_checkpoint(checkpoint: dict[str, Any]) -> nn.Module:
    model_cfg_dict = dict(checkpoint.get('model_cfg', {}))
    model_cfg_dict.setdefault('model_type', 'lstm')
    model_cfg = PoseFallModelConfig(**model_cfg_dict)
    model = build_pose_fall_model(model_cfg)
    model.load_state_dict(checkpoint['model_state'])
    return model
