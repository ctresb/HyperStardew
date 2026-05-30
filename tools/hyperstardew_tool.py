#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import os
import random
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MOD_DIR = REPO_ROOT / "3-HyperStardew"
DEFAULT_SOURCE_ROOT = Path(
    os.environ.get(
        "HYPERSTARDEW_SOURCE_ROOT",
        "/Users/joaodavisn/Library/Application Support/Steam/steamapps/common/"
        "Stardew Valley/Contents/MacOS/Content (unpacked)",
    )
)
CACHE_PATH = Path(os.environ.get("HYPERSTARDEW_CACHE", REPO_ROOT / "tools" / "hyper_cache.sqlite"))
REPORT_DIR = REPO_ROOT / "tools" / "reports"

LANGS = [
    "ja", "ko", "zh-CN", "ar", "he", "hi", "th", "bn", "ta", "ml",
    "my", "km", "lo", "si", "ne", "ur", "fa", "am", "ka", "hy",
    "el", "ru", "uk", "fi", "hu", "tr", "kk", "vi", "sw", "is",
]
DEFAULT_HOPS = 25
DEFAULT_ATTEMPTS = 3
DEFAULT_WORKERS = 25
HOP_RETRIES = 4
CACHE_NAMESPACE = f"hops{DEFAULT_HOPS}-repair-v3"
FREEGTX_BACKEND_NAME = "freegtx"
SUPER_CACHE_NAMESPACE = f"hops{DEFAULT_HOPS}-freegtx-v2"
SIMILARITY_CACHE_NAMESPACE = f"hops{DEFAULT_HOPS}-similarity-v1"
FREEGTX_HOP_CACHE_NAMESPACE = "freegtx-hop-v1"
VALID_CACHE_PREFIX = f"hops{DEFAULT_HOPS}-"
SIMILARITY_THRESHOLD = 0.94
DEFAULT_SIMILARITY_REPAIR_THRESHOLD = 0.60
DEFAULT_SIMILARITY_REPAIR_NGRAM = 3
DEFAULT_SIMILARITY_MIN_WORDS = 8
MIN_SIMILAR_CHARS = 12
MIN_DISTINCT_HYPER_ALPHA = 40
MIN_DISTINCT_HYPER_WORDS = 6
MIN_NEAR_ORIGINAL_ALPHA = 60
MIN_NEAR_ORIGINAL_WORDS = 8
MANUAL_QUEUE_LIMIT_MD = 250
SUPER_REPAIR_MAX_PASSES = 3
SUPER_IDENTITY_RESCUE_ROUTES = 8
FREEGTX_MAX_IN_FLIGHT_HTTP = int(os.environ.get("HYPERSTARDEW_MAX_HTTP", "8"))
FREEGTX_MAX_QPS = float(os.environ.get("HYPERSTARDEW_MAX_QPS", "10"))
FREEGTX_TIMEOUT = float(os.environ.get("HYPERSTARDEW_HTTP_TIMEOUT", "10"))
FREEGTX_HOP_CACHE = os.environ.get("HYPERSTARDEW_HOP_CACHE", "1") != "0"
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
SUPER_CACHE_ROUTE_KINDS = ("normal", "identity_rescue", "stubborn_short_rescue")
STUBBORN_SHORT_ALPHA_MAX = 28

TRIVIAL_HUMAN_TEXTS = {
    "sim", "não", "nao", "ok", "okay", "oi", "olá", "ola", "ah", "hã",
    "ha", "hm", "hmm", "uh", "hum", "hic",
}
TRANSLATE_SMOKE_TERMS = [
    "Pizza",
    "Bolo de Chocolate",
    "Algas Verdes",
    "Obsidiana",
    "Minério de Cobre",
    "Não, obrigado",
    "Tênis",
    "Arqueologia",
    "Chapéu de Dinossauro",
    "Orelhas de Gato",
    "Café da manhã completo",
    "Dentes Afiados",
    "Máscara de Pássaro Azul",
    "Sapatos Mágicos",
    "Manga",
    "Use isto para atrair mais monstros.",
    "Estou com fome.",
    "Você está aqui!",
    "O que você está fazendo aqui?",
    "Minério de Ferro",
]
HIGH_RISK_CHARS = set("$#|_/%@{}[]^\"'")
STRATIFIED_BUCKETS = (
    ("Characters/Dialogue", "Characters/Dialogue/"),
    ("Data/Events", "Data/Events/"),
    ("Data/Festivals", "Data/Festivals/"),
    ("Strings", "Strings/"),
    ("Data", "Data/"),
)

EVENT_COMMANDS = {
    "action", "addBigProp", "addConversationTopic", "addCookingRecipe",
    "addCraftingRecipe", "addFloorObject", "addItem", "addLantern",
    "addMailReceived", "addObject", "addProp", "addQuest", "addSpecialOrder",
    "addTemporaryActor", "addToTable", "advancedMove", "ambientLight",
    "animate", "animationFrame", "attachCharacterToTempSprite", "awardFestivalPrize",
    "background", "bgColor", "boardPlayer", "broadcastMail", "catQuestion",
    "cave", "changeLocation", "changeMapTile", "changeName", "changePortrait",
    "changeSprite", "changeToTemporaryMap", "changeYSourceRectOffset",
    "characterSelect", "cutscene", "doAction", "drawOffset", "elliotbooktalk",
    "emote", "end", "eventSeen", "extendSourceRect", "eyes", "faceDirection",
    "fade", "farmerAnimation", "farmerEat", "fork", "friendship", "globalFade",
    "globalFadeToClear", "glow", "grandpaCandles", "grandpaEvaluation",
    "grandpaEvaluation2", "halt", "hideShadow", "hostMail", "ignoreCollisions",
    "ignoreEventTileOffset", "ignoreMovementAnimation", "itemAboveHead", "jump",
    "loadActors", "mail", "mailReceived", "makeInvisible", "mapMarker",
    "message", "minedig", "money", "move", "musicVolume", "nameSelect",
    "pause", "playMusic", "playSound", "playerControl", "positionOffset",
    "proceedPosition", "question", "quickQuestion", "removeItem",
    "removeQuest", "removeSprite", "removeTemporarySprites", "removeTile",
    "replaceWithClone", "resetVariable", "rustyKey", "screenFlash", "setRunning",
    "setSkipActions", "shake", "showFrame", "showRivalFrame", "skippable",
    "speak", "specificTemporarySprite", "splitSpeak", "startJittering",
    "stopAdvancedMoves", "stopAnimation", "stopGlowing", "stopJittering",
    "stopMusic", "stopRunning", "stopSound", "stopSwimming", "swimming",
    "switchEvent", "taxvote", "temporaryAnimatedSprite", "temporarySprite",
    "textAboveHead", "tossConcession", "tutorialMenu", "updateMinigame",
    "viewport", "wait", "waitForAllStationary", "waitForOtherPlayers",
    "warp", "warpFarmers", "weddingSprite",
}

SLASH_FIELD_RULES = {
    "Data/Quests.json": {1: "prose", 2: "prose", 3: "prose"},
    "Data/Bundles.json": {-1: "prose"},
    "Data/Boots.json": {-1: "prose"},
    "Data/hats.json": {5: "prose"},
    "Data/Monsters.json": {-1: "prose"},
}
CARET_FIELD_RULES = {"Data/Achievements.json": {0: "prose", 1: "prose"}}

BARE_MAIL_TOKEN = re.compile(
    r"%(?:secretsanta|farm|name|pet|fork|kid1|kid2|adj|noun|place|"
    r"spouse|time|season|band|book|rival|dish|firstnameletter|"
    r"favorite|endearment|endearmentlower)\b"
)
DIALOGUE_COMMAND = re.compile(r"([#|]?)\$[dqrpkc1] [^#\n]*#")
EXTRA_COMMAND_HASH = re.compile(r"\$[dqrpkc1] [^#\n]*##")
CHOICE_DIALOGUE_COMMAND = re.compile(r"([#|]?)\$([dqrpc])\s([^#\n]*)#")
GENDER_BLOCK = re.compile(r"\$\{([^}^¦]*)[\^¦]([^}]*)\}\$")
EMOTE_STAR = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])\*([^*\n]{1,60})\*(?![A-Za-zÀ-ÿ0-9])")
TRIVIAL_NUMERIC = re.compile(r"^-?\d+(?:[.,]\d+)?$")

