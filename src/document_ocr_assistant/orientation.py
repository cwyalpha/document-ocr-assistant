from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import OcrBlock, PageOrientation
from .runtime import find_orientation_model


@dataclass(frozen=True, slots=True)
class OrientationResult:
    image: np.ndarray
    detected_angle: int
    applied_angle: int
    confidence: float
    original_height: int
    original_width: int
    warning: str = ""


class OrientationEngine:
    """Four-way document orientation classifier backed by ONNX Runtime."""

    LABELS = (0, 90, 180, 270)

    def __init__(self) -> None:
        self._session: Any = None
        self._input_name = ""
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return find_orientation_model() is not None

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        with self._lock:
            if self._session is not None:
                return self._session
            model = find_orientation_model()
            if not model:
                raise FileNotFoundError("未找到四方向页面检测模型。")
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(model), providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            return self._session

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        import cv2

        height, width = image.shape[:2]
        scale = 256.0 / max(1, min(height, width))
        resized = cv2.resize(
            image,
            (max(224, round(width * scale)), max(224, round(height * scale))),
            interpolation=cv2.INTER_LANCZOS4,
        )
        height, width = resized.shape[:2]
        top = (height - 224) // 2
        left = (width - 224) // 2
        cropped = resized[top : top + 224, left : left + 224]
        rgb = cropped[:, :, ::-1].astype(np.float32) / 255.0
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (rgb - mean) / std
        return normalized.transpose(2, 0, 1)[None].astype(np.float32)

    def classify(self, image: np.ndarray) -> tuple[int, float]:
        session = self._ensure_session()
        with self._lock:
            logits = np.asarray(
                session.run(None, {self._input_name: self._preprocess(image)})[0]
            )[0]
        logits = logits - float(np.max(logits))
        probabilities = np.exp(logits)
        probabilities /= max(float(np.sum(probabilities)), 1e-12)
        index = int(np.argmax(probabilities))
        return self.LABELS[index], float(probabilities[index])

    def orient(
        self,
        image: np.ndarray,
        mode: PageOrientation,
        confidence_threshold: float,
    ) -> OrientationResult:
        height, width = image.shape[:2]
        detected = 0
        confidence = 1.0
        warning = ""
        if mode is PageOrientation.AUTO:
            if not self.available:
                return OrientationResult(
                    image,
                    0,
                    0,
                    0.0,
                    height,
                    width,
                    "页面方向模型不可用，已按原方向识别。",
                )
            detected, confidence = self.classify(image)
            applied = detected if confidence >= confidence_threshold else 0
            if applied == 0 and detected != 0:
                warning = (
                    f"页面方向置信度较低（{confidence:.1%}），未自动旋转；"
                    "可在识别选项中手动指定角度。"
                )
        elif mode is PageOrientation.OFF:
            applied = 0
        else:
            applied = int(mode.value)
            detected = applied
        rotated = rotate_image(image, applied)
        return OrientationResult(
            rotated,
            detected,
            applied,
            confidence,
            height,
            width,
            warning,
        )


def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    normalized = angle % 360
    if normalized == 0:
        return image
    return np.rot90(image, k=normalized // 90).copy()


def point_to_original(
    x: float, y: float, angle: int, original_width: int, original_height: int
) -> tuple[float, float]:
    normalized = angle % 360
    if normalized == 90:
        return original_width - 1 - y, x
    if normalized == 180:
        return original_width - 1 - x, original_height - 1 - y
    if normalized == 270:
        return y, original_height - 1 - x
    return x, y


def blocks_to_original(
    blocks: list[OcrBlock], result: OrientationResult
) -> list[OcrBlock]:
    if result.applied_angle == 0:
        return blocks
    restored: list[OcrBlock] = []
    for block in blocks:
        polygon = [
            list(
                point_to_original(
                    point[0],
                    point[1],
                    result.applied_angle,
                    result.original_width,
                    result.original_height,
                )
            )
            for point in block.polygon
        ]
        restored.append(OcrBlock(block.text, polygon, block.score, block.page_index))
    return restored
