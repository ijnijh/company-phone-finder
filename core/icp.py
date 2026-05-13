"""ICP(이상적 고객 프로필) 점수 계산.

`data/icp_keywords.yaml` 사전을 로드해 카테고리·제목 텍스트에 대한 점수를 산출한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


_DEFAULT_YAML = Path(__file__).resolve().parents[1] / "data" / "icp_keywords.yaml"


@dataclass
class IcpConfig:
    positive: dict[str, list[str]] = field(default_factory=dict)
    negative: dict[str, list[str]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def positive_flat(self) -> list[str]:
        return [kw for group in self.positive.values() for kw in group]

    @property
    def negative_flat(self) -> list[str]:
        return [kw for group in self.negative.values() for kw in group]

    def w(self, name: str, default: float = 0.0) -> float:
        return float(self.weights.get(name, default))

    def t(self, name: str, default: float = 0.0) -> float:
        return float(self.thresholds.get(name, default))


def load_config(path: Path | str | None = None) -> IcpConfig:
    p = Path(path) if path else _DEFAULT_YAML
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return IcpConfig(
        positive=data.get("positive", {}) or {},
        negative=data.get("negative", {}) or {},
        weights=data.get("weights", {}) or {},
        thresholds=data.get("thresholds", {}) or {},
    )


def score_category(text: str, config: IcpConfig) -> tuple[float, list[str], list[str]]:
    """텍스트(보통 category + title)에 대한 ICP 점수.

    Returns:
        (score, matched_positive, matched_negative)
    """
    if not text:
        return 0.0, [], []
    matched_pos: list[str] = []
    matched_neg: list[str] = []
    for kw in config.positive_flat:
        if kw and kw in text:
            matched_pos.append(kw)
    for kw in config.negative_flat:
        if kw and kw in text:
            matched_neg.append(kw)
    score = (
        len(matched_pos) * config.w("icp_positive", 3.0)
        + len(matched_neg) * config.w("icp_negative", -3.0)
    )
    return score, matched_pos, matched_neg