TOKEN_PATTERNS = [
    ("mail_item", re.compile(r"%item\s[^%]*%%")),
    ("mail_subject_mark", re.compile(r"\[#\]")),
    ("reveal_taste_token", re.compile(r"%revealtaste:[A-Za-z0-9_]+:\d+")),
    ("percent_token", re.compile(r"%(?!revealtaste:)[a-zA-Z][a-zA-Z0-9_]*(?::[^%\s]+)*%")),
    ("bare_mail_token", BARE_MAIL_TOKEN),
    ("dialogue_command", DIALOGUE_COMMAND),
    ("dialogue_break", re.compile(r"#\$[bekq]#")),
    ("gender_block", re.compile(r"\$\{[^}]*[\^¦][^}]*\}\$")),
    ("cp_token", re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")),
    ("format_slot", re.compile(r"\{\d+\}")),
    ("game_token", re.compile(r"\[[A-Z_][A-Z0-9_]*\]")),
    ("item_ref", re.compile(r"\([A-Z]{1,3}\)[A-Za-z0-9_]+")),
    ("player_name", re.compile(r"@")),
    ("dialogue_mood", re.compile(r"\$\d{1,2}")),
    ("dialogue_code", re.compile(r"(?<!})\$[abcdehklnopqrsuvz]")),
    ("caret", re.compile(r"\^")),
]

@dataclass
class Piece:
    type: str
    value: str = ""
    values: list[str] = field(default_factory=list)


class TranslationError(RuntimeError):
    pass


class TranslationRetryableError(TranslationError):
    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass
class TranslateMetrics:
    requests: int = 0
    retries: int = 0
    failures: int = 0
    cache_hits: int = 0
    cache_writes: int = 0
    rate_limit_waits: int = 0
    rate_limit_wait_seconds: float = 0.0
    total_latency_seconds: float = 0.0
    status_counts: Counter = field(default_factory=Counter)
    error_counts: Counter = field(default_factory=Counter)
    lock: Any = field(default_factory=threading.Lock, repr=False)

    def add_request(self, status: int | str, latency: float) -> None:
        with self.lock:
            self.requests += 1
            self.total_latency_seconds += latency
            self.status_counts[str(status)] += 1

    def add_retry(self, error: str) -> None:
        with self.lock:
            self.retries += 1
            self.error_counts[error] += 1

    def add_failure(self, error: str) -> None:
        with self.lock:
            self.failures += 1
            self.error_counts[error] += 1

    def add_cache_hit(self) -> None:
        with self.lock:
            self.cache_hits += 1

    def add_cache_write(self) -> None:
        with self.lock:
            self.cache_writes += 1

    def add_rate_limit_wait(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self.lock:
            self.rate_limit_waits += 1
            self.rate_limit_wait_seconds += seconds

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "requests": self.requests,
                "retries": self.retries,
                "failures": self.failures,
                "cache_hits": self.cache_hits,
                "cache_writes": self.cache_writes,
                "rate_limit_waits": self.rate_limit_waits,
                "rate_limit_wait_seconds": round(self.rate_limit_wait_seconds, 3),
                "total_latency_seconds": round(self.total_latency_seconds, 3),
                "status_counts": dict(self.status_counts),
                "error_counts": dict(self.error_counts),
            }


@dataclass
class HyperTranslationResult:
    source: str
    target: str
    route_kind: str
    route: list[str]
    hops: int


class TranslateBackend:
    name = "backend"

    def translate(self, text: str, src: str, dst: str) -> str:
        raise NotImplementedError

    def metrics_dict(self) -> dict[str, Any]:
        return {}


class FreeGoogleTranslateBackend(TranslateBackend):
    name = FREEGTX_BACKEND_NAME

    def __init__(
        self,
        max_in_flight_http: int = FREEGTX_MAX_IN_FLIGHT_HTTP,
        max_qps: float = FREEGTX_MAX_QPS,
        timeout: float = FREEGTX_TIMEOUT,
        hop_retries: int = HOP_RETRIES,
        use_hop_cache: bool = FREEGTX_HOP_CACHE,
    ):
        self.max_in_flight_http = max(1, max_in_flight_http)
        self.max_qps = max(0.1, max_qps)
        self.timeout = timeout
        self.hop_retries = max(1, hop_retries)
        self.use_hop_cache = use_hop_cache
        self.semaphore = threading.BoundedSemaphore(self.max_in_flight_http)
        self.rate_lock = threading.Lock()
        self.next_request_at = 0.0
        self.metrics = TranslateMetrics()

    def hop_namespace(self, src: str, dst: str) -> str:
        return f"{FREEGTX_HOP_CACHE_NAMESPACE}:{src}->{dst}"

    def translate(self, text: str, src: str, dst: str) -> str:
        if not text:
            return text
        if self.use_hop_cache:
            cached, _ = cache_get_many([text], namespace=self.hop_namespace(src, dst))
            if text in cached:
                self.metrics.add_cache_hit()
                return cached[text]

        delay = 0.45
        last_error: Exception | None = None
        for attempt in range(1, self.hop_retries + 1):
            try:
                translated = self._translate_once(text, src, dst)
                if self.use_hop_cache and translated:
                    cache_put(text, translated, namespace=self.hop_namespace(src, dst))
                    self.metrics.add_cache_write()
                return translated
            except TranslationRetryableError as exc:
                last_error = exc
                if attempt >= self.hop_retries:
                    break
                self.metrics.add_retry(type(exc).__name__)
                sleep_for = exc.retry_after if exc.retry_after is not None else delay + random.random() * 0.3
                time.sleep(max(0.05, sleep_for))
                delay = min(delay * 1.8, 5.0)
            except Exception as exc:
                last_error = exc
                self.metrics.add_failure(type(exc).__name__)
                raise
        self.metrics.add_failure(type(last_error).__name__ if last_error else "unknown")
        raise TranslationError(f"translate {src}->{dst} failed after {self.hop_retries} retries: {last_error!r}")

    def _wait_for_rate_slot(self) -> None:
        interval = 1.0 / self.max_qps
        with self.rate_lock:
            now = time.monotonic()
            wait = max(0.0, self.next_request_at - now)
            self.next_request_at = max(now, self.next_request_at) + interval
        if wait > 0:
            self.metrics.add_rate_limit_wait(wait)
            time.sleep(wait)

    def _translate_once(self, text: str, src: str, dst: str) -> str:
        self._wait_for_rate_slot()
        params = urllib.parse.urlencode({"client": "gtx", "sl": src, "tl": dst, "dt": "t", "q": text})
        url = "https://translate.googleapis.com/translate_a/single?" + params
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        start = time.monotonic()
        with self.semaphore:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    status = getattr(resp, "status", 200)
            except urllib.error.HTTPError as exc:
                latency = time.monotonic() - start
                status = exc.code
                self.metrics.add_request(status, latency)
                retry_after = parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
                if status in RETRYABLE_HTTP_STATUS:
                    raise TranslationRetryableError(f"http {status}", status=status, retry_after=retry_after) from exc
                raise TranslationError(f"http {status}") from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                latency = time.monotonic() - start
                self.metrics.add_request("transport_error", latency)
                raise TranslationRetryableError(f"transport error: {exc!r}") from exc

        latency = time.monotonic() - start
        self.metrics.add_request(status, latency)
        try:
            data = json.loads(raw)
            translated = "".join(seg[0] for seg in data[0] if seg and seg[0]) if data and data[0] else ""
        except Exception as exc:
            raise TranslationRetryableError(f"invalid json/shape: {exc!r}") from exc
        if not translated:
            raise TranslationRetryableError("empty translation response")
        return translated

    def metrics_dict(self) -> dict[str, Any]:
        data = self.metrics.to_dict()
        data.update({
            "backend": self.name,
            "max_in_flight_http": self.max_in_flight_http,
            "max_qps": self.max_qps,
            "timeout": self.timeout,
            "hop_retries": self.hop_retries,
            "hop_cache": self.use_hop_cache,
        })
        return data

@dataclass
class Context:
    mod_dir: Path
    source_root: Path

    @property
    def hyper_root(self) -> Path:
        return self.mod_dir / "assets" / "i18n_hyper"

    def source_for_rel(self, rel: str) -> Path:
        p = Path(rel)
        return self.source_root / p.with_name(p.stem + ".pt-BR.json")


def is_trivial(text: str) -> bool:
    if not text or not text.strip():
        return True
    if len(text.strip()) == 1:
        return True
    return bool(TRIVIAL_NUMERIC.match(text.strip()))


def reassemble(pieces: list[Piece]) -> str:
    out = []
    for p in pieces:
        if p.type in ("text", "key"):
            out.append(p.value)
        elif p.type == "emote":
            out.append("*" + p.value + "*")
        elif p.type == "gender":
            out.append("${" + p.values[0] + "^" + p.values[1] + "}$")
        else:
            raise ValueError(f"unknown piece type {p.type!r}")
    return "".join(out)


def flush_text(buf: list[str], pieces: list[Piece]) -> None:
    if buf:
        pieces.append(Piece("text", "".join(buf)))
        buf.clear()


def tokenize(text: str) -> list[Piece]:
    pieces: list[Piece] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("$y '", i):
            quote_end = text.find('"', i)
            if quote_end == -1:
                quote_end = len(text)
            end = text.rfind("'", i + 4, quote_end)
            if end != -1:
                flush_text(buf, pieces)
                pieces.append(Piece("key", "$y '"))
                inner = text[i + 4:end]
                for pi, part in enumerate(inner.split("_")):
                    if pi:
                        pieces.append(Piece("key", "_"))
                    pieces.extend(tokenize(part))
                pieces.append(Piece("key", "'"))
                i = end + 1
                continue

        m = GENDER_BLOCK.match(text, i)
        if m:
            flush_text(buf, pieces)
            pieces.append(Piece("gender", values=[m.group(1), m.group(2)]))
            i = m.end()
            continue

        m = EMOTE_STAR.match(text, i)
        if m:
            flush_text(buf, pieces)
            pieces.append(Piece("emote", m.group(1)))
            i = m.end()
            continue

        matched = None
        for name, pattern in TOKEN_PATTERNS:
            m = pattern.match(text, i)
            if m:
                matched = m
                break
        if matched:
            flush_text(buf, pieces)
            pieces.append(Piece("key", matched.group(0)))
            i = matched.end()
            continue

        buf.append(text[i])
        i += 1
    flush_text(buf, pieces)
    return post_process(pieces)


def post_process(pieces: list[Piece]) -> list[Piece]:
    out: list[Piece] = []
    for p in pieces:
        if p.type == "text" and not any(ch.isalpha() for ch in p.value):
            p = Piece("key", p.value)
        if out and out[-1].type == "key" and p.type == "key":
            out[-1].value += p.value
        else:
            out.append(p)
    return [p for p in out if not (p.type == "text" and p.value == "")]


def split_unquoted_slash(value: str) -> list[str]:
    segments = []
    buf = []
    in_quote = False
    for ch in value:
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
        elif ch == "/" and not in_quote:
            segments.append("".join(buf))
            buf.clear()
        else:
            buf.append(ch)
    segments.append("".join(buf))
    return segments


def tokenize_quoted_spans(segment: str) -> list[Piece]:
    pieces: list[Piece] = []
    i = 0
    while i < len(segment):
        qstart = segment.find('"', i)
        if qstart == -1:
            pieces.append(Piece("key", segment[i:]))
            break
        qend = segment.find('"', qstart + 1)
        if qend == -1:
            pieces.append(Piece("key", segment[i:]))
            break
        pieces.append(Piece("key", segment[i:qstart + 1]))
        pieces.extend(tokenize(segment[qstart + 1:qend]))
        pieces.append(Piece("key", '"'))
        i = qend + 1
    return post_process(pieces)


def tokenize_quick_question_segment(segment: str) -> list[Piece]:
    break_pos = segment.find("(break)")
    head = segment if break_pos == -1 else segment[:break_pos]
    tail = "" if break_pos == -1 else segment[break_pos:]
    first_hash = head.find("#")
    if first_hash == -1:
        return tokenize_quoted_spans(segment)

    pieces: list[Piece] = [Piece("key", head[:first_hash + 1])]
    pos = first_hash + 1
    while pos <= len(head):
        next_hash = head.find("#", pos)
        if next_hash == -1:
            option = head[pos:]
            if option:
                pieces.extend(tokenize(option))
            break
        option = head[pos:next_hash]
        if option:
            pieces.extend(tokenize(option))
        pieces.append(Piece("key", "#"))
        pos = next_hash + 1
    if tail:
        pieces.extend(tokenize_quoted_spans(tail))
    return post_process(pieces)


def split_event_script(value: str) -> list[Piece]:
    pieces: list[Piece] = []
    for si, seg in enumerate(split_unquoted_slash(value)):
        if si:
            pieces.append(Piece("key", "/"))
        if not seg:
            continue
        stripped = seg.lstrip()
        head = stripped.split(" ", 1)[0]
        if head == "quickQuestion":
            pieces.extend(tokenize_quick_question_segment(seg))
        elif '"' in stripped and (head in EVENT_COMMANDS or "\\speak " in stripped or "\\message " in stripped or "\\textAboveHead " in stripped):
            pieces.extend(tokenize_quoted_spans(seg))
        else:
            pieces.append(Piece("key", seg))
    return post_process(pieces)


def slash_is_structural(rel: str, key: str) -> bool:
    if rel.startswith("Data/Events/"):
        return True
    if rel.startswith("Data/Festivals/"):
        return key in ("conditions", "mainEvent", "afterFestival") or key.startswith("set-up")
    if rel in SLASH_FIELD_RULES:
        return True
    if rel == "Strings/StringsFromCSFiles.json":
        if key == "OptionsPage.cs.11278":
            return True
        if key.startswith("Dialogue.cs.") and key.rsplit(".", 1)[-1].isdigit():
            n = int(key.rsplit(".", 1)[-1])
            return 795 <= n <= 810
    return False


def looks_like_event_script(value: str) -> bool:
    if "/" not in value and "(break)" not in value:
        return False
    for segment in split_unquoted_slash(value):
        stripped = segment.lstrip()
        if not stripped:
            continue
        head = stripped.split(" ", 1)[0]
        if head in EVENT_COMMANDS:
            return True
        if "\\speak " in stripped or "\\message " in stripped or "\\textAboveHead " in stripped:
            return True
    return any(token in value for token in ("festivalEnd/end", "waitForOtherPlayers", "endContest", "/end"))


def value_to_pieces(rel: str, key: str, value: str) -> list[Piece]:
    if rel.startswith("Data/Events/"):
        return split_event_script(value)
    if rel.startswith("Data/Festivals/") and (
        key in ("conditions", "mainEvent", "afterFestival")
        or key.startswith("set-up")
        or looks_like_event_script(value)
    ):
        return split_event_script(value)
    if looks_like_event_script(value):
        return split_event_script(value)
    if rel in SLASH_FIELD_RULES:
        rules = SLASH_FIELD_RULES[rel]
        parts = value.split("/")
        resolved = {idx if idx >= 0 else len(parts) + idx: role for idx, role in rules.items()}
        pieces: list[Piece] = []
        for i, part in enumerate(parts):
            if i:
                pieces.append(Piece("key", "/"))
            if resolved.get(i) == "prose":
                pieces.extend(tokenize(part))
            else:
                pieces.append(Piece("key", part))
        return post_process(pieces)
    if rel in CARET_FIELD_RULES:
        rules = CARET_FIELD_RULES[rel]
        pieces: list[Piece] = []
        for i, part in enumerate(value.split("^")):
            if i:
                pieces.append(Piece("key", "^"))
            if rules.get(i) == "prose":
                pieces.extend(tokenize(part))
            else:
                pieces.append(Piece("key", part))
        return post_process(pieces)
    return tokenize(value)


def walk_values(src: Any, dst: Any, path: str = ""):
    if isinstance(src, dict) and isinstance(dst, dict):
        for key, src_value in src.items():
            if key in dst:
                yield from walk_values(src_value, dst[key], f"{path}.{key}" if path else str(key))
    elif isinstance(src, list) and isinstance(dst, list):
        for i, src_value in enumerate(src):
            if i < len(dst):
                yield from walk_values(src_value, dst[i], f"{path}[{i}]")
    else:
        yield path, src, dst


def compare_shape(src: Any, dst: Any, path: str = "") -> list[dict[str, Any]]:
    issues = []
    if type(src) is not type(dst):
        return [{"path": path, "kind": "type_mismatch", "source_type": type(src).__name__, "target_type": type(dst).__name__}]
    if isinstance(src, dict):
        sk, dk = set(src), set(dst)
        for key in sorted(sk - dk):
            issues.append({"path": f"{path}.{key}" if path else str(key), "kind": "missing_key"})
        for key in sorted(dk - sk):
            issues.append({"path": f"{path}.{key}" if path else str(key), "kind": "extra_key"})
        for key in sorted(sk & dk):
            issues.extend(compare_shape(src[key], dst[key], f"{path}.{key}" if path else str(key)))
    elif isinstance(src, list):
        if len(src) != len(dst):
            issues.append({"path": path, "kind": "list_length_mismatch", "source": len(src), "target": len(dst)})
        for i, (a, b) in enumerate(zip(src, dst)):
            issues.extend(compare_shape(a, b, f"{path}[{i}]"))
    return issues


def normalize_token(name: str, value: str) -> str:
    if name == "gender_block":
        return "gender:¦" if "¦" in value else "gender:^"
    return value


def protected_tokens(text: str) -> list[tuple[str, str]]:
    matches = []
    for name, pattern in TOKEN_PATTERNS:
        for m in pattern.finditer(text):
            matches.append((m.start(), m.end(), name, normalize_token(name, m.group(0))))
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    occupied = -1
    for start, end, name, value in matches:
        if start < occupied:
            continue
        out.append((name, value))
        occupied = end
    return out


def event_head_signature(text: str) -> list[str]:
    heads = []
    for segment in text.split("/"):
        stripped = segment.lstrip()
        if not stripped:
            heads.append("")
            continue
        head = stripped.split(" ", 1)[0]
        heads.append(head if head in EVENT_COMMANDS else "<literal>")
    return heads


def y_dialogue_signature(text: str) -> list[dict[str, Any]]:
    sigs = []
    pos = 0
    while True:
        start = text.find("$y", pos)
        if start == -1:
            break
        quote_end = text.find('"', start)
        if quote_end == -1:
            quote_end = len(text)
        q1 = text.find("'", start, quote_end)
        q2 = text.rfind("'", start, quote_end)
        if q1 == -1 or q2 <= q1:
            sigs.append({"closed": False, "parts": 0, "tokens": []})
            pos = start + 2
            continue
        inner = text[q1 + 1:q2]
        sigs.append({"closed": True, "parts": len(inner.split("_")), "tokens": protected_tokens(inner)})
        pos = q2 + 1
    return sigs


def value_signature(rel: str, key: str, value: str) -> dict[str, Any]:
    sig = {"tokens": protected_tokens(value), "extra_command_hashes": len(EXTRA_COMMAND_HASH.findall(value))}
    ysig = y_dialogue_signature(value)
    if ysig:
        sig["y_dialogues"] = ysig
    if slash_is_structural(rel, key):
        sig["slash_count"] = value.count("/")
    if rel.startswith("Data/Events/") or (rel.startswith("Data/Festivals/") and (key in ("mainEvent", "afterFestival") or key.startswith("set-up"))):
        sig["event_heads"] = event_head_signature(value)
    return sig


def dialogue_command_signature(value: str) -> list[tuple[str, str, str]]:
    return [
        (match.group(1), match.group(2), re.sub(r"\s+", " ", match.group(3).strip()))
        for match in CHOICE_DIALOGUE_COMMAND.finditer(value)
    ]


def dialogue_d_branch_signature(value: str) -> list[tuple[str, str, int]]:
    matches = list(re.finditer(r"([#|]?)\$d\s([^#\n]*)#", value))
    out = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(value)
        body = value[match.end():end]
        out.append((match.group(1), re.sub(r"\s+", " ", match.group(2).strip()), body.count("|")))
    return out


def diff_signature(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    diff = {}
    for field in sorted(set(a) | set(b)):
        if a.get(field) != b.get(field):
            diff[field] = {"source": a.get(field), "target": b.get(field)}
    return diff


def load_pair(ctx: Context, rel: str) -> tuple[Any, Any]:
    src_path = ctx.source_for_rel(rel)
    dst_path = ctx.hyper_root / rel
    return json.loads(src_path.read_text(encoding="utf-8")), json.loads(dst_path.read_text(encoding="utf-8"))


def audit(ctx: Context) -> dict[str, Any]:
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    shape_issues: dict[str, list[dict[str, Any]]] = defaultdict(list)
    summary = Counter()
    missing_sources = []
    for hp in sorted(ctx.hyper_root.rglob("*.json")):
        rel = hp.relative_to(ctx.hyper_root).as_posix()
        sp = ctx.source_for_rel(rel)
        if not sp.exists():
            missing_sources.append(rel)
            summary["missing_source"] += 1
            continue
        try:
            src, dst = load_pair(ctx, rel)
        except Exception as exc:
            shape_issues[rel].append({"path": "", "kind": "json_parse_error", "error": str(exc)})
            summary["json_parse_error"] += 1
            continue
        for issue in compare_shape(src, dst):
            shape_issues[rel].append(issue)
            summary[issue["kind"]] += 1
        for key, sv, dv in walk_values(src, dst):
            if not isinstance(sv, str) or not isinstance(dv, str):
                continue
            diff = diff_signature(value_signature(rel, key, sv), value_signature(rel, key, dv))
            if diff:
                by_file[rel].append({"key": key, "diff": diff, "source_preview": sv[:220], "target_preview": dv[:220]})
                for field in diff:
                    summary[field] += 1
    return {
        "summary": dict(summary),
        "missing_sources": missing_sources,
        "files_with_shape_issues": len(shape_issues),
        "files_with_signature_issues": len(by_file),
        "total_shape_issues": sum(len(v) for v in shape_issues.values()),
        "total_signature_issues": sum(len(v) for v in by_file.values()),
        "shape_issues": shape_issues,
        "signature_issues": by_file,
    }


def ensure_cache() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (src TEXT PRIMARY KEY, dst TEXT NOT NULL, ts REAL NOT NULL)")
    conn.commit()
    return conn


def cache_key(src: str, namespace: str = CACHE_NAMESPACE) -> str:
    return f"{namespace}\0{src}"


def cache_get_many(texts: list[str], namespace: str = CACHE_NAMESPACE) -> tuple[dict[str, str], list[str]]:
    conn = ensure_cache()
    out = {}
    missing = []
    try:
        for text in list(dict.fromkeys(texts)):
            row = conn.execute("SELECT dst FROM cache WHERE src = ?", (cache_key(text, namespace),)).fetchone()
            if row:
                out[text] = row[0]
            else:
                missing.append(text)
    finally:
        conn.close()
    return out, missing


def cache_put(src: str, dst: str, namespace: str = CACHE_NAMESPACE) -> None:
    conn = ensure_cache()
    try:
        conn.execute("INSERT OR REPLACE INTO cache(src, dst, ts) VALUES (?, ?, ?)", (cache_key(src, namespace), dst, time.time()))
        conn.commit()
    finally:
        conn.close()


def super_cache_source_key(text: str, route_kind: str, hops: int = DEFAULT_HOPS, backend: str = FREEGTX_BACKEND_NAME) -> str:
    return json.dumps(
        {
            "backend": backend,
            "route_kind": route_kind,
            "hops": hops,
            "text": text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def super_cache_get_many(texts: list[str], namespace: str = SUPER_CACHE_NAMESPACE) -> tuple[dict[str, str], list[str], list[str]]:
    conn = ensure_cache()
    good: dict[str, str] = {}
    missing: list[str] = []
    rejected: list[str] = []
    try:
        for text in list(dict.fromkeys(texts)):
            found = False
            for route_kind in SUPER_CACHE_ROUTE_KINDS:
                src = super_cache_source_key(text, route_kind)
                row = conn.execute("SELECT dst FROM cache WHERE src = ?", (cache_key(src, namespace),)).fetchone()
                if not row:
                    continue
                found = True
                if is_good_hyper_result(text, row[0]):
                    good[text] = row[0]
                    break
                rejected.append(text)
            if text not in good:
                missing.append(text)
                if not found:
                    continue
    finally:
        conn.close()
    return good, list(dict.fromkeys(missing)), list(dict.fromkeys(rejected))


def super_cache_put(src: str, dst: str, route_kind: str, namespace: str = SUPER_CACHE_NAMESPACE) -> None:
    cache_put(super_cache_source_key(src, route_kind), dst, namespace=namespace)


def cache_get_good_hyper_many(texts: list[str], namespace: str = SUPER_CACHE_NAMESPACE) -> tuple[dict[str, str], list[str], list[str]]:
    if namespace in {SUPER_CACHE_NAMESPACE, SIMILARITY_CACHE_NAMESPACE}:
        return super_cache_get_many(texts, namespace=namespace)
    cached, missing = cache_get_many(texts, namespace=namespace)
    good: dict[str, str] = {}
    rejected: list[str] = []
    for source, target in cached.items():
        if is_good_hyper_result(source, target):
            good[source] = target
        else:
            rejected.append(source)
    combined_missing = list(dict.fromkeys([*missing, *rejected]))
    return good, combined_missing, rejected


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def google_translate(text: str, src: str, dst: str, timeout: float = FREEGTX_TIMEOUT) -> str:
    backend = FreeGoogleTranslateBackend(timeout=timeout, use_hop_cache=False)
    return backend.translate(text, src, dst)


def translate_hop(text: str, src: str, dst: str, backend: TranslateBackend | None = None) -> str:
    backend = backend or FreeGoogleTranslateBackend()
    return backend.translate(text, src, dst)


def split_outer_affixes(text: str) -> tuple[str, str, str]:
    start = 0
    end = len(text)
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[:start], text[start:end], text[end:]


def hypertranslate(
    text: str,
    hops: int = DEFAULT_HOPS,
    attempts: int = DEFAULT_ATTEMPTS,
    namespace: str = CACHE_NAMESPACE,
    preserve_affixes: bool = False,
    use_cache: bool = True,
    backend: TranslateBackend | None = None,
) -> str:
    if is_trivial(text):
        return text
    if preserve_affixes:
        prefix, core, suffix = split_outer_affixes(text)
        if core and (prefix or suffix):
            return prefix + hypertranslate(core, hops=hops, attempts=attempts, namespace=namespace, preserve_affixes=False, use_cache=use_cache, backend=backend) + suffix
    prefix_len = len(text) - len(text.lstrip())
    suffix_len = len(text) - len(text.rstrip())
    if prefix_len or suffix_len:
        end = len(text) - suffix_len if suffix_len else len(text)
        core = text[prefix_len:end]
        if core:
            return text[:prefix_len] + hypertranslate(core, hops=hops, attempts=attempts, namespace=namespace, use_cache=use_cache, backend=backend) + text[end:]
    if use_cache:
        cached, missing = cache_get_many([text], namespace=namespace)
        if text in cached:
            return cached[text]
    backend = backend or FreeGoogleTranslateBackend()
    last = None
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = hypertranslate_candidate(text, "normal", hops=hops, backend=backend)
            current = result.target
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2.0 * attempt, 6.0) + random.random())
            continue
        last = current
        if current.strip().lower() != text.strip().lower():
            if use_cache:
                cache_put(text, current, namespace=namespace)
            return current
        last_error = RuntimeError("identity result")
    raise RuntimeError(
        f"hypertranslation failed for: {text[:80]!r}; "
        f"last_error={last_error!r}; last={last[:80] if last else None!r}"
    )


def is_stubborn_short_text(text: str) -> bool:
    norm = normalize_human(text)
    alpha_count = sum(1 for ch in norm if ch.isalpha())
    return 2 <= alpha_count <= STUBBORN_SHORT_ALPHA_MAX


def build_translation_route(hops: int = DEFAULT_HOPS) -> list[str]:
    if hops <= len(LANGS):
        return random.sample(LANGS, hops)
    route: list[str] = []
    while len(route) < hops:
        route.extend(random.sample(LANGS, len(LANGS)))
    return route[:hops]


def hypertranslate_route(text: str, route: list[str], backend: TranslateBackend, route_kind: str = "normal") -> str:
    current = text
    prev = "pt"
    stubborn_source_langs = {"auto", "en", "ja", "tr", "ru", "ar", "ko"}
    for index, lang in enumerate(route):
        src = prev
        if route_kind == "stubborn_short_rescue" and index in {0, 2, 5, 9, 14, 20}:
            src = random.choice(tuple(stubborn_source_langs - {lang}))
        current = translate_hop(current, src, lang, backend=backend)
        prev = lang
    final_src = prev
    if route_kind == "stubborn_short_rescue" and route:
        final_src = random.choice((prev, "auto", "en", "ja"))
    return translate_hop(current, final_src, "pt", backend=backend)


def hypertranslate_candidate(
    text: str,
    route_kind: str,
    hops: int = DEFAULT_HOPS,
    backend: TranslateBackend | None = None,
    preserve_affixes: bool = False,
) -> HyperTranslationResult:
    if preserve_affixes:
        prefix, core, suffix = split_outer_affixes(text)
        if core and (prefix or suffix):
            inner = hypertranslate_candidate(core, route_kind, hops=hops, backend=backend, preserve_affixes=False)
            return HyperTranslationResult(
                source=text,
                target=prefix + inner.target + suffix,
                route_kind=inner.route_kind,
                route=inner.route,
                hops=inner.hops,
            )
    prefix_len = len(text) - len(text.lstrip())
    suffix_len = len(text) - len(text.rstrip())
    if prefix_len or suffix_len:
        end = len(text) - suffix_len if suffix_len else len(text)
        core = text[prefix_len:end]
        if core:
            inner = hypertranslate_candidate(core, route_kind, hops=hops, backend=backend, preserve_affixes=False)
            return HyperTranslationResult(
                source=text,
                target=text[:prefix_len] + inner.target + text[end:],
                route_kind=inner.route_kind,
                route=inner.route,
                hops=inner.hops,
            )
    backend = backend or FreeGoogleTranslateBackend()
    route = build_translation_route(hops)
    return HyperTranslationResult(
        source=text,
        target=hypertranslate_route(text, route, backend=backend, route_kind=route_kind),
        route_kind=route_kind,
        route=route,
        hops=hops,
    )


def collect_texts(pieces: list[Piece]) -> list[str]:
    texts = []
    for p in pieces:
        if p.type in ("text", "emote") and not is_trivial(p.value):
            texts.append(p.value)
        elif p.type == "gender":
            for v in p.values:
                if v and not is_trivial(v):
                    texts.append(v)
    return texts


def apply_translations(pieces: list[Piece], tmap: dict[str, str]) -> tuple[list[Piece], list[str]]:
    failures = []
    out = []
    def tr(v: str) -> str:
        if is_trivial(v):
            return v
        tv = tmap.get(v)
        if tv is None or tv.strip().lower() == v.strip().lower():
            failures.append(v)
            return v
        return tv
    for p in pieces:
        if p.type == "text":
            out.append(Piece("text", tr(p.value)))
        elif p.type == "emote":
            out.append(Piece("emote", tr(p.value)))
        elif p.type == "gender":
            out.append(Piece("gender", values=[tr(v) if v else v for v in p.values]))
        else:
            out.append(p)
    return out, failures


def json_path_parts(dotted_key: str) -> list[str | int]:
    parts: list[str | int] = []
    for segment in dotted_key.split("."):
        while segment:
            if segment.startswith("["):
                end = segment.index("]")
                parts.append(int(segment[1:end]))
                segment = segment[end + 1:]
                continue
            match = re.match(r"[^\[]+", segment)
            if not match:
                raise ValueError(f"invalid json path segment: {segment!r}")
            parts.append(match.group(0))
            segment = segment[match.end():]
    return parts


def assign(doc: Any, dotted_key: str, value: str) -> None:
    if isinstance(doc, dict) and dotted_key in doc:
        doc[dotted_key] = value
        return
    cur = doc
    parts = json_path_parts(dotted_key)
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def deterministic_repair(src: str, dst: str) -> tuple[str, Counter]:
    stats = Counter()
    sc = list(DIALOGUE_COMMAND.finditer(src))
    dc = list(DIALOGUE_COMMAND.finditer(dst))
    out = dst
    if len(sc) == len(dc):
        inserts = []
        deletes = []
        for sm, dm in zip(sc, dc):
            if sm.group(1) and not dm.group(1):
                inserts.append((dm.start(), sm.group(1)))
            src_extra = sm.end() < len(src) and src[sm.end()] == "#"
            dst_extra = dm.end() < len(dst) and dst[dm.end()] == "#"
            if dst_extra and not src_extra:
                deletes.append(dm.end())
        for pos in reversed(deletes):
            out = out[:pos] + out[pos + 1:]
            stats["extra_command_hashes_removed"] += 1
        for pos, sep in reversed(inserts):
            out = out[:pos] + sep + out[pos:]
            stats["inserted_command_separators"] += 1
    out2, n = re.subn(r"}\$([abcdehklnopqrsuvyz])(?=[A-Za-zÀ-ÿ])", r"}$ \1", out)
    out = out2
    stats["gender_close_spacing"] += n
    for token in sorted(set(BARE_MAIL_TOKEN.findall(src)), key=len, reverse=True):
        out, n = re.subn(rf"{re.escape(token)}(?=[A-Za-zÀ-ÿ0-9_])", token + " ", out)
        stats["bare_token_spaces"] += n
    return out, stats


def repair(ctx: Context) -> dict[str, Any]:
    before = audit(ctx)
    stats = Counter()
    touched = set()
    for rel, items in before["signature_issues"].items():
        src_doc, dst_doc = load_pair(ctx, rel)
        changed = False
        for item in items:
            key = item["key"]
            sv = src_doc[key]
            dv = dst_doc[key]
            new, s = deterministic_repair(sv, dv)
            if new != dv:
                dst_doc[key] = new
                changed = True
                stats.update(s)
        if changed:
            (ctx.hyper_root / rel).write_text(json.dumps(dst_doc, ensure_ascii=False, indent=2), encoding="utf-8")
            touched.add(rel)

    mid = audit(ctx)
    plans = []
    for rel, items in mid["signature_issues"].items():
        src_doc, dst_doc = load_pair(ctx, rel)
        for item in items:
            key = item["key"]
            sv = src_doc[key]
            pieces = value_to_pieces(rel, key, sv)
            if reassemble(pieces) != sv:
                raise RuntimeError(f"source round-trip failed for {rel}::{key}")
            plans.append((rel, key, pieces))

    texts = []
    for _, _, pieces in plans:
        texts.extend(collect_texts(pieces))
    texts = list(dict.fromkeys(texts))
    tmap, missing = cache_get_many(texts)
    print(f"Targeted values: {len(plans)}")
    print(f"Targeted pieces: {len(texts)}")
    print(f"Cache hits: {len(tmap)}")
    print(f"Cache misses: {len(missing)}")
    print(f"Hops per piece: {DEFAULT_HOPS}")
    print(f"Parallel workers: {DEFAULT_WORKERS}")
    translation_records = []
    if missing:
        failures = []
        def work(text: str) -> tuple[str, str]:
            return text, hypertranslate(text, hops=DEFAULT_HOPS, attempts=DEFAULT_ATTEMPTS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
            futures = {executor.submit(work, text): text for text in missing}
            done = 0
            for future in concurrent.futures.as_completed(futures):
                text = futures[future]
                done += 1
                try:
                    src_text, dst_text = future.result()
                    tmap[src_text] = dst_text
                    translation_records.append({
                        "source": src_text,
                        "target": dst_text,
                        "hops": DEFAULT_HOPS,
                        "cache_namespace": CACHE_NAMESPACE,
                    })
                    print(f"  hypertranslated {done}/{len(missing)}: {src_text[:72]!r}", flush=True)
                except Exception as exc:
                    failures.append({"piece": text, "error": str(exc)})
                    print(f"  failed {done}/{len(missing)}: {text[:72]!r} -> {exc}", flush=True)
        if failures:
            raise RuntimeError("targeted hypertranslation failures: " + json.dumps(failures[:10], ensure_ascii=False))

    by_file = defaultdict(list)
    failures = []
    for rel, key, pieces in plans:
        new_pieces, f = apply_translations(pieces, tmap)
        if f:
            failures.extend({"file": rel, "key": key, "piece": x} for x in f)
            continue
        by_file[rel].append((key, reassemble(new_pieces)))
    if failures:
        raise RuntimeError("refusing original fallback; failed pieces written to report")

    for rel, entries in by_file.items():
        _, dst_doc = load_pair(ctx, rel)
        for key, value in entries:
            assign(dst_doc, key, value)
        (ctx.hyper_root / rel).write_text(json.dumps(dst_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        touched.add(rel)

    after = audit(ctx)
    return {
        "before": before,
        "after": after,
        "repair_stats": dict(stats),
        "files_touched": sorted(touched),
        "translation_config": {
            "hops": DEFAULT_HOPS,
            "workers": DEFAULT_WORKERS,
            "attempts": DEFAULT_ATTEMPTS,
            "cache_namespace": CACHE_NAMESPACE,
        },
        "translated_pieces": translation_records,
    }


def profile(ctx: Context) -> dict[str, Any]:
    files = 0
    values = 0
    token_counts = Counter()
    event_heads = Counter()
    y_dialogues = 0
    missing = []
    for hp in sorted(ctx.hyper_root.rglob("*.json")):
        rel = hp.relative_to(ctx.hyper_root).as_posix()
        sp = ctx.source_for_rel(rel)
        if not sp.exists():
            missing.append(rel)
            continue
        files += 1
        doc = json.loads(sp.read_text(encoding="utf-8"))
        items = doc.items() if isinstance(doc, dict) else enumerate(doc) if isinstance(doc, list) else []
        for k, v in items:
            if not isinstance(v, str):
                continue
            values += 1
            for name, _ in protected_tokens(v):
                token_counts[name] += 1
            for sig in y_dialogue_signature(v):
                y_dialogues += 1
            if rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/"):
                for head in event_head_signature(v):
                    event_heads[head] += 1
    return {
        "files": files,
        "values": values,
        "missing_sources": missing,
        "token_counts": dict(token_counts.most_common()),
        "event_heads": dict(event_heads.most_common()),
        "y_dialogues": y_dialogues,
    }


def normalize_human(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text.strip().lower())


def is_trivial_human(text: str) -> bool:
    norm = normalize_human(text)
    if not norm:
        return True
    if norm in TRIVIAL_HUMAN_TEXTS:
        return True
    if not any(ch.isalpha() for ch in norm):
        return True
    alpha_count = sum(1 for ch in norm if ch.isalpha())
    return alpha_count <= 1


def human_text_weight(text: str) -> tuple[int, int]:
    norm = normalize_human(text)
    alpha_count = sum(1 for ch in norm if ch.isalpha())
    word_count = len(re.findall(r"[A-Za-zÀ-ÿ]+", norm))
    return alpha_count, word_count


def requires_distinct_hyper_result(text: str) -> bool:
    alpha_count, word_count = human_text_weight(text)
    return alpha_count >= MIN_DISTINCT_HYPER_ALPHA or word_count >= MIN_DISTINCT_HYPER_WORDS


def requires_near_original_check(text: str) -> bool:
    alpha_count, word_count = human_text_weight(text)
    return alpha_count >= MIN_NEAR_ORIGINAL_ALPHA or word_count >= MIN_NEAR_ORIGINAL_WORDS


def is_good_hyper_result(source: str, target: str) -> bool:
    if not target or not target.strip():
        return False
    source_norm = normalize_human(source)
    target_norm = normalize_human(target)
    if source_norm == target_norm and requires_distinct_hyper_result(source):
        return False
    if not source_norm or not target_norm:
        return False
    if requires_near_original_check(source):
        ratio = difflib.SequenceMatcher(None, source_norm, target_norm).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            return False
    return True


def preview(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def human_fragments(pieces: list[Piece]) -> list[dict[str, Any]]:
    out = []
    for idx, piece in enumerate(pieces):
        if piece.type in ("text", "emote"):
            out.append({"piece_index": idx, "role": piece.type, "text": piece.value})
        elif piece.type == "gender":
            for alt_idx, value in enumerate(piece.values):
                out.append({"piece_index": idx, "role": f"gender[{alt_idx}]", "text": value})
    return out


def word_tokens_for_similarity(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", normalize_human(text).lower())


def word_ngram_counter(words: list[str], ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM) -> Counter:
    if ngram <= 0:
        raise ValueError("ngram must be positive")
    if len(words) < ngram:
        return Counter()
    return Counter(tuple(words[i:i + ngram]) for i in range(len(words) - ngram + 1))


def word_ngram_containment(source: str, target: str, ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM) -> float:
    source_ngrams = word_ngram_counter(word_tokens_for_similarity(source), ngram=ngram)
    if not source_ngrams:
        return 0.0
    target_ngrams = word_ngram_counter(word_tokens_for_similarity(target), ngram=ngram)
    if not target_ngrams:
        return 0.0
    overlap = sum(min(count, target_ngrams.get(gram, 0)) for gram, count in source_ngrams.items())
    total = sum(source_ngrams.values())
    return overlap / total if total else 0.0


def is_similarity_repair_candidate(
    source_fragment: str,
    ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM,
    min_words: int = DEFAULT_SIMILARITY_MIN_WORDS,
) -> bool:
    if is_trivial_human(source_fragment):
        return False
    if not requires_distinct_hyper_result(source_fragment):
        return False
    return len(word_tokens_for_similarity(source_fragment)) >= max(ngram, min_words)


def structural_fingerprint(rel: str, key: str, pieces: list[Piece]) -> list[tuple[str, str]]:
    structural = slash_is_structural(rel, key)
    out: list[tuple[str, str]] = []
    for piece in pieces:
        if piece.type == "key":
            value = piece.value
            if any(ch in HIGH_RISK_CHARS for ch in value):
                out.append(("key", value))
            elif structural and any(ch.isalpha() for ch in value):
                out.append(("event-key", value))
        elif piece.type in ("emote", "gender"):
            out.append((piece.type, piece.type))
    return out


def structural_mismatch_category(source_struct: list[tuple[str, str]], target_struct: list[tuple[str, str]]) -> str:
    source_keys = [(kind, value) for kind, value in source_struct if kind in ("key", "event-key")]
    target_keys = [(kind, value) for kind, value in target_struct if kind in ("key", "event-key")]
    if source_keys == target_keys:
        return "display-risk"
    combined = " ".join(value for _, value in source_keys + target_keys)
    has_event_key = any(kind == "event-key" for kind, _ in source_keys + target_keys)
    critical_dialogue = bool(re.search(r"\$[qrdpcy]\b|#\$[bekq]#|[/_|]", combined))
    return "crash-risk" if has_event_key or critical_dialogue else "display-risk"


def raw_protected_tokens(text: str) -> list[tuple[str, str, int, int]]:
    matches = []
    for name, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), name, match.group(0)))
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    occupied = -1
    for start, end, name, value in matches:
        if start < occupied:
            continue
        out.append((name, value, start, end))
        occupied = end
    return out


def is_wordish(ch: str) -> bool:
    return ch.isalpha() or ch.isdigit() or ch == "_"


def has_clean_boundary(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not ((before and is_wordish(before)) or (after and is_wordish(after)))


def token_boundary_issues(source: str, target: str) -> list[dict[str, str]]:
    boundary_tokens = {
        "bare_mail_token", "percent_token", "reveal_taste_token", "player_name", "format_slot",
        "cp_token", "game_token", "item_ref", "mail_item",
    }
    issues = []
    for name, token, _, _ in raw_protected_tokens(source):
        if name not in boundary_tokens:
            continue
        source_positions = [m for m in re.finditer(re.escape(token), source)]
        source_has_clean_boundary = any(has_clean_boundary(source, m.start(), m.end()) for m in source_positions)
        positions = [m for m in re.finditer(re.escape(token), target)]
        if not positions:
            continue
        if not source_has_clean_boundary:
            continue
        if all(has_clean_boundary(target, m.start(), m.end()) for m in positions):
            continue
        issues.append({"token_type": name, "token": token, "reason": "token_glued_to_text"})
    return issues


EVENT_COMMAND_TEXT = re.compile(
    r"\b(?:pause|showFrame|textAboveHead|playSound|jump|emote|globalFade|"
    r"viewport|waitForOtherPlayers|festivalEnd|warp|faceDirection|"
    r"specificTemporarySprite|animate|speak|message|moveToSoup|cutscene)\b",
    re.IGNORECASE,
)


def commandish_text(text: str, rel: str = "") -> bool:
    if re.search(r"(^|[^#|])\$[qrdpcy]\s", text):
        return True
    if rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/"):
        return bool(EVENT_COMMAND_TEXT.search(text) and ("/" in text or "\\" in text or " - " in text))
    return False


def event_terminator_mismatch(rel: str, source: str, target: str) -> bool:
    if not (rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/")):
        return False
    required = []
    if source.endswith("/end") or "/end" in source:
        required.append("/end")
    if "festivalEnd/end" in source:
        required.append("festivalEnd/end")
    if "endContest" in source:
        required.append("endContest")
    return any(token not in target for token in required)


def cache_stats() -> dict[str, int]:
    if not CACHE_PATH.exists():
        return {"rows": 0, "valid_hops25_rows": 0, "legacy_rows": 0}
    conn = ensure_cache()
    try:
        rows = conn.execute("SELECT src FROM cache").fetchall()
    finally:
        conn.close()
    valid = sum(1 for (src,) in rows if src.startswith(VALID_CACHE_PREFIX))
    return {"rows": len(rows), "valid_hops25_rows": valid, "legacy_rows": len(rows) - valid}


def git_modified_hyper_rels(ctx: Context) -> set[str]:
    try:
        root_rel = ctx.hyper_root.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return set()
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--", root_rel],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return set()
    prefix = root_rel + "/"
    return {
        line[len(prefix):]
        for line in proc.stdout.splitlines()
        if line.startswith(prefix) and line.endswith(".json")
    }


def bucket_for_rel(rel: str) -> str:
    for name, prefix in STRATIFIED_BUCKETS:
        if rel.startswith(prefix):
            return name
    return "Other"


def risk_reasons(rel: str, key: str, source: str, modified_rels: set[str]) -> list[str]:
    reasons = []
    if y_dialogue_signature(source):
        reasons.append("y_dialogue")
    if re.search(r"\$[qr]\s", source):
        reasons.append("q_r_dialogue")
    if rel.startswith("Data/Events/") and '"' in source:
        reasons.append("event_quoted_dialogue")
    if rel.startswith("Data/Festivals/") and '"' in source:
        reasons.append("festival_quoted_dialogue")
    if any(ch in source for ch in HIGH_RISK_CHARS):
        reasons.append("protected_syntax")
    if rel in modified_rels:
        reasons.append("modified_by_previous_repair")
    return reasons


def add_entry(entries: list[dict[str, Any]], seen: set[tuple[Any, ...]], entry: dict[str, Any]) -> None:
    marker = (
        entry.get("file", ""),
        entry.get("key", ""),
        entry.get("category", ""),
        entry.get("reason", ""),
        str(entry.get("piece", "")),
        entry.get("source_fragment", "")[:120],
    )
    if marker in seen:
        return
    seen.add(marker)
    entries.append(entry)


def deep_audit(ctx: Context) -> dict[str, Any]:
    base = audit(ctx)
    modified_rels = git_modified_hyper_rels(ctx)
    findings: list[dict[str, Any]] = []
    high_risk: list[dict[str, Any]] = []
    sample_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    finding_seen: set[tuple[Any, ...]] = set()
    high_seen: set[tuple[Any, ...]] = set()
    summary = Counter()

    for hp in sorted(ctx.hyper_root.rglob("*.json")):
        rel = hp.relative_to(ctx.hyper_root).as_posix()
        sp = ctx.source_for_rel(rel)
        if not sp.exists():
            continue
        try:
            src_doc, dst_doc = load_pair(ctx, rel)
        except Exception:
            continue

        for key, source_value, target_value in walk_values(src_doc, dst_doc):
            if not isinstance(source_value, str) or not isinstance(target_value, str):
                continue
            summary["string_values"] += 1
            bucket = bucket_for_rel(rel)
            source_preview = preview(source_value)
            target_preview = preview(target_value)

            try:
                source_pieces = value_to_pieces(rel, key, source_value)
                target_pieces = value_to_pieces(rel, key, target_value)
            except Exception as exc:
                entry = {
                    "category": "crash-risk",
                    "reason": "parser_exception",
                    "file": rel,
                    "key": key,
                    "error": repr(exc),
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                }
                add_entry(findings, finding_seen, entry)
                continue

            source_roundtrip = reassemble(source_pieces)
            target_roundtrip = reassemble(target_pieces)
            if source_roundtrip != source_value:
                add_entry(findings, finding_seen, {
                    "category": "crash-risk",
                    "reason": "source_roundtrip_failed",
                    "file": rel,
                    "key": key,
                    "source_preview": source_preview,
                    "roundtrip_preview": preview(source_roundtrip),
                    "recommended_action": "model-original-grammar-before-repair",
                })
            if target_roundtrip != target_value:
                add_entry(findings, finding_seen, {
                    "category": "display-risk",
                    "reason": "target_roundtrip_failed",
                    "file": rel,
                    "key": key,
                    "target_preview": target_preview,
                    "roundtrip_preview": preview(target_roundtrip),
                    "recommended_action": "needs-repair",
                })

            source_struct = structural_fingerprint(rel, key, source_pieces)
            target_struct = structural_fingerprint(rel, key, target_pieces)
            if source_struct != target_struct:
                category = structural_mismatch_category(source_struct, target_struct)
                add_entry(findings, finding_seen, {
                    "category": category,
                    "reason": "structural_fingerprint_mismatch",
                    "file": rel,
                    "key": key,
                    "source_struct": source_struct[:40],
                    "target_struct": target_struct[:40],
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair" if category == "crash-risk" else "manual-review",
                })

            source_dialogue_sig = dialogue_command_signature(source_value)
            target_dialogue_sig = dialogue_command_signature(target_value)
            if source_dialogue_sig != target_dialogue_sig:
                add_entry(findings, finding_seen, {
                    "category": "crash-risk",
                    "reason": "dialogue_command_signature_mismatch",
                    "file": rel,
                    "key": key,
                    "source_dialogue_signature": source_dialogue_sig,
                    "target_dialogue_signature": target_dialogue_sig,
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                })

            source_d_branch_sig = dialogue_d_branch_signature(source_value)
            target_d_branch_sig = dialogue_d_branch_signature(target_value)
            if source_d_branch_sig != target_d_branch_sig:
                add_entry(findings, finding_seen, {
                    "category": "crash-risk",
                    "reason": "dialogue_d_branch_mismatch",
                    "file": rel,
                    "key": key,
                    "source_dialogue_d_signature": source_d_branch_sig,
                    "target_dialogue_d_signature": target_d_branch_sig,
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                })

            if event_terminator_mismatch(rel, source_value, target_value):
                add_entry(findings, finding_seen, {
                    "category": "crash-risk",
                    "reason": "event_terminator_mismatch",
                    "file": rel,
                    "key": key,
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                })

            for issue in token_boundary_issues(source_value, target_value):
                add_entry(findings, finding_seen, {
                    "category": "display-risk",
                    "reason": issue["reason"],
                    "file": rel,
                    "key": key,
                    "token_type": issue["token_type"],
                    "token": issue["token"],
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                })

            source_fragments = human_fragments(source_pieces)
            target_fragments = human_fragments(target_pieces)
            if len(source_fragments) != len(target_fragments):
                add_entry(findings, finding_seen, {
                    "category": "display-risk",
                    "reason": "human_fragment_count_mismatch",
                    "file": rel,
                    "key": key,
                    "source_count": len(source_fragments),
                    "target_count": len(target_fragments),
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                    "recommended_action": "needs-repair",
                })

            for idx, (source_fragment, target_fragment) in enumerate(zip(source_fragments, target_fragments)):
                sv = source_fragment["text"]
                tv = target_fragment["text"]
                if is_trivial_human(sv):
                    continue
                ns = normalize_human(sv)
                nt = normalize_human(tv)
                if not nt:
                    add_entry(findings, finding_seen, {
                        "category": "display-risk",
                        "reason": "empty_human_fragment",
                        "file": rel,
                        "key": key,
                        "piece": idx,
                        "source_fragment": sv,
                        "target_fragment": tv,
                        "recommended_action": "needs-repair",
                    })
                    continue
                if ns == nt:
                    if requires_distinct_hyper_result(sv):
                        add_entry(findings, finding_seen, {
                            "category": "not-hypertranslated",
                            "reason": "identical_nontrivial_fragment",
                            "file": rel,
                            "key": key,
                            "piece": idx,
                            "source_fragment": sv,
                            "target_fragment": tv,
                            "recommended_action": "needs-repair",
                        })
                elif requires_near_original_check(sv):
                    ratio = difflib.SequenceMatcher(None, ns, nt).ratio()
                    if ratio >= SIMILARITY_THRESHOLD:
                        add_entry(findings, finding_seen, {
                            "category": "not-hypertranslated",
                            "reason": "near_original_fragment",
                            "file": rel,
                            "key": key,
                            "piece": idx,
                            "similarity": round(ratio, 3),
                            "source_fragment": sv,
                            "target_fragment": tv,
                            "recommended_action": "needs-repair",
                        })

                if len(sv.strip()) >= 30 and len(tv.strip()) < 4:
                    add_entry(findings, finding_seen, {
                        "category": "display-risk",
                        "reason": "suspiciously_short_fragment",
                        "file": rel,
                        "key": key,
                        "piece": idx,
                        "source_fragment": sv,
                        "target_fragment": tv,
                        "recommended_action": "manual-review",
                    })
                if len(tv) > max(300, len(sv) * 4):
                    add_entry(findings, finding_seen, {
                        "category": "display-risk",
                        "reason": "suspiciously_long_fragment",
                        "file": rel,
                        "key": key,
                        "piece": idx,
                        "source_len": len(sv),
                        "target_len": len(tv),
                        "source_fragment": preview(sv),
                        "target_fragment": preview(tv),
                        "recommended_action": "manual-review",
                    })
                if commandish_text(tv, rel):
                    add_entry(findings, finding_seen, {
                        "category": "crash-risk" if rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/") else "display-risk",
                        "reason": "command_like_text_fragment",
                        "file": rel,
                        "key": key,
                        "piece": idx,
                        "target_fragment": preview(tv),
                        "recommended_action": "needs-repair",
                    })

            reasons = risk_reasons(rel, key, source_value, modified_rels)
            if reasons:
                add_entry(high_risk, high_seen, {
                    "category": "pending-manual-review",
                    "reason": ",".join(reasons),
                    "file": rel,
                    "key": key,
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                })
            elif len(sample_candidates[bucket]) < 40:
                sample_candidates[bucket].append({
                    "category": "stratified-sample",
                    "reason": bucket,
                    "file": rel,
                    "key": key,
                    "source_preview": source_preview,
                    "target_preview": target_preview,
                })

    for entry in findings:
        summary[f"finding:{entry['category']}"] += 1
        summary[f"reason:{entry['reason']}"] += 1
    for entry in high_risk:
        for reason in entry["reason"].split(","):
            summary[f"high_risk:{reason}"] += 1

    stratified_samples = []
    for bucket, entries in sample_candidates.items():
        stratified_samples.extend(entries[:20])

    cache = cache_stats()
    grammar_findings = [f for f in findings if f["reason"] in ("source_roundtrip_failed", "target_roundtrip_failed", "parser_exception")]
    structural_findings = [f for f in findings if f["category"] == "crash-risk"]
    display_findings = [f for f in findings if f["category"] == "display-risk"]
    hyper_findings = [f for f in findings if f["category"] == "not-hypertranslated"]
    criteria = {
        "structurally_safe": (
            base["total_shape_issues"] == 0
            and base["total_signature_issues"] == 0
            and not grammar_findings
            and not structural_findings
        ),
        "really_hypertranslated": not hyper_findings,
        "manual_review_complete": False,
        "no_known_surprises": False,
    }
    criteria["no_known_surprises"] = (
        criteria["structurally_safe"]
        and criteria["really_hypertranslated"]
        and not display_findings
    )

    manual_review_queue = {
        "summary": {
            "high_risk_count": len(high_risk),
            "finding_count": len(findings),
            "stratified_sample_count": len(stratified_samples),
            "manual_review_complete": False,
        },
        "findings": findings,
        "high_risk": high_risk,
        "stratified_samples": stratified_samples,
    }

    return {
        "summary": dict(summary.most_common()),
        "base_audit": base,
        "cache": cache,
        "criteria": criteria,
        "counts": {
            "string_values": summary["string_values"],
            "findings": len(findings),
            "crash_risk_findings": len(structural_findings),
            "display_risk_findings": len(display_findings),
            "not_hypertranslated_findings": len(hyper_findings),
            "high_risk_manual_review_items": len(high_risk),
            "stratified_sample_items": len(stratified_samples),
            "modified_hyper_files": len(modified_rels),
        },
        "manual_review_queue": manual_review_queue,
    }


def get_value(doc: Any, dotted_key: str) -> Any:
    if isinstance(doc, dict) and dotted_key in doc:
        return doc[dotted_key]
    cur = doc
    for part in json_path_parts(dotted_key):
        cur = cur[part]
    return cur


def apply_boundary_fix_value(source: str, target: str) -> str:
    out = target
    tokens = []
    for name, token, _, _ in raw_protected_tokens(source):
        if name in {"bare_mail_token", "percent_token", "reveal_taste_token", "player_name", "format_slot", "cp_token", "game_token", "item_ref", "mail_item"}:
            tokens.append(token)
    for token in sorted(set(tokens), key=len, reverse=True):
        def repl(match: re.Match) -> str:
            before = out[match.start() - 1] if match.start() > 0 else ""
            after = out[match.end()] if match.end() < len(out) else ""
            left = " " if before and is_wordish(before) else ""
            right = " " if after and is_wordish(after) else ""
            return left + token + right
        out = re.sub(re.escape(token), repl, out)
    return re.sub(r"[ \t]{2,}", " ", out)


def apply_syntax_fix_value(target: str) -> str:
    out = target
    out = re.sub(r"(?<=[A-Za-zÀ-ÿ0-9])(\*[^*\n]{1,80}\*)", r" \1", out)
    out = re.sub(r"(\*[^*\n]{1,80}\*)(?=[A-Za-zÀ-ÿ0-9])", r"\1 ", out)
    out = re.sub(r"([.!?])(?=\$[a-z0-9])", r"\1 ", out)
    return re.sub(r"[ \t]{2,}", " ", out)


def sanitize_generated_text(text: str, rel: str, key: str, source_value: str) -> str:
    out = text.replace("\n", " ").replace("\r", " ")
    if rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/"):
        out = out.replace('"', "'").replace("/", " - ").replace("\\", " ")
    if "$y '" in source_value:
        out = out.replace("'", "’").replace("_", " ")
    replacements = {
        "$": "dolar",
        "#": "numero",
        "|": " ",
        "^": " ",
        "{": "(",
        "}": ")",
        "[": "(",
        "]": ")",
        "%": "por cento",
        "@": "arroba",
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return re.sub(r"[ \t]{2,}", " ", out)


def preserved_human_fragment(source_fragment: str, target_fragment: str) -> bool:
    if is_trivial_human(source_fragment):
        return True
    if not target_fragment.strip():
        return False
    if normalize_human(source_fragment) == normalize_human(target_fragment):
        return False
    if protected_tokens(target_fragment):
        return False
    if len(source_fragment.strip()) >= 30 and len(target_fragment.strip()) < 4:
        return False
    if len(target_fragment) > max(300, len(source_fragment) * 4):
        return False
    return True


def event_needs_full_rebuild(rel: str, key: str, source_value: str, current_value: str) -> bool:
    try:
        source_pieces = value_to_pieces(rel, key, source_value)
        target_pieces = value_to_pieces(rel, key, current_value)
    except Exception:
        return True
    if reassemble(source_pieces) != source_value:
        return True
    if reassemble(target_pieces) != current_value:
        return True
    if structural_fingerprint(rel, key, source_pieces) != structural_fingerprint(rel, key, target_pieces):
        return True
    return len(human_fragments(source_pieces)) != len(human_fragments(target_pieces))


def structured_value_needs_full_rebuild(rel: str, key: str, source_value: str, current_value: str) -> bool:
    if rel not in {"Data/SecretNotes.json"}:
        return False
    return event_needs_full_rebuild(rel, key, source_value, current_value)


def is_event_or_choice_quality_target(rel: str, source_value: str) -> bool:
    if rel.startswith("Data/Events/") or rel.startswith("Data/Festivals/"):
        return True
    return bool(re.search(r"\$[qrpy]\s", source_value))


def make_event_span_template(
    rel: str,
    key: str,
    source_value: str,
    current_value: str,
    *,
    preserve_current: bool = True,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    source_pieces = value_to_pieces(rel, key, source_value)
    if reassemble(source_pieces) != source_value:
        return "", [], [{"reason": "source_roundtrip_failed"}]
    if preserve_current:
        try:
            target_fragments = human_fragments(value_to_pieces(rel, key, current_value))
        except Exception:
            target_fragments = []
    else:
        target_fragments = []

    source_fragment_index = 0
    translation_sources: list[str] = []
    template_pieces: list[Piece] = []
    failures: list[dict[str, Any]] = []

    def choose_fragment(source_text: str, role: str) -> str:
        nonlocal source_fragment_index
        target_text = target_fragments[source_fragment_index]["text"] if preserve_current and source_fragment_index < len(target_fragments) else ""
        source_fragment_index += 1
        if preserve_current and commandish_text(target_text, rel):
            placeholder = f"__HS_TRANSLATE_{len(translation_sources)}__"
            translation_sources.append(source_text)
            return placeholder
        if preserve_current and preserved_human_fragment(source_text, target_text):
            return sanitize_generated_text(target_text, rel, key, source_value)
        if is_trivial_human(source_text):
            return source_text
        placeholder = f"__HS_TRANSLATE_{len(translation_sources)}__"
        translation_sources.append(source_text)
        return placeholder

    for piece in source_pieces:
        if piece.type == "text":
            template_pieces.append(Piece("text", choose_fragment(piece.value, "text")))
        elif piece.type == "emote":
            template_pieces.append(Piece("emote", choose_fragment(piece.value, "emote")))
        elif piece.type == "gender":
            values = [choose_fragment(v, f"gender[{i}]") if v else v for i, v in enumerate(piece.values)]
            template_pieces.append(Piece("gender", values=values))
        else:
            template_pieces.append(piece)

    return reassemble(template_pieces), translation_sources, failures


def translate_missing_super(
    missing: list[str],
    progress: Any = None,
    namespace: str = SUPER_CACHE_NAMESPACE,
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    tmap: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    if not missing:
        return tmap, failures, records, {}

    backend = FreeGoogleTranslateBackend()

    def route_kinds_for(text: str) -> list[str]:
        kinds = ["normal"]
        kinds.extend(["identity_rescue"] * SUPER_IDENTITY_RESCUE_ROUTES)
        if is_stubborn_short_text(text):
            kinds.extend(["stubborn_short_rescue"] * SUPER_IDENTITY_RESCUE_ROUTES)
        return kinds

    def work(text: str) -> HyperTranslationResult:
        errors: list[str] = []
        for route_number, route_kind in enumerate(route_kinds_for(text), start=1):
            try:
                result = hypertranslate_candidate(
                    text,
                    route_kind,
                    hops=DEFAULT_HOPS,
                    backend=backend,
                    preserve_affixes=True,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue
            if is_good_hyper_result(text, result.target):
                super_cache_put(text, result.target, route_kind=result.route_kind, namespace=namespace)
                return result
            errors.append(f"{route_kind}_{route_number} identity/near-original result: {result.target[:120]!r}")
        raise RuntimeError(
            f"hypertranslation rescue failed after {len(route_kinds_for(text))} routes; "
            f"last_error={errors[-1] if errors else 'unknown'}"
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
        futures = {executor.submit(work, text): text for text in missing}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            text = futures[future]
            done += 1
            try:
                result = future.result()
                tmap[result.source] = result.target
                records.append({
                    "source": result.source,
                    "target": result.target,
                    "hops": result.hops,
                    "route": result.route,
                    "route_kind": result.route_kind,
                    "cache_namespace": namespace,
                    "backend": FREEGTX_BACKEND_NAME,
                })
                if progress:
                    progress(result.route_kind, done, len(missing), result.source)
                print(f"  super-hypertranslated {done}/{len(missing)} [{result.route_kind}]: {result.source[:72]!r}", flush=True)
            except Exception as exc:
                failures.append({"piece": text, "error": str(exc)})
                if progress:
                    progress("failed", done, len(missing), text)
                print(f"  failed {done}/{len(missing)}: {text[:72]!r} -> {exc}", flush=True)
    return tmap, failures, records, backend.metrics_dict()


def make_repair_action(ctx: Context, finding: dict[str, Any], source_value: str, current_value: str) -> dict[str, Any]:
    rel = finding["file"]
    key = finding["key"]
    reason = finding["reason"]
    base = {
        "file": rel,
        "key": key,
        "reason": reason,
        "category": finding["category"],
        "source_preview": preview(source_value),
        "current_preview": preview(current_value),
        "proposed_preview": "",
        "requires_translation": False,
        "translation_sources": [],
        "source_value": source_value,
    }

    if reason == "token_glued_to_text":
        proposed = apply_boundary_fix_value(source_value, current_value)
        base.update({
            "action_type": "boundary_fix",
            "proposed_preview": preview(proposed),
            "deterministic_value": proposed,
            "will_preserve_current_hyper": True,
        })
        return base

    if reason == "dialogue_command_signature_mismatch":
        template, translation_sources, failures = make_event_span_template(
            rel,
            key,
            source_value,
            current_value,
            preserve_current=False,
        )
        if template and not failures:
            base.update({
                "action_type": "dialogue_full_rebuild",
                "template_value": template,
                "translation_sources": translation_sources,
                "requires_translation": bool(translation_sources),
                "proposed_preview": preview(template),
                "will_preserve_current_hyper": False,
            })
            return base

    if finding["category"] == "crash-risk" and reason in {
        "structural_fingerprint_mismatch",
        "target_roundtrip_failed",
        "command_like_text_fragment",
        "event_terminator_mismatch",
    }:
        full_rebuild = reason in {"command_like_text_fragment", "event_terminator_mismatch"} or event_needs_full_rebuild(rel, key, source_value, current_value)
        template, translation_sources, failures = make_event_span_template(
            rel,
            key,
            source_value,
            current_value,
            preserve_current=not full_rebuild,
        )
        if template and not failures:
            base.update({
                "action_type": "event_full_rebuild" if full_rebuild else "event_span_repair",
                "template_value": template,
                "translation_sources": translation_sources,
                "requires_translation": bool(translation_sources),
                "proposed_preview": preview(template),
                "will_preserve_current_hyper": not full_rebuild,
            })
            return base

    if reason in {"structural_fingerprint_mismatch", "human_fragment_count_mismatch", "target_roundtrip_failed"} and structured_value_needs_full_rebuild(rel, key, source_value, current_value):
        template, translation_sources, failures = make_event_span_template(
            rel,
            key,
            source_value,
            current_value,
            preserve_current=False,
        )
        if template and not failures:
            base.update({
                "action_type": "structured_full_rebuild",
                "template_value": template,
                "translation_sources": translation_sources,
                "requires_translation": bool(translation_sources),
                "proposed_preview": preview(template),
                "will_preserve_current_hyper": False,
            })
            return base

    syntax_value = apply_syntax_fix_value(current_value)
    if reason in {"structural_fingerprint_mismatch", "human_fragment_count_mismatch"} and syntax_value != current_value:
        base.update({
            "action_type": "syntax_fix",
            "proposed_preview": preview(syntax_value),
            "deterministic_value": syntax_value,
            "will_preserve_current_hyper": True,
        })
        return base

    if reason in {"identical_nontrivial_fragment", "near_original_fragment", "suspiciously_short_fragment", "suspiciously_long_fragment", "empty_human_fragment"}:
        source_fragment = finding.get("source_fragment", "")
        target_fragment = finding.get("target_fragment", "")
        if source_fragment and target_fragment and target_fragment in current_value and not is_trivial_human(source_fragment):
            base.update({
                "action_type": "fragment_retranslate",
                "source_fragment": source_fragment,
                "target_fragment": target_fragment,
                "translation_sources": [source_fragment],
                "requires_translation": True,
                "proposed_preview": preview(current_value.replace(target_fragment, f"<translate:{preview(source_fragment, 48)}>", 1)),
                "will_preserve_current_hyper": True,
            })
            return base

    if reason in {"structural_fingerprint_mismatch", "target_roundtrip_failed", "command_like_text_fragment", "event_terminator_mismatch"}:
        full_rebuild = finding["category"] == "crash-risk" and (
            reason in {"command_like_text_fragment", "event_terminator_mismatch"}
            or event_needs_full_rebuild(rel, key, source_value, current_value)
        )
        template, translation_sources, failures = make_event_span_template(
            rel,
            key,
            source_value,
            current_value,
            preserve_current=not full_rebuild,
        )
        if template and not failures:
            base.update({
                "action_type": "event_full_rebuild" if full_rebuild else "event_span_repair",
                "template_value": template,
                "translation_sources": translation_sources,
                "requires_translation": bool(translation_sources),
                "proposed_preview": preview(template),
                "will_preserve_current_hyper": not full_rebuild,
            })
            return base

    base.update({
        "action_type": "manual_blocker",
        "proposed_preview": preview(current_value),
        "will_preserve_current_hyper": True,
    })
    return base


def build_super_repair_plan(
    ctx: Context,
    audit_result: dict[str, Any] | None = None,
    stability_only: bool = False,
    event_choice_quality: bool = False,
) -> dict[str, Any]:
    audit_result = audit_result or deep_audit(ctx)
    actions = []
    seen = set()
    full_rebuild_values: set[tuple[str, str]] = set()
    docs: dict[str, tuple[Any, Any]] = {}

    for finding in audit_result["manual_review_queue"].get("findings", []):
        rel = finding["file"]
        key = finding["key"]
        marker = (rel, key, finding["reason"], finding["category"], finding.get("piece"))
        if marker in seen:
            continue
        seen.add(marker)
        if rel not in docs:
            docs[rel] = load_pair(ctx, rel)
        source_doc, target_doc = docs[rel]
        source_value = get_value(source_doc, key)
        current_value = get_value(target_doc, key)
        if not isinstance(source_value, str) or not isinstance(current_value, str):
            continue
        if finding.get("category") == "not-hypertranslated":
            if stability_only and not event_choice_quality:
                continue
            if event_choice_quality and not is_event_or_choice_quality_target(rel, source_value):
                continue
        action = make_repair_action(ctx, finding, source_value, current_value)
        value_marker = (rel, key)
        if action["action_type"] in {"event_full_rebuild", "structured_full_rebuild"}:
            if value_marker in full_rebuild_values:
                continue
            actions = [existing for existing in actions if (existing["file"], existing["key"]) != value_marker]
            full_rebuild_values.add(value_marker)
        elif value_marker in full_rebuild_values:
            continue
        actions.append(action)

    translation_sources = []
    for action in actions:
        if action["action_type"] != "manual_blocker":
            translation_sources.extend(action.get("translation_sources", []))
    translation_sources = list(dict.fromkeys(x for x in translation_sources if x and not is_trivial_human(x)))
    cached, missing, rejected_cache = cache_get_good_hyper_many(translation_sources, namespace=SUPER_CACHE_NAMESPACE)
    counts = Counter(action["action_type"] for action in actions)
    plan = {
        "schema_version": 1,
        "cache_namespace": SUPER_CACHE_NAMESPACE,
        "stability_only": stability_only,
        "event_choice_quality": event_choice_quality,
        "hops": DEFAULT_HOPS,
        "workers": DEFAULT_WORKERS,
        "audit_counts": audit_result["counts"],
        "action_counts": dict(counts),
        "translation_estimate": {
            "fragments": len(translation_sources),
            "cache_hits": len(cached),
            "cache_misses": len(missing),
            "cache_rejected": len(rejected_cache),
        },
        "actions": actions,
    }
    return plan


def load_super_repair_plan() -> dict[str, Any]:
    path = REPORT_DIR / "super_repair_plan.json"
    if not path.exists():
        raise FileNotFoundError(f"No saved plan at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_super_repair_summary(report: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "super_repair_summary.md"
    before = report["plan"]["audit_counts"]
    after = report.get("final", {}).get("counts", before)
    lines = [
        "# HyperStardew Super Repair Summary",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Stability only: `{report['plan'].get('stability_only', False)}`",
        f"- Event/choice quality: `{report['plan'].get('event_choice_quality', False)}`",
        f"- Actions planned: {len(report['plan']['actions'])}",
        f"- Files touched: {len(report.get('files_touched', []))}",
        f"- Backup dir: `{report.get('backup_dir') or 'none'}`",
        f"- Values changed: {report['totals'].get('values_changed', 0)}",
        f"- Pieces hypertranslated: {report['totals'].get('pieces_translated', 0)}",
        f"- Cache hits: {report['totals'].get('cache_hits', 0)}",
        f"- Cache misses: {report['totals'].get('cache_misses', 0)}",
        f"- Cache rejected: {report['totals'].get('cache_rejected', 0)}",
        f"- Cache namespace: `{report['plan']['cache_namespace']}`",
        f"- Backend requests: {report['totals'].get('backend_requests', 0)}",
        f"- Backend retries: {report['totals'].get('backend_retries', 0)}",
        f"- Backend rate-limit waits: {report['totals'].get('backend_rate_limit_waits', 0)}",
        "",
        "## Planned Actions",
        "",
    ]
    for name, count in sorted(report["plan"]["action_counts"].items()):
        lines.append(f"- {name}: {count}")
    lines.extend([
        "",
        "## Findings Before",
        "",
        f"- crash-risk: {before['crash_risk_findings']}",
        f"- display-risk: {before['display_risk_findings']}",
        f"- not-hypertranslated: {before['not_hypertranslated_findings']}",
        "",
        "## Findings After",
        "",
        f"- crash-risk: {after['crash_risk_findings']}",
        f"- display-risk: {after['display_risk_findings']}",
        f"- not-hypertranslated: {after['not_hypertranslated_findings']}",
        "",
    ])
    if report.get("failures"):
        lines.extend(["## Failures", ""])
        for item in report["failures"][:100]:
            location = f"`{item.get('file')}::{item.get('key')}`" if item.get("file") and item.get("key") else "`translation`"
            piece = f" piece={preview(item.get('piece', ''), 90)!r}" if item.get("piece") else ""
            detail = item.get("error") or item.get("reason") or "failed"
            lines.append(f"- {location} {item.get('reason', 'failed')}: {detail}{piece}")
    blockers = report.get("final", {}).get("manual_review_queue", {}).get("findings", [])
    if blockers:
        lines.extend(["", "## Remaining Blockers", ""])
        for item in blockers[:100]:
            lines.append(f"- `{item['category']}` / `{item['reason']}` in `{item['file']}::{item['key']}`")
        if len(blockers) > 100:
            lines.append(f"- ... {len(blockers) - 100} more in `deep_audit_report.json`.")
    backend_metrics = report.get("backend_metrics") or {}
    if backend_metrics:
        lines.extend([
            "",
            "## Backend Metrics",
            "",
            f"- backend: `{backend_metrics.get('backend', FREEGTX_BACKEND_NAME)}`",
            f"- max_in_flight_http: {backend_metrics.get('max_in_flight_http')}",
            f"- max_qps: {backend_metrics.get('max_qps')}",
            f"- status_counts: `{backend_metrics.get('status_counts', {})}`",
            f"- error_counts: `{backend_metrics.get('error_counts', {})}`",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_action_value(action: dict[str, Any], current_value: str, translations: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    failures = []
    action_type = action["action_type"]
    rel = action["file"]
    key = action["key"]
    source_value = action.get("source_value", "")
    if action_type == "boundary_fix":
        return apply_boundary_fix_value(source_value, current_value), failures
    if action_type == "syntax_fix":
        return apply_syntax_fix_value(current_value), failures
    if action_type == "fragment_retranslate":
        source_fragment = action["source_fragment"]
        target_fragment = action["target_fragment"]
        translated = translations.get(source_fragment)
        if not translated:
            return current_value, [{"reason": "missing_translation", "piece": source_fragment}]
        translated = sanitize_generated_text(translated, rel, key, source_value)
        if not is_good_hyper_result(source_fragment, translated):
            return current_value, [{"reason": "identity_translation", "piece": source_fragment}]
        if target_fragment not in current_value:
            return current_value, [{"reason": "target_fragment_not_found", "piece": target_fragment}]
        return current_value.replace(target_fragment, translated, 1), failures
    if action_type in {"event_span_repair", "event_full_rebuild", "structured_full_rebuild", "dialogue_full_rebuild"}:
        value = action["template_value"]
        for idx, source_fragment in enumerate(action.get("translation_sources", [])):
            translated = translations.get(source_fragment)
            if not translated:
                failures.append({"reason": "missing_translation", "piece": source_fragment})
                continue
            translated = sanitize_generated_text(translated, rel, key, source_value)
            if not is_good_hyper_result(source_fragment, translated):
                failures.append({"reason": "identity_translation", "piece": source_fragment})
                continue
            value = value.replace(f"__HS_TRANSLATE_{idx}__", translated)
        if failures:
            return current_value, failures
        return value, failures
    return current_value, failures


def super_repair(
    ctx: Context,
    apply: bool = False,
    assume_yes: bool = False,
    progress: Any = None,
    resume: bool = False,
    stability_only: bool = False,
    event_choice_quality: bool = False,
) -> dict[str, Any]:
    if resume:
        plan = load_super_repair_plan()
        saved_blockers = [
            {
                "category": action["category"],
                "reason": action["reason"],
                "file": action["file"],
                "key": action["key"],
            }
            for action in plan.get("actions", [])
            if action.get("action_type") == "manual_blocker"
        ]
        audit_result = {
            "counts": plan["audit_counts"],
            "manual_review_queue": {"findings": saved_blockers},
        }
    else:
        audit_result = deep_audit(ctx)
        plan = build_super_repair_plan(ctx, audit_result, stability_only=stability_only, event_choice_quality=event_choice_quality)
        write_report("super_repair_plan.json", plan)
    totals = Counter()
    failures: list[dict[str, Any]] = []
    translated_records: list[dict[str, Any]] = []
    files_touched: set[str] = set()
    mode = "apply" if apply else "dry-run"

    translation_sources = []
    for action in plan["actions"]:
        if action["action_type"] != "manual_blocker":
            translation_sources.extend(action.get("translation_sources", []))
    translation_sources = list(dict.fromkeys(x for x in translation_sources if x and not is_trivial_human(x)))
    cached, missing, rejected_cache = cache_get_good_hyper_many(translation_sources, namespace=SUPER_CACHE_NAMESPACE)
    totals["cache_hits"] = len(cached)
    totals["cache_misses"] = len(missing)
    totals["cache_rejected"] = len(rejected_cache)

    report: dict[str, Any] = {
        "mode": mode,
        "plan": plan,
        "files_touched": [],
        "backup_dir": None,
        "failures": failures,
        "translated_pieces": translated_records,
        "backend_metrics": {},
        "totals": {},
        "final": audit_result,
    }

    if not apply:
        report["totals"] = dict(totals)
        write_report("super_repair_report.json", report)
        write_super_repair_summary(report)
        return report

    if not assume_yes:
        print("Super-repair is about to write JSON files.")
        print(f"Actions: {len(plan['actions'])}; translations: {len(translation_sources)}; cache misses: {len(missing)}")
        confirmation = input("Type APPLY to continue: ").strip()
        if confirmation != "APPLY":
            report["mode"] = "cancelled"
            report["totals"] = dict(totals)
            write_report("super_repair_report.json", report)
            write_super_repair_summary(report)
            return report

    translated, translate_failures, records, backend_metrics = translate_missing_super(missing, progress=progress)
    translations = {**cached, **translated}
    failures.extend({"reason": "translation_failed", **failure} for failure in translate_failures)
    translated_records.extend(records)
    totals["pieces_translated"] = len(records)
    totals["backend_requests"] = backend_metrics.get("requests", 0)
    totals["backend_retries"] = backend_metrics.get("retries", 0)
    totals["backend_failures"] = backend_metrics.get("failures", 0)
    totals["backend_rate_limit_waits"] = backend_metrics.get("rate_limit_waits", 0)
    report["backend_metrics"] = backend_metrics

    docs: dict[str, Any] = {}
    changed_by_file: dict[str, int] = Counter()
    for idx, action in enumerate(plan["actions"], start=1):
        if action["action_type"] == "manual_blocker":
            if progress:
                progress("action", idx, len(plan["actions"]), f"manual {action['file']}::{action['key']}")
            continue
        rel = action["file"]
        key = action["key"]
        if rel not in docs:
            _, docs[rel] = load_pair(ctx, rel)
        current_value = get_value(docs[rel], key)
        if not isinstance(current_value, str):
            continue
        new_value, action_failures = render_action_value(action, current_value, translations)
        if action_failures:
            failures.extend({"file": rel, "key": key, **failure} for failure in action_failures)
            continue
        if new_value != current_value:
            assign(docs[rel], key, new_value)
            changed_by_file[rel] += 1
            totals["values_changed"] += 1
        if progress:
            progress("action", idx, len(plan["actions"]), f"{rel}::{key}")

    backup_dir: Path | None = None
    rels_to_write = [rel for rel in docs if changed_by_file.get(rel, 0)]
    if rels_to_write:
        backup_dir = REPORT_DIR / "backups" / time.strftime("super-repair-%Y%m%d-%H%M%S")
        for rel in rels_to_write:
            source_path = ctx.hyper_root / rel
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, backup_path)

    for rel in rels_to_write:
        doc = docs[rel]
        (ctx.hyper_root / rel).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        files_touched.add(rel)

    final = deep_audit(ctx)
    write_report("deep_audit_report.json", final)
    write_report("manual_review_queue.json", final["manual_review_queue"])
    write_manual_review_markdown(final["manual_review_queue"])
    write_deep_audit_verdict_markdown(final)
    report["final"] = final
    report["files_touched"] = sorted(files_touched)
    report["backup_dir"] = str(backup_dir) if backup_dir else None
    report["failures"] = failures
    report["translated_pieces"] = translated_records
    report["totals"] = dict(totals)
    if failures and report["mode"] == "apply":
        report["mode"] = "apply-partial"
    write_report("super_repair_report.json", report)
    write_super_repair_summary(report)
    return report


def similarity_audit(
    ctx: Context,
    threshold: float = DEFAULT_SIMILARITY_REPAIR_THRESHOLD,
    ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM,
    min_words: int = DEFAULT_SIMILARITY_MIN_WORDS,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    summary = Counter()
    by_file = Counter()
    by_bucket = Counter()

    for hp in sorted(ctx.hyper_root.rglob("*.json")):
        rel = hp.relative_to(ctx.hyper_root).as_posix()
        sp = ctx.source_for_rel(rel)
        if not sp.exists():
            continue
        summary["files"] += 1
        try:
            src_doc, dst_doc = load_pair(ctx, rel)
        except Exception as exc:
            blockers.append({"file": rel, "reason": "json_load_failed", "error": str(exc)})
            summary["json_load_failed"] += 1
            continue

        for key, source_value, target_value in walk_values(src_doc, dst_doc):
            if not isinstance(source_value, str) or not isinstance(target_value, str):
                continue
            summary["string_values"] += 1
            try:
                source_pieces = value_to_pieces(rel, key, source_value)
                target_pieces = value_to_pieces(rel, key, target_value)
            except Exception as exc:
                blockers.append({
                    "file": rel,
                    "key": key,
                    "reason": "parser_exception",
                    "error": repr(exc),
                    "source_preview": preview(source_value),
                    "target_preview": preview(target_value),
                })
                summary["parser_exception"] += 1
                continue

            if reassemble(source_pieces) != source_value:
                blockers.append({
                    "file": rel,
                    "key": key,
                    "reason": "source_roundtrip_failed",
                    "source_preview": preview(source_value),
                })
                summary["source_roundtrip_failed"] += 1
                continue
            if reassemble(target_pieces) != target_value:
                blockers.append({
                    "file": rel,
                    "key": key,
                    "reason": "target_roundtrip_failed",
                    "target_preview": preview(target_value),
                })
                summary["target_roundtrip_failed"] += 1
                continue

            source_fragments = human_fragments(source_pieces)
            target_fragments = human_fragments(target_pieces)
            if len(source_fragments) != len(target_fragments):
                blockers.append({
                    "file": rel,
                    "key": key,
                    "reason": "human_fragment_count_mismatch",
                    "source_count": len(source_fragments),
                    "target_count": len(target_fragments),
                    "source_preview": preview(source_value),
                    "target_preview": preview(target_value),
                })
                summary["human_fragment_count_mismatch"] += 1
                continue

            for fragment_index, (source_fragment, target_fragment) in enumerate(zip(source_fragments, target_fragments)):
                source_text = source_fragment["text"]
                target_text = target_fragment["text"]
                if not is_similarity_repair_candidate(source_text, ngram=ngram, min_words=min_words):
                    summary["skipped_short_or_trivial"] += 1
                    continue
                summary["human_fragments_checked"] += 1
                score = word_ngram_containment(source_text, target_text, ngram=ngram)
                if score < threshold:
                    continue
                finding = {
                    "category": "too-similar-to-original",
                    "reason": "word_ngram_containment",
                    "file": rel,
                    "key": key,
                    "fragment": fragment_index,
                    "piece_index": source_fragment["piece_index"],
                    "role": source_fragment["role"],
                    "score": round(score, 6),
                    "threshold": threshold,
                    "ngram": ngram,
                    "source_word_count": len(word_tokens_for_similarity(source_text)),
                    "source_fragment": source_text,
                    "target_fragment": target_text,
                    "source_preview": preview(source_value),
                    "target_preview": preview(target_value),
                    "recommended_action": "similarity-repair",
                }
                findings.append(finding)
                by_file[rel] += 1
                by_bucket[bucket_for_rel(rel)] += 1

    summary["findings"] = len(findings)
    summary["blockers"] = len(blockers)
    return {
        "schema_version": 1,
        "threshold": threshold,
        "ngram": ngram,
        "min_words": min_words,
        "metric": "word_trigram_containment" if ngram == 3 else f"word_{ngram}gram_containment",
        "summary": dict(summary),
        "counts": {
            "findings": len(findings),
            "blockers": len(blockers),
            "files_with_findings": len(by_file),
            "human_fragments_checked": summary["human_fragments_checked"],
            "string_values": summary["string_values"],
        },
        "by_file": dict(by_file.most_common()),
        "by_bucket": dict(by_bucket.most_common()),
        "findings": findings,
        "blockers": blockers,
    }


def build_similarity_repair_plan(
    ctx: Context,
    threshold: float = DEFAULT_SIMILARITY_REPAIR_THRESHOLD,
    ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM,
    min_words: int = DEFAULT_SIMILARITY_MIN_WORDS,
    audit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit_result = audit_result or similarity_audit(ctx, threshold=threshold, ngram=ngram, min_words=min_words)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    docs: dict[str, tuple[Any, Any]] = {}

    for finding in audit_result.get("findings", []):
        rel = finding["file"]
        key = finding["key"]
        if rel not in docs:
            docs[rel] = load_pair(ctx, rel)
        source_doc, target_doc = docs[rel]
        source_value = get_value(source_doc, key)
        current_value = get_value(target_doc, key)
        if not isinstance(source_value, str) or not isinstance(current_value, str):
            continue
        marker = (rel, key)
        action = grouped.get(marker)
        if not action:
            action = {
                "action_type": "similarity_fragment_retranslate",
                "file": rel,
                "key": key,
                "reason": "word_ngram_containment",
                "category": "not-hypertranslated",
                "source_preview": preview(source_value),
                "current_preview": preview(current_value),
                "proposed_preview": preview(current_value),
                "requires_translation": True,
                "translation_sources": [],
                "fragments": [],
                "source_value": source_value,
                "threshold": threshold,
                "ngram": ngram,
                "min_words": min_words,
            }
            grouped[marker] = action
        action["fragments"].append({
            "fragment": finding["fragment"],
            "piece_index": finding["piece_index"],
            "role": finding["role"],
            "score": finding["score"],
            "source_fragment": finding["source_fragment"],
            "target_fragment": finding["target_fragment"],
            "source_word_count": finding["source_word_count"],
        })
        if finding["source_fragment"] not in action["translation_sources"]:
            action["translation_sources"].append(finding["source_fragment"])

    actions = list(grouped.values())
    for action in actions:
        proposed = get_value(docs[action["file"]][1], action["key"])
        if not isinstance(proposed, str):
            proposed = action["current_preview"]
        for fragment in action["fragments"]:
            target_fragment = fragment["target_fragment"]
            marker = f"<translate:{preview(fragment['source_fragment'], 48)}>"
            if target_fragment in proposed:
                proposed = proposed.replace(target_fragment, marker, 1)
        action["proposed_preview"] = preview(proposed)

    translation_sources = []
    for action in actions:
        translation_sources.extend(action.get("translation_sources", []))
    translation_sources = list(dict.fromkeys(x for x in translation_sources if x and not is_trivial_human(x)))
    cached, missing, rejected_cache = cache_get_good_hyper_many(translation_sources, namespace=SIMILARITY_CACHE_NAMESPACE)
    return {
        "schema_version": 1,
        "cache_namespace": SIMILARITY_CACHE_NAMESPACE,
        "hops": DEFAULT_HOPS,
        "workers": DEFAULT_WORKERS,
        "threshold": threshold,
        "ngram": ngram,
        "min_words": min_words,
        "metric": audit_result["metric"],
        "audit_counts": audit_result["counts"],
        "action_counts": dict(Counter(action["action_type"] for action in actions)),
        "fragment_count": sum(len(action["fragments"]) for action in actions),
        "translation_estimate": {
            "fragments": len(translation_sources),
            "cache_hits": len(cached),
            "cache_misses": len(missing),
            "cache_rejected": len(rejected_cache),
        },
        "actions": actions,
        "blockers": audit_result.get("blockers", []),
    }


def validate_similarity_repair_value(
    rel: str,
    key: str,
    source_value: str,
    new_value: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    try:
        source_pieces = value_to_pieces(rel, key, source_value)
        new_pieces = value_to_pieces(rel, key, new_value)
    except Exception as exc:
        return [{"reason": "parser_exception_after_repair", "error": repr(exc)}]

    if reassemble(source_pieces) != source_value:
        failures.append({"reason": "source_roundtrip_failed"})
    if reassemble(new_pieces) != new_value:
        failures.append({"reason": "target_roundtrip_failed_after_repair"})
    sig_diff = diff_signature(value_signature(rel, key, source_value), value_signature(rel, key, new_value))
    if sig_diff:
        failures.append({"reason": "value_signature_mismatch_after_repair", "diff": sig_diff})
    if structural_fingerprint(rel, key, source_pieces) != structural_fingerprint(rel, key, new_pieces):
        failures.append({"reason": "structural_fingerprint_mismatch_after_repair"})
    if dialogue_command_signature(source_value) != dialogue_command_signature(new_value):
        failures.append({"reason": "dialogue_command_signature_mismatch_after_repair"})
    if dialogue_d_branch_signature(source_value) != dialogue_d_branch_signature(new_value):
        failures.append({"reason": "dialogue_d_branch_mismatch_after_repair"})
    if event_terminator_mismatch(rel, source_value, new_value):
        failures.append({"reason": "event_terminator_mismatch_after_repair"})
    for issue in token_boundary_issues(source_value, new_value):
        failures.append({"reason": issue["reason"], "token": issue["token"], "token_type": issue["token_type"]})
    source_fragments = human_fragments(source_pieces)
    new_fragments = human_fragments(new_pieces)
    if len(source_fragments) != len(new_fragments):
        failures.append({
            "reason": "human_fragment_count_mismatch_after_repair",
            "source_count": len(source_fragments),
            "target_count": len(new_fragments),
        })
    for idx, fragment in enumerate(new_fragments):
        if commandish_text(fragment["text"], rel):
            failures.append({"reason": "command_like_text_fragment_after_repair", "fragment": idx})
    return failures


def render_similarity_action_value(
    action: dict[str, Any],
    current_value: str,
    translations: dict[str, str],
) -> tuple[str, list[dict[str, Any]]]:
    rel = action["file"]
    key = action["key"]
    threshold = action.get("threshold", DEFAULT_SIMILARITY_REPAIR_THRESHOLD)
    ngram = action.get("ngram", DEFAULT_SIMILARITY_REPAIR_NGRAM)
    source_value = action["source_value"]
    try:
        source_pieces = value_to_pieces(rel, key, source_value)
        current_pieces = value_to_pieces(rel, key, current_value)
    except Exception as exc:
        return current_value, [{"reason": "parser_exception", "error": repr(exc)}]
    if reassemble(source_pieces) != source_value:
        return current_value, [{"reason": "source_roundtrip_failed"}]
    if reassemble(current_pieces) != current_value:
        return current_value, [{"reason": "current_roundtrip_failed"}]

    source_fragments = human_fragments(source_pieces)
    current_fragments = human_fragments(current_pieces)
    if len(source_fragments) != len(current_fragments):
        return current_value, [{
            "reason": "human_fragment_count_mismatch",
            "source_count": len(source_fragments),
            "target_count": len(current_fragments),
        }]

    flagged = {fragment["fragment"]: fragment for fragment in action.get("fragments", [])}
    failures: list[dict[str, Any]] = []
    fragment_index = 0

    def choose_fragment(source_text: str, current_text: str) -> str:
        nonlocal fragment_index
        flagged_fragment = flagged.get(fragment_index)
        fragment_index += 1
        if not flagged_fragment:
            return current_text
        translated = translations.get(source_text)
        if not translated:
            failures.append({"reason": "missing_translation", "piece": source_text})
            return current_text
        translated = sanitize_generated_text(translated, rel, key, source_value)
        if not is_good_hyper_result(source_text, translated):
            failures.append({"reason": "identity_translation", "piece": source_text, "target": translated})
            return current_text
        score = word_ngram_containment(source_text, translated, ngram=ngram)
        if score >= threshold:
            failures.append({
                "reason": "still_too_similar_after_translation",
                "piece": source_text,
                "target": translated,
                "score": round(score, 6),
            })
            return current_text
        return translated

    current_fragment_index = 0
    out_pieces: list[Piece] = []
    for piece in source_pieces:
        if piece.type in ("text", "emote"):
            current_text = current_fragments[current_fragment_index]["text"]
            out_pieces.append(Piece(piece.type, choose_fragment(piece.value, current_text)))
            current_fragment_index += 1
        elif piece.type == "gender":
            values = []
            for value in piece.values:
                current_text = current_fragments[current_fragment_index]["text"]
                values.append(choose_fragment(value, current_text))
                current_fragment_index += 1
            out_pieces.append(Piece("gender", values=values))
        else:
            out_pieces.append(piece)

    if failures:
        return current_value, failures
    new_value = reassemble(out_pieces)
    validation_failures = validate_similarity_repair_value(rel, key, source_value, new_value)
    if validation_failures:
        return current_value, validation_failures
    return new_value, failures


def write_similarity_repair_summary(report: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "similarity_repair_summary.md"
    plan = report["plan"]
    similarity_after = report.get("final_similarity") or {"counts": plan["audit_counts"]}
    lines = [
        "# HyperStardew Similarity Repair Summary",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Threshold: {plan['threshold']}",
        f"- N-gram size: {plan['ngram']}",
        f"- Minimum source words: {plan.get('min_words', DEFAULT_SIMILARITY_MIN_WORDS)}",
        f"- Actions planned: {len(plan['actions'])}",
        f"- Fragments planned: {plan['fragment_count']}",
        f"- Files touched: {len(report.get('files_touched', []))}",
        f"- Backup dir: `{report.get('backup_dir') or 'none'}`",
        f"- Values changed: {report['totals'].get('values_changed', 0)}",
        f"- Pieces hypertranslated: {report['totals'].get('pieces_translated', 0)}",
        f"- Cache hits: {report['totals'].get('cache_hits', 0)}",
        f"- Cache misses: {report['totals'].get('cache_misses', 0)}",
        f"- Cache rejected: {report['totals'].get('cache_rejected', 0)}",
        f"- Cache namespace: `{plan['cache_namespace']}`",
        "",
        "## Similarity Counts",
        "",
        f"- Before: {plan['audit_counts']['findings']}",
        f"- After: {similarity_after['counts']['findings']}",
        "",
    ]
    if report.get("final_deep"):
        counts = report["final_deep"]["counts"]
        lines.extend([
            "## Deep Audit After",
            "",
            f"- crash-risk: {counts['crash_risk_findings']}",
            f"- display-risk: {counts['display_risk_findings']}",
            f"- not-hypertranslated: {counts['not_hypertranslated_findings']}",
            "",
        ])
    if report.get("failures"):
        lines.extend(["## Failures", ""])
        for item in report["failures"][:100]:
            location = f"`{item.get('file')}::{item.get('key')}`" if item.get("file") and item.get("key") else "`translation`"
            detail = item.get("error") or item.get("reason") or "failed"
            piece = f" piece={preview(item.get('piece', ''), 90)!r}" if item.get("piece") else ""
            lines.append(f"- {location} {item.get('reason', 'failed')}: {detail}{piece}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def similarity_repair(
    ctx: Context,
    apply: bool = False,
    assume_yes: bool = False,
    threshold: float = DEFAULT_SIMILARITY_REPAIR_THRESHOLD,
    ngram: int = DEFAULT_SIMILARITY_REPAIR_NGRAM,
    min_words: int = DEFAULT_SIMILARITY_MIN_WORDS,
    progress: Any = None,
) -> dict[str, Any]:
    audit_result = similarity_audit(ctx, threshold=threshold, ngram=ngram, min_words=min_words)
    plan = build_similarity_repair_plan(
        ctx,
        threshold=threshold,
        ngram=ngram,
        min_words=min_words,
        audit_result=audit_result,
    )
    write_report("similarity_audit_report.json", audit_result)
    write_report("similarity_repair_plan.json", plan)

    totals = Counter()
    failures: list[dict[str, Any]] = []
    translated_records: list[dict[str, Any]] = []
    files_touched: set[str] = set()
    mode = "apply" if apply else "dry-run"

    translation_sources = []
    for action in plan["actions"]:
        translation_sources.extend(action.get("translation_sources", []))
    translation_sources = list(dict.fromkeys(x for x in translation_sources if x and not is_trivial_human(x)))
    cached, missing, rejected_cache = cache_get_good_hyper_many(translation_sources, namespace=SIMILARITY_CACHE_NAMESPACE)
    totals["cache_hits"] = len(cached)
    totals["cache_misses"] = len(missing)
    totals["cache_rejected"] = len(rejected_cache)

    report: dict[str, Any] = {
        "mode": mode,
        "plan": plan,
        "files_touched": [],
        "backup_dir": None,
        "failures": failures,
        "translated_pieces": translated_records,
        "backend_metrics": {},
        "totals": {},
        "final_similarity": audit_result,
        "final_deep": None,
    }

    if not apply:
        report["totals"] = dict(totals)
        write_report("similarity_repair_report.json", report)
        write_similarity_repair_summary(report)
        return report

    if not assume_yes:
        print("Similarity-repair is about to write JSON files.")
        print(f"Actions: {len(plan['actions'])}; fragments: {plan['fragment_count']}; cache misses: {len(missing)}")
        confirmation = input("Type APPLY to continue: ").strip()
        if confirmation != "APPLY":
            report["mode"] = "cancelled"
            report["totals"] = dict(totals)
            write_report("similarity_repair_report.json", report)
            write_similarity_repair_summary(report)
            return report

    translated, translate_failures, records, backend_metrics = translate_missing_super(
        missing,
        progress=progress,
        namespace=SIMILARITY_CACHE_NAMESPACE,
    )
    translations = {**cached, **translated}
    failures.extend({"reason": "translation_failed", **failure} for failure in translate_failures)
    translated_records.extend(records)
    totals["pieces_translated"] = len(records)
    totals["backend_requests"] = backend_metrics.get("requests", 0)
    totals["backend_retries"] = backend_metrics.get("retries", 0)
    totals["backend_failures"] = backend_metrics.get("failures", 0)
    totals["backend_rate_limit_waits"] = backend_metrics.get("rate_limit_waits", 0)
    report["backend_metrics"] = backend_metrics

    docs: dict[str, Any] = {}
    changed_by_file: dict[str, int] = Counter()
    for idx, action in enumerate(plan["actions"], start=1):
        rel = action["file"]
        key = action["key"]
        if rel not in docs:
            _, docs[rel] = load_pair(ctx, rel)
        current_value = get_value(docs[rel], key)
        if not isinstance(current_value, str):
            continue
        new_value, action_failures = render_similarity_action_value(action, current_value, translations)
        if action_failures:
            failures.extend({"file": rel, "key": key, **failure} for failure in action_failures)
            continue
        if new_value != current_value:
            assign(docs[rel], key, new_value)
            changed_by_file[rel] += 1
            totals["values_changed"] += 1
        if progress:
            progress("action", idx, len(plan["actions"]), f"{rel}::{key}")

    rels_to_write = [rel for rel in docs if changed_by_file.get(rel, 0)]
    backup_dir: Path | None = None
    if rels_to_write:
        backup_dir = REPORT_DIR / "backups" / time.strftime("similarity-repair-%Y%m%d-%H%M%S")
        for rel in rels_to_write:
            source_path = ctx.hyper_root / rel
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, backup_path)

    for rel in rels_to_write:
        (ctx.hyper_root / rel).write_text(json.dumps(docs[rel], ensure_ascii=False, indent=2), encoding="utf-8")
        files_touched.add(rel)

    final_deep = deep_audit(ctx)
    final_similarity = similarity_audit(ctx, threshold=threshold, ngram=ngram, min_words=min_words)
    write_report("deep_audit_report.json", final_deep)
    write_report("manual_review_queue.json", final_deep["manual_review_queue"])
    write_manual_review_markdown(final_deep["manual_review_queue"])
    write_deep_audit_verdict_markdown(final_deep)
    write_report("similarity_audit_report.json", final_similarity)
    report["final_deep"] = final_deep
    report["final_similarity"] = final_similarity
    report["files_touched"] = sorted(files_touched)
    report["backup_dir"] = str(backup_dir) if backup_dir else None
    report["failures"] = failures
    report["translated_pieces"] = translated_records
    report["totals"] = dict(totals)
    if failures and report["mode"] == "apply":
        report["mode"] = "apply-partial"
    write_report("similarity_repair_report.json", report)
    write_similarity_repair_summary(report)
    return report


def write_report(name: str, data: Any) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_manual_review_markdown(queue: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "manual_review_queue.md"
    lines = [
        "# HyperStardew Manual Review Queue",
        "",
        "Generated by `python3 -B tools/hyperstardew_tool.py deep-audit`.",
        "",
        "## Summary",
        "",
        f"- Findings requiring attention: {queue['summary']['finding_count']}",
        f"- High-risk strings pending manual review: {queue['summary']['high_risk_count']}",
        f"- Stratified sample items: {queue['summary']['stratified_sample_count']}",
        f"- Manual review complete: {queue['summary']['manual_review_complete']}",
        "",
        "## Findings",
        "",
    ]
    findings = queue.get("findings", [])
    if not findings:
        lines.append("- None.")
    for item in findings[:MANUAL_QUEUE_LIMIT_MD]:
        lines.extend([
            f"- `{item['category']}` / `{item['reason']}` in `{item['file']}::{item['key']}`",
            f"  - source: {preview(item.get('source_fragment') or item.get('source_preview', ''), 180)}",
            f"  - target: {preview(item.get('target_fragment') or item.get('target_preview', ''), 180)}",
            f"  - action: `{item.get('recommended_action', 'manual-review')}`",
        ])
    if len(findings) > MANUAL_QUEUE_LIMIT_MD:
        lines.append(f"- ... {len(findings) - MANUAL_QUEUE_LIMIT_MD} more findings in `manual_review_queue.json`.")

    lines.extend(["", "## High Risk Pending Manual Review", ""])
    high_risk = queue.get("high_risk", [])
    if not high_risk:
        lines.append("- None.")
    for item in high_risk[:MANUAL_QUEUE_LIMIT_MD]:
        lines.extend([
            f"- `{item['reason']}` in `{item['file']}::{item['key']}`",
            f"  - source: {preview(item.get('source_preview', ''), 180)}",
            f"  - target: {preview(item.get('target_preview', ''), 180)}",
        ])
    if len(high_risk) > MANUAL_QUEUE_LIMIT_MD:
        lines.append(f"- ... {len(high_risk) - MANUAL_QUEUE_LIMIT_MD} more high-risk items in `manual_review_queue.json`.")

    lines.extend(["", "## Stratified Samples", ""])
    for item in queue.get("stratified_samples", []):
        lines.extend([
            f"- `{item['reason']}` sample in `{item['file']}::{item['key']}`",
            f"  - source: {preview(item.get('source_preview', ''), 160)}",
            f"  - target: {preview(item.get('target_preview', ''), 160)}",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_deep_audit_verdict_markdown(result: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "deep_audit_verdict.md"
    counts = result["counts"]
    criteria = result["criteria"]
    base = result["base_audit"]
    cache = result["cache"]
    lines = [
        "# HyperStardew Deep Audit Verdict",
        "",
        "## What Was Audited",
        "",
        f"- String values checked: {counts['string_values']}",
        f"- Shape issues from base audit: {base['total_shape_issues']}",
        f"- Signature issues from base audit: {base['total_signature_issues']}",
        f"- Modified hyper files in current diff: {counts['modified_hyper_files']}",
        f"- Cache rows: {cache['rows']} total, {cache['valid_hops25_rows']} with hops25 namespace, {cache['legacy_rows']} legacy",
        "",
        "## Findings",
        "",
        f"- Total findings: {counts['findings']}",
        f"- Crash-risk findings: {counts['crash_risk_findings']}",
        f"- Display-risk findings: {counts['display_risk_findings']}",
        f"- Not-hypertranslated findings: {counts['not_hypertranslated_findings']}",
        f"- High-risk manual review items: {counts['high_risk_manual_review_items']}",
        f"- Stratified samples generated: {counts['stratified_sample_items']}",
        "",
        "## Criteria",
        "",
    ]
    for name, ok in criteria.items():
        lines.append(f"- {name}: {ok}")
    lines.extend([
        "",
        "## Verdict",
        "",
    ])
    if criteria["no_known_surprises"]:
        lines.append("The mod passed the deep audit criteria.")
    else:
        lines.append("The mod did not pass the deep audit criteria. It should not be called really correct yet.")
        if not criteria["structurally_safe"]:
            lines.append("- Structural safety is not proven because crash-risk or grammar findings remain.")
        if not criteria["really_hypertranslated"]:
            lines.append("- Hypertranslation is not proven because original or near-original human fragments remain.")
        if not criteria["manual_review_complete"]:
            lines.append("- Manual review is not complete; inspect `manual_review_queue.md` / `.json`.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_audit_result(result: dict[str, Any]) -> None:
    print("=" * 70)
    print(f"Shape issues: {result['total_shape_issues']} in {result['files_with_shape_issues']} files")
    print(f"Signature issues: {result['total_signature_issues']} in {result['files_with_signature_issues']} files")
    for name, count in sorted(result["summary"].items(), key=lambda x: (-x[1], x[0]))[:20]:
        print(f"  {name:<28} {count}")


def print_deep_audit_result(result: dict[str, Any]) -> None:
    counts = result["counts"]
    criteria = result["criteria"]
    print("=" * 70)
    print(f"String values checked: {counts['string_values']}")
    print(f"Findings: {counts['findings']}")
    print(f"  crash-risk: {counts['crash_risk_findings']}")
    print(f"  display-risk: {counts['display_risk_findings']}")
    print(f"  not-hypertranslated: {counts['not_hypertranslated_findings']}")
    print(f"High-risk manual review queue: {counts['high_risk_manual_review_items']}")
    print(f"Stratified samples: {counts['stratified_sample_items']}")
    print("Criteria:")
    for name, ok in criteria.items():
        print(f"  {name:<24} {ok}")


def translate_smoke() -> dict[str, Any]:
    terms = TRANSLATE_SMOKE_TERMS
    cached, missing, rejected = cache_get_good_hyper_many(terms, namespace=SUPER_CACHE_NAMESPACE)
    translated, failures, records, backend_metrics = translate_missing_super(missing)
    results = []
    for source, target in cached.items():
        results.append({
            "source": source,
            "target": target,
            "source_kind": "cache",
            "ok": is_good_hyper_result(source, target),
        })
    for record in records:
        results.append({
            "source": record["source"],
            "target": record["target"],
            "source_kind": record.get("route_kind", "translated"),
            "route": record.get("route", []),
            "ok": is_good_hyper_result(record["source"], record["target"]),
        })
    missing_after = sorted(set(terms) - {item["source"] for item in results})
    report = {
        "cache_namespace": SUPER_CACHE_NAMESPACE,
        "terms": terms,
        "cache_hits": len(cached),
        "cache_rejected": len(rejected),
        "translated": len(records),
        "failures": failures,
        "missing_after": missing_after,
        "results": sorted(results, key=lambda item: terms.index(item["source"])),
        "backend_metrics": backend_metrics,
        "passed": not failures and not missing_after and all(item["ok"] for item in results),
    }
    write_report("translate_smoke_report.json", report)
    return report


def make_context(args: argparse.Namespace) -> Context:
    return Context(mod_dir=Path(args.mod_dir).resolve(), source_root=Path(args.source_root).resolve())


def run_tui(ctx: Context) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.widgets import DataTable, Footer, Header, ProgressBar, RichLog, Static
    except Exception as exc:
        print(f"Textual is not available: {exc}")
        return 1

    class HyperStardewTUI(App):
        CSS = """
        Screen { layout: vertical; }
        #dashboard {
            height: 7;
            border: solid $accent;
            padding: 1 2;
        }
        .progress-label {
            height: 1;
            padding: 0 1;
        }
        ProgressBar {
            height: 1;
            margin: 0 1;
        }
        #actions {
            height: 1fr;
            border: solid $primary;
        }
        #log {
            height: 10;
            border: solid $secondary;
        }
        """
        BINDINGS = [
            Binding("a", "audit", "Audit"),
            Binding("p", "plan", "Plan"),
            Binding("x", "stability_plan", "Stability"),
            Binding("s", "resume", "Resume"),
            Binding("d", "dry_run", "Dry-run"),
            Binding("r", "run_apply", "Apply"),
            Binding("v", "preview", "Preview"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(self, context: Context):
            super().__init__()
            self.ctx = context
            self.audit_result: dict[str, Any] | None = None
            self.plan: dict[str, Any] | None = None
            self.confirm_apply = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("Pressione 'a' para auditar, 'p' para plano completo, 'x' para plano estabilidade, 's' para retomar plano salvo, 'r' duas vezes para aplicar.", id="dashboard")
            yield Static("Plano: parado", id="plan-status", classes="progress-label")
            yield ProgressBar(total=1, show_eta=False, id="plan-progress")
            yield Static("Traduções: parado", id="translation-status", classes="progress-label")
            yield ProgressBar(total=1, show_eta=False, id="translation-progress")
            yield DataTable(id="actions")
            yield RichLog(id="log", wrap=True, highlight=True)
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#actions", DataTable)
            table.cursor_type = "row"
            table.add_columns("Action", "Reason", "File", "Key", "Translate", "Preview")
            self.write_log("TUI pronta. Nada é escrito sem confirmação explícita.")

        def write_log(self, message: str) -> None:
            self.query_one("#log", RichLog).write(message)

        def set_dashboard(self, text: str) -> None:
            self.query_one("#dashboard", Static).update(text)

        def set_progress(self, kind: str, done: int, total: int, text: str = "") -> None:
            total = max(total, 1)
            if kind == "action":
                self.query_one("#plan-status", Static).update(f"Plano/aplicação: {done}/{total} {preview(text, 90)}")
                self.query_one("#plan-progress", ProgressBar).update(total=total, progress=done)
            else:
                self.query_one("#translation-status", Static).update(f"Traduções: {done}/{total} {kind} {preview(text, 90)}")
                self.query_one("#translation-progress", ProgressBar).update(total=total, progress=done)

        def reset_progress(self, message: str) -> None:
            self.query_one("#plan-status", Static).update(message)
            self.query_one("#plan-progress", ProgressBar).update(total=1, progress=0)
            self.query_one("#translation-status", Static).update("Traduções: parado")
            self.query_one("#translation-progress", ProgressBar).update(total=1, progress=0)

        def load_plan_into_table(self) -> None:
            table = self.query_one("#actions", DataTable)
            table.clear()
            if not self.plan:
                return
            for action in self.plan["actions"][:1000]:
                table.add_row(
                    action["action_type"],
                    action["reason"],
                    action["file"],
                    action["key"],
                    "yes" if action.get("requires_translation") else "no",
                    preview(action.get("proposed_preview", ""), 80),
                )

        def update_dashboard_from_plan(self) -> None:
            if not self.plan:
                self.set_dashboard("Sem plano. Pressione 'p'.")
                return
            counts = self.plan["audit_counts"]
            actions = self.plan["action_counts"]
            tr = self.plan["translation_estimate"]
            lines = [
                f"Findings: crash={counts['crash_risk_findings']} display={counts['display_risk_findings']} not-hyper={counts['not_hypertranslated_findings']}",
                "Actions: " + ", ".join(f"{k}={v}" for k, v in sorted(actions.items())),
                f"Translations: fragments={tr['fragments']} cache_hits={tr['cache_hits']} cache_misses={tr['cache_misses']} rejected={tr.get('cache_rejected', 0)}",
                f"Stability only: {self.plan.get('stability_only', False)}",
                "Dry-run is default. Pressione 'r' duas vezes para aplicar o plano atual.",
            ]
            self.set_dashboard("\n".join(lines))

        def action_audit(self) -> None:
            self.write_log("Rodando deep-audit...")
            self.reset_progress("Audit: rodando")
            self.run_worker(self.audit_worker, thread=True)

        def audit_worker(self) -> None:
            result = deep_audit(self.ctx)
            write_report("deep_audit_report.json", result)
            write_report("manual_review_queue.json", result["manual_review_queue"])
            write_manual_review_markdown(result["manual_review_queue"])
            write_deep_audit_verdict_markdown(result)
            self.call_from_thread(self.finish_audit, result)

        def finish_audit(self, result: dict[str, Any]) -> None:
            self.audit_result = result
            c = result["counts"]
            self.set_dashboard(
                f"Audit concluído: findings={c['findings']} crash={c['crash_risk_findings']} "
                f"display={c['display_risk_findings']} not-hyper={c['not_hypertranslated_findings']}\n"
                "Pressione 'p' para montar plano seguro."
            )
            self.write_log("Audit salvo em tools/reports/deep_audit_report.json")
            self.set_progress("action", 1, 1, "audit completo")

        def action_plan(self) -> None:
            self.write_log("Montando RepairPlan seguro...")
            self.reset_progress("Plano: montando")
            self.run_worker(self.plan_worker, thread=True)

        def plan_worker(self) -> None:
            result = self.audit_result or deep_audit(self.ctx)
            plan = build_super_repair_plan(self.ctx, result, stability_only=False)
            write_report("super_repair_plan.json", plan)
            self.call_from_thread(self.finish_plan, result, plan)

        def action_stability_plan(self) -> None:
            self.write_log("Montando plano de estabilidade: só crash/display/estrutura, sem not-hyper estético.")
            self.reset_progress("Plano estabilidade: montando")
            self.run_worker(self.stability_plan_worker, thread=True)

        def stability_plan_worker(self) -> None:
            result = self.audit_result or deep_audit(self.ctx)
            plan = build_super_repair_plan(self.ctx, result, stability_only=True)
            write_report("super_repair_plan.json", plan)
            self.call_from_thread(self.finish_plan, result, plan)

        def finish_plan(self, result: dict[str, Any], plan: dict[str, Any]) -> None:
            self.audit_result = result
            self.plan = plan
            self.load_plan_into_table()
            self.update_dashboard_from_plan()
            self.write_log("Plano salvo em tools/reports/super_repair_plan.json")
            self.set_progress("action", 1, 1, "plano completo")

        def action_dry_run(self) -> None:
            self.write_log("Rodando super-repair em dry-run...")
            self.reset_progress("Dry-run: rodando")
            self.run_worker(self.dry_run_worker, thread=True)

        def dry_run_worker(self) -> None:
            report = super_repair(self.ctx, apply=False, assume_yes=True)
            self.call_from_thread(self.finish_dry_run, report)

        def finish_dry_run(self, report: dict[str, Any]) -> None:
            self.plan = report["plan"]
            self.load_plan_into_table()
            self.update_dashboard_from_plan()
            self.write_log("Dry-run concluído. Nenhum JSON do mod foi escrito.")
            self.write_log("Relatórios: super_repair_plan.json, super_repair_report.json, super_repair_summary.md")
            self.set_progress("action", 1, 1, "dry-run completo")

        def action_resume(self) -> None:
            try:
                self.plan = load_super_repair_plan()
            except Exception as exc:
                self.write_log(f"Não consegui carregar plano salvo: {exc}")
                return
            self.load_plan_into_table()
            self.update_dashboard_from_plan()
            self.write_log("Plano salvo carregado. Nada foi aplicado; pressione 'r' duas vezes para aplicar.")

        def action_run_apply(self) -> None:
            if not self.plan:
                self.write_log("Nenhum plano carregado. Rode 'p' para planejar ou 's' para retomar um plano salvo.")
                return
            if not self.confirm_apply:
                self.confirm_apply = True
                self.write_log("Confirmação necessária: pressione 'r' novamente para aplicar e escrever JSONs.")
                return
            self.confirm_apply = False
            self.write_log("Aplicando plano. Acompanhe traduções e cache abaixo.")
            self.reset_progress("Aplicação: iniciando")
            self.run_worker(self.apply_worker, thread=True)

        def apply_worker(self) -> None:
            def progress(kind: str, done: int, total: int, text: str) -> None:
                self.call_from_thread(self.set_progress, kind, done, total, text)
                self.call_from_thread(self.write_log, f"{kind} {done}/{total}: {preview(text, 90)}")
            try:
                report = super_repair(self.ctx, apply=True, assume_yes=True, progress=progress, resume=True)
            except Exception as exc:
                self.call_from_thread(self.write_log, f"Falha ao aplicar plano salvo: {exc}")
                return
            self.call_from_thread(self.finish_apply, report)

        def finish_apply(self, report: dict[str, Any]) -> None:
            final = report["final"]["counts"]
            self.write_log(
                f"Aplicação concluída: crash={final['crash_risk_findings']} "
                f"display={final['display_risk_findings']} not-hyper={final['not_hypertranslated_findings']}"
            )
            self.write_log("Relatórios finais atualizados em tools/reports.")
            self.plan = report["plan"]
            self.load_plan_into_table()
            self.update_dashboard_from_plan()
            self.set_progress("action", 1, 1, "aplicação completa")

        def action_preview(self) -> None:
            table = self.query_one("#actions", DataTable)
            if not self.plan or table.cursor_row is None:
                self.write_log("Nenhuma ação selecionada.")
                return
            idx = table.cursor_row
            if idx >= len(self.plan["actions"]):
                return
            action = self.plan["actions"][idx]
            self.write_log(f"PREVIEW {action['action_type']} {action['file']}::{action['key']}")
            self.write_log(f"current: {action.get('current_preview', '')}")
            self.write_log(f"proposed: {action.get('proposed_preview', '')}")

    HyperStardewTUI(ctx).run()
    return 0


def menu(ctx: Context) -> int:
    while True:
        print("\nHyperStardew tools")
        print("1. Audit structure")
        print("2. Repair legacy signature issues")
        print("3. Profile original structure")
        print("4. Deep audit + manual review queue")
        print("5. Super repair dry-run plan")
        print("6. Stability-only dry-run plan")
        print("7. Translate smoke test")
        print("8. Launch Textual TUI")
        print("9. Similarity audit")
        print("10. Similarity repair dry-run")
        print("11. Exit")
        choice = input("> ").strip()
        if choice == "1":
            result = audit(ctx)
            print_audit_result(result)
            print(f"Report: {write_report('deep_structure_validation.json', result)}")
        elif choice == "2":
            result = repair(ctx)
            print_audit_result(result["after"])
            print(f"Report: {write_report('repair_report.json', result)}")
        elif choice == "3":
            result = profile(ctx)
            print(f"Files: {result['files']} Values: {result['values']} y_dialogues: {result['y_dialogues']}")
            print("Top tokens:")
            for name, count in list(result["token_counts"].items())[:20]:
                print(f"  {name:<24} {count}")
            print(f"Report: {write_report('source_profile.json', result)}")
        elif choice == "4":
            result = deep_audit(ctx)
            print_deep_audit_result(result)
            print(f"Report: {write_report('deep_audit_report.json', result)}")
            print(f"Manual queue JSON: {write_report('manual_review_queue.json', result['manual_review_queue'])}")
            print(f"Manual queue MD: {write_manual_review_markdown(result['manual_review_queue'])}")
            print(f"Verdict: {write_deep_audit_verdict_markdown(result)}")
        elif choice == "5":
            result = super_repair(ctx, apply=False, assume_yes=True)
            print("Dry-run complete. No mod JSON files were written.")
            print(f"Actions planned: {len(result['plan']['actions'])}")
            print(f"Action counts: {result['plan']['action_counts']}")
            print(f"Translations needed: {result['plan']['translation_estimate']}")
            print("Report: tools/reports/super_repair_report.json")
            print("Summary: tools/reports/super_repair_summary.md")
        elif choice == "6":
            result = super_repair(ctx, apply=False, assume_yes=True, stability_only=True)
            print("Stability dry-run complete. No mod JSON files were written.")
            print(f"Actions planned: {len(result['plan']['actions'])}")
            print(f"Action counts: {result['plan']['action_counts']}")
            print(f"Translations needed: {result['plan']['translation_estimate']}")
        elif choice == "7":
            result = translate_smoke()
            print(f"Translate smoke passed: {result['passed']}")
            print(f"Report: {REPORT_DIR / 'translate_smoke_report.json'}")
        elif choice == "8":
            return run_tui(ctx)
        elif choice == "9":
            result = similarity_audit(ctx)
            print(f"Similarity findings: {result['counts']['findings']} at threshold {result['threshold']}")
            print(f"Report: {write_report('similarity_audit_report.json', result)}")
        elif choice == "10":
            result = similarity_repair(ctx, apply=False, assume_yes=True)
            print("Similarity dry-run complete. No mod JSON files were written.")
            print(f"Actions planned: {len(result['plan']['actions'])}")
            print(f"Fragments planned: {result['plan']['fragment_count']}")
            print(f"Translations needed: {result['plan']['translation_estimate']}")
            print("Report: tools/reports/similarity_repair_report.json")
            print("Summary: tools/reports/similarity_repair_summary.md")
        elif choice == "11":
            return 0
        else:
            print("Invalid option.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HyperStardew audit/repair tool")
    parser.add_argument("command", nargs="?", choices=["menu", "audit", "repair", "profile", "deep-audit", "super-repair", "similarity-audit", "similarity-repair", "translate-smoke", "tui"], default="menu")
    parser.add_argument("--mod-dir", default=str(DEFAULT_MOD_DIR))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--dry-run", action="store_true", help="For repair commands, build the plan and reports without writing mod JSONs. This is the default.")
    parser.add_argument("--apply", action="store_true", help="For repair commands, apply the planned safe repairs after explicit confirmation.")
    parser.add_argument("--resume", action="store_true", help="For super-repair, reuse tools/reports/super_repair_plan.json instead of recalculating a new plan.")
    parser.add_argument("--stability-only", action="store_true", help="For super-repair, plan only crash/display/structural fixes and skip not-hypertranslated quality fixes.")
    parser.add_argument("--event-choice-quality", action="store_true", help="For super-repair, also repair original/near-original text inside Data/Events, Data/Festivals, and dialogue choice strings.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_REPAIR_THRESHOLD, help="For similarity-audit/repair, word n-gram containment threshold. Default: 0.60.")
    parser.add_argument("--ngram", type=int, default=DEFAULT_SIMILARITY_REPAIR_NGRAM, help="For similarity-audit/repair, word n-gram size. Default: 3.")
    parser.add_argument("--min-words", type=int, default=DEFAULT_SIMILARITY_MIN_WORDS, help="For similarity-audit/repair, ignore source fragments shorter than this many words. Default: 8.")
    parser.add_argument("--yes", action="store_true", help="For repair --apply, skip the typed APPLY confirmation. Intended for the TUI or explicit automation.")
    args = parser.parse_args(argv)
    if args.command in {"super-repair", "similarity-repair"} and args.apply and args.dry_run:
        parser.error("--dry-run and --apply cannot be used together")
    if args.ngram <= 0:
        parser.error("--ngram must be positive")
    if args.min_words <= 0:
        parser.error("--min-words must be positive")
    ctx = make_context(args)
    if args.command == "menu":
        return menu(ctx)
    if args.command == "tui":
        return run_tui(ctx)
    if args.command == "audit":
        result = audit(ctx)
        print_audit_result(result)
        print(f"Report: {write_report('deep_structure_validation.json', result)}")
        return 1 if result["total_shape_issues"] or result["total_signature_issues"] else 0
    if args.command == "repair":
        result = repair(ctx)
        print_audit_result(result["after"])
        print(f"Report: {write_report('repair_report.json', result)}")
        return 1 if result["after"]["total_shape_issues"] or result["after"]["total_signature_issues"] else 0
    if args.command == "profile":
        result = profile(ctx)
        print(f"Files: {result['files']} Values: {result['values']} y_dialogues: {result['y_dialogues']}")
        print(f"Report: {write_report('source_profile.json', result)}")
        return 0
    if args.command == "deep-audit":
        result = deep_audit(ctx)
        print_deep_audit_result(result)
        print(f"Report: {write_report('deep_audit_report.json', result)}")
        print(f"Manual queue JSON: {write_report('manual_review_queue.json', result['manual_review_queue'])}")
        print(f"Manual queue MD: {write_manual_review_markdown(result['manual_review_queue'])}")
        print(f"Verdict: {write_deep_audit_verdict_markdown(result)}")
        return 0 if result["criteria"]["no_known_surprises"] else 1
    if args.command == "similarity-audit":
        result = similarity_audit(ctx, threshold=args.threshold, ngram=args.ngram, min_words=args.min_words)
        print("=" * 70)
        print(f"Similarity findings: {result['counts']['findings']}")
        print(f"Files with findings: {result['counts']['files_with_findings']}")
        print(f"Human fragments checked: {result['counts']['human_fragments_checked']}")
        print(f"Threshold: {result['threshold']} / ngram: {result['ngram']} / min_words: {result['min_words']}")
        print(f"Report: {write_report('similarity_audit_report.json', result)}")
        return 0 if result["counts"]["findings"] == 0 and result["counts"]["blockers"] == 0 else 1
    if args.command == "similarity-repair":
        result = similarity_repair(
            ctx,
            apply=args.apply,
            assume_yes=args.yes,
            threshold=args.threshold,
            ngram=args.ngram,
            min_words=args.min_words,
        )
        print(f"Mode: {result['mode']}")
        print(f"Actions planned: {len(result['plan']['actions'])}")
        print(f"Fragments planned: {result['plan']['fragment_count']}")
        print(f"Translations: {result['plan']['translation_estimate']}")
        print("Report: tools/reports/similarity_repair_report.json")
        print("Summary: tools/reports/similarity_repair_summary.md")
        if not args.apply:
            print("Dry-run only. No mod JSON files were written. Use `similarity-repair --apply` to apply.")
            return 0
        if result.get("final_deep"):
            print_deep_audit_result(result["final_deep"])
        final_similarity = result.get("final_similarity", {"counts": {"findings": 1, "blockers": 1}})
        deep_counts = result.get("final_deep", {}).get("counts", {})
        deep_ok = not (
            deep_counts.get("crash_risk_findings", 1)
            or deep_counts.get("display_risk_findings", 1)
            or deep_counts.get("not_hypertranslated_findings", 1)
        )
        return 0 if deep_ok and final_similarity["counts"]["findings"] == 0 and not result.get("failures") else 1
    if args.command == "translate-smoke":
        result = translate_smoke()
        print(f"Translate smoke passed: {result['passed']}")
        print(f"Cache hits: {result['cache_hits']} translated: {result['translated']} failures: {len(result['failures'])}")
        for item in result["results"]:
            print(f"  {item['source']!r} -> {item['target']!r} [{item['source_kind']}]")
        if result["failures"]:
            for failure in result["failures"][:20]:
                print(f"  failed {failure.get('piece')!r}: {failure.get('error')}")
        print("Report: tools/reports/translate_smoke_report.json")
        return 0 if result["passed"] else 1
    if args.command == "super-repair":
        result = super_repair(
            ctx,
            apply=args.apply,
            assume_yes=args.yes,
            resume=args.resume,
            stability_only=args.stability_only,
            event_choice_quality=args.event_choice_quality,
        )
        print(f"Mode: {result['mode']}")
        print(f"Actions planned: {len(result['plan']['actions'])}")
        print(f"Action counts: {result['plan']['action_counts']}")
        print(f"Translations: {result['plan']['translation_estimate']}")
        print("Report: tools/reports/super_repair_report.json")
        print("Summary: tools/reports/super_repair_summary.md")
        if not args.apply:
            print("Dry-run only. No mod JSON files were written. Use `super-repair --apply` or the TUI to apply.")
            return 0
        print_deep_audit_result(result["final"])
        counts = result["final"]["counts"]
        if args.stability_only:
            return 0 if not (counts["crash_risk_findings"] or counts["display_risk_findings"]) else 1
        return 0 if not (counts["crash_risk_findings"] or counts["display_risk_findings"] or counts["not_hypertranslated_findings"]) else 1
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
