"""Lokālie OCR dzinēji.

- AppleVisionEngine: macOS iebūvētais Vision (labākais rokrakstam uz Mac).
- RapidOcrEngine: RapidOCR (PaddleOCR modeļi caur ONNX), darbojas visur.

Abi atgriež vārdu sarakstu ar koordinātām attēla pikseļos.
"""

from __future__ import annotations

import io
import logging
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class Word:
    text: str
    conf: float
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 (augšējais kreisais = 0,0)
    alts: list[str] = field(default_factory=list)


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._ocr = RapidOCR()

    def read(self, img: Image.Image) -> list[Word]:
        result, _ = self._ocr(np.asarray(img.convert("RGB")))
        words = []
        for box, text, conf in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            words.append(Word(text, float(conf), (min(xs), min(ys), max(xs), max(ys))))
        return words

    def read_line(self, img: Image.Image) -> list[Word]:
        """Nolasa attēlu kā vienu teksta rindu (bez teksta meklēšanas)."""
        img = img.convert("RGB")
        if img.height != 48:
            img = img.resize((max(1, img.width * 48 // img.height), 48))
        result, _ = self._ocr(np.asarray(img), use_det=False, use_cls=False)
        return [Word(t, float(c), (0, 0, img.width, img.height)) for t, c in result or []]


class AppleVisionEngine:
    name = "apple-vision"

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("Apple Vision ir pieejams tikai macOS")
        import Vision  # type: ignore  # pyobjc-framework-Vision
        from Foundation import NSData  # type: ignore

        self._vision = Vision
        self._nsdata = NSData
        self._languages = self._pick_languages()

    def _pick_languages(self) -> list[str]:
        req = self._vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(self._vision.VNRequestTextRecognitionLevelAccurate)
        try:
            supported, _ = req.supportedRecognitionLanguagesAndReturnError_(None)
            supported = [str(s) for s in supported or []]
        except Exception:  # vecākas macOS versijas
            supported = []
        wanted = [lang for lang in ("lv-LV", "en-US") if lang in supported]
        return wanted or ["en-US"]

    def _run(self, img: Image.Image) -> list[Word]:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        raw = buf.getvalue()
        data = self._nsdata.dataWithBytes_length_(raw, len(raw))
        handler = self._vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        req = self._vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(self._vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(False)
        req.setRecognitionLanguages_(self._languages)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            raise RuntimeError(f"Vision kļūda: {err}")
        width, height = img.size
        words = []
        for obs in req.results() or []:
            cands = obs.topCandidates_(3)
            if not cands:
                continue
            bb = obs.boundingBox()  # normalizēts, sākumpunkts apakšējā kreisajā stūrī
            x0 = bb.origin.x * width
            y0 = (1 - bb.origin.y - bb.size.height) * height
            x1 = x0 + bb.size.width * width
            y1 = y0 + bb.size.height * height
            words.append(Word(
                str(cands[0].string()),
                float(cands[0].confidence()),
                (x0, y0, x1, y1),
                alts=[str(c.string()) for c in list(cands)[1:]],
            ))
        return words

    def read(self, img: Image.Image) -> list[Word]:
        return self._run(img)

    def read_line(self, img: Image.Image) -> list[Word]:
        # Vision pats atrod tekstu; mazam attēlam pievienojam baltu apmali.
        padded = Image.new("RGB", (img.width + 40, img.height + 40), "white")
        padded.paste(img.convert("RGB"), (20, 20))
        return self._run(padded)


def available_engines(preferred: str = "auto") -> list:
    """Atgriež pieejamos dzinējus. 'auto' = visi pieejamie (rezultāti tiek apvienoti)."""
    order = {
        "auto": [AppleVisionEngine, RapidOcrEngine],
        "vision": [AppleVisionEngine],
        "rapidocr": [RapidOcrEngine],
    }.get(preferred, [AppleVisionEngine, RapidOcrEngine])
    engines = []
    for cls in order:
        try:
            engines.append(cls())
        except Exception as exc:  # dzinējs nav instalēts vai nav šajā OS
            log.info("OCR dzinējs %s nav pieejams: %s", cls.__name__, exc)
    if not engines:
        raise RuntimeError(
            "Nav pieejams neviens OCR dzinējs. Instalējiet rapidocr-onnxruntime "
            "vai (uz Mac) pyobjc-framework-Vision."
        )
    return engines
