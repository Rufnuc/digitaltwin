"""OCR / Document-AI provider abstraction (spec §12, Phase 5).

We never build OCR/handwriting recognition ourselves — commercial Document-AI
providers (Google Document AI, AWS Textract, Azure) plug in behind this seam.
Phase 1 defines the interface and data shapes only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ExtractedField:
    name: str
    value: str
    confidence: float


@dataclass
class OCRResult:
    raw_text: str
    fields: list[ExtractedField] = field(default_factory=list)
    overall_confidence: float = 0.0
    provider: str = "none"


class OCRProvider(Protocol):
    def extract(self, data: bytes, content_type: str) -> OCRResult: ...


class NullOCRProvider:
    def extract(self, data: bytes, content_type: str) -> OCRResult:
        raise NotImplementedError(
            "OCR provider not configured. Document extraction is a Phase 5 capability."
        )


def get_ocr_provider() -> OCRProvider:
    return NullOCRProvider()
