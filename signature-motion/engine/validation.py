"""Dependency-free validation at the renderer/agent boundary."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
TEMPLATE_IDS = ("type-impact", "redline", "signal", "flow-state", "prism", "after-hours")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
TOP_FIELDS = {"schema_version", "template", "width", "height", "fps", "duration", "seed", "brand", "palette", "content", "demo"}


class ConfigError(ValueError):
    """A configuration violates the public render contract."""


def _fail(path: str, message: str) -> None:
    raise ConfigError(f"{path}: {message}")


def _object(value, path: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing:
        _fail(path, f"missing fields: {', '.join(sorted(missing))}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(sorted(extra))}")
    return value


def _text(value, path: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a nonempty string")
    if len(value) > maximum:
        _fail(path, f"must contain at most {maximum} characters")
    if any(ord(char) < 32 for char in value):
        _fail(path, "must not contain line breaks or control characters")


def _texts(value, path: str, minimum: int, maximum: int, chars: int) -> None:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail(path, f"must contain {minimum}..{maximum} strings")
    for index, item in enumerate(value):
        _text(item, f"{path}[{index}]", chars)


def _url(value, path: str) -> None:
    _text(value, path, 2048)
    try:
        parts = urlsplit(value)
        valid = parts.scheme in {"http", "https"} and bool(parts.hostname) and not parts.username and not parts.password
        _ = parts.port
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in value):
        _fail(path, "must be an HTTP(S) source URL without credentials")


def frame_count(config: dict) -> int:
    """Calculate the exact frame count from decimal configuration values."""
    try:
        frames = Decimal(str(config["duration"])) * Decimal(str(config["fps"]))
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise ConfigError("duration/fps: invalid frame timing") from exc
    if not frames.is_finite() or frames != frames.to_integral_value():
        _fail("duration", "must end on a whole frame at the selected fps")
    return int(frames)


def canonical_json(config: dict) -> str:
    """Stable serialization for render provenance, independent of key order."""
    try:
        return json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config: cannot serialize as strict JSON: {exc}") from exc


def config_hash(config: dict) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def local_file(value: str, base_dir: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        _fail(field, "must be a nonempty local file path")
    if "://" in value or value.lower().startswith(("data:", "file:", "http:", "https:")):
        _fail(field, "must be a local path; network and data URLs are not supported")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    try:
        path = path.resolve(strict=True)
        if not path.is_file():
            _fail(field, "must identify a regular file")
        with path.open("rb") as stream:
            if not stream.read(1):
                _fail(field, "file is empty")
    except (OSError, RuntimeError) as exc:
        raise ConfigError(f"{field}: cannot read local file {value!r}: {exc}") from exc
    return path


def validate_config(config: dict, base_dir: str | Path | None = None) -> dict:
    """Return an independent validated configuration with absolute asset paths.

    This routine uses only the Python standard library. Image decoding is checked
    immediately before drawing, so `--validate` does not require Pillow.
    """
    _object(config, "config", TOP_FIELDS)
    if type(config["schema_version"]) is not int or config["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", "must be 1")
    if config["template"] not in TEMPLATE_IDS:
        _fail("template", f"must be one of {', '.join(TEMPLATE_IDS)}")
    for name in ("width", "height"):
        if type(config[name]) is not int or config[name] < 144 or config[name] % 2:
            _fail(name, "must be an even integer of at least 144 pixels")
    width, height = config["width"], config["height"]
    if not ((width * 16 == height * 9 and width <= 1080 and height <= 1920)
            or (width * 9 == height * 16 and width <= 1920 and height <= 1080)
            or (width == height and width <= 1080)):
        _fail("width/height", "must be 9:16, 16:9, or 1:1 at or below 1080x1920, 1920x1080, or 1080x1080")
    if type(config["fps"]) is not int or config["fps"] not in {24, 25, 30, 60}:
        _fail("fps", "must be 24, 25, 30, or 60")
    duration = config["duration"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 6 <= duration <= 30 or not math.isfinite(duration):
        _fail("duration", "must be a finite number between 6 and 30 seconds")
    frame_count(config)
    if type(config["seed"]) is not int or not 0 <= config["seed"] <= 4294967295:
        _fail("seed", "must be an unsigned 32-bit integer")
    if type(config["demo"]) is not bool:
        _fail("demo", "must be a boolean")
    _text(config["brand"], "brand", 24)
    palette = _object(config["palette"], "palette", {"background", "foreground", "accent"})
    for name, color in palette.items():
        if not isinstance(color, str) or not HEX.fullmatch(color):
            _fail(f"palette.{name}", "must use #RRGGBB hexadecimal color")
    template = config["template"]
    content = config["content"]
    if template == "type-impact":
        _object(content, "content", {"headline", "subhead", "cta"})
        _texts(content["headline"], "content.headline", 2, 3, 18)
        fields = {"subhead": 100, "cta": 32}
    elif template == "redline":
        _object(content, "content", {"headline", "quote", "source", "verdict"}, {"source_url"})
        fields = {"headline": 42, "quote": 140, "source": 80, "verdict": 44}
    elif template == "signal":
        _object(content, "content", {"headline", "series", "unit", "source", "takeaway"}, {"source_url"})
        fields = {"headline": 42, "unit": 16, "source": 80, "takeaway": 60}
        series = content["series"]
        if not isinstance(series, list) or not 3 <= len(series) <= 8:
            _fail("content.series", "must contain 3..8 data points")
        for index, item in enumerate(series):
            _object(item, f"content.series[{index}]", {"label", "value"})
            _text(item["label"], f"content.series[{index}].label", 12)
            number = item["value"]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= 1e15 or not math.isfinite(number):
                _fail(f"content.series[{index}].value", "must be finite and between 0 and 1e15")
    elif template == "flow-state":
        _object(content, "content", {"headline", "steps", "before_label", "after_label", "subhead"})
        _texts(content["steps"], "content.steps", 3, 4, 24)
        fields = {"headline": 42, "before_label": 24, "after_label": 24, "subhead": 70}
    elif template == "prism":
        _object(content, "content", {"headline", "cards", "subhead"}, {"assets"})
        _texts(content["headline"], "content.headline", 2, 2, 18)
        _texts(content["cards"], "content.cards", 3, 3, 18)
        fields = {"subhead": 80}
    else:
        _object(content, "content", {"title", "subtitle", "badge", "cta"})
        _texts(content["title"], "content.title", 2, 2, 18)
        fields = {"subtitle": 64, "badge": 18, "cta": 32}
    for name, maximum in fields.items():
        _text(content[name], f"content.{name}", maximum)
    if template in {"redline", "signal"} and not config["demo"] and "source_url" not in content:
        _fail("content.source_url", "is required for non-demo evidence")
    if "source_url" in content:
        _url(content["source_url"], "content.source_url")
    result = copy.deepcopy(config)
    if template == "prism" and "assets" in content:
        paths = content["assets"]
        if not isinstance(paths, list) or len(paths) != 3:
            _fail("content.assets", "must contain exactly 3 local image paths")
        root = Path(base_dir or Path.cwd())
        resolved = []
        for index, value in enumerate(paths):
            path = local_file(value, root, f"content.assets[{index}]")
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                _fail(f"content.assets[{index}]", "must be a PNG, JPEG, or WebP image")
            resolved.append(str(path))
        result["content"]["assets"] = resolved
    canonical_json(result)
    return result


def load_config(path: str | Path) -> tuple[dict, dict]:
    """Return the exact submitted object and validated runtime object."""
    source = Path(path).resolve()
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConfigError(f"config: duplicate JSON key {key!r}")
            result[key] = value
        return result
    try:
        raw = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates,
                         parse_constant=lambda value: (_ for _ in ()).throw(ConfigError(f"config: invalid JSON number {value}")))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError(f"config: cannot read {source}: {exc}") from exc
    return raw, validate_config(raw, source.parent)


def preview_config(config: dict, scale: float) -> dict:
    if not math.isfinite(scale) or not 0 < scale <= 1:
        _fail("preview", "scale must be greater than 0 and at most 1")
    result = copy.deepcopy(config)
    width, height = config["width"], config["height"]
    base_w, base_h = (18, 32) if width < height else ((32, 18) if width > height else (2, 2))
    steps = max(math.ceil(144 / min(base_w, base_h)), round(width * scale / base_w))
    result["width"], result["height"] = base_w * steps, base_h * steps
    return result
