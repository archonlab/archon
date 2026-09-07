#!/usr/bin/env python3
"""Canonical, UI-independent ARCHON World portability service.

The service deliberately integrates with the existing ``Atlas/Worlds`` layout.
It never imports scientific runtime modules and accepts only bounded JSON and
PNG/GIF data from a portable package.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
import time
from typing import Any, BinaryIO
import zipfile


FORMAT_ID = "ARCHON_WORLD"
FORMAT_VERSION = 1
IDENTITY_VERSION = 1
WORLD_EXTENSION = ".archon-world"
WORLD_COLLECTION_EXTENSION = ".archon-worlds"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_COLLECTION_BYTES = 4 * 1024 * 1024 * 1024
MAX_PREVIEW_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ZIP_ENTRIES = 2
_UID_RE = re.compile(r"^WORLD-[0-9A-F]{64}$")
_RULE_FIELDS = (
    "seed", "diffusion", "inertia", "damping", "decay", "noise", "bias",
    "sharpen", "threshold_push", "w_avg_r1", "w_avg_r4", "w_avg_r12",
    "w_var_r1", "w_var_r4", "w_lap_r1", "w_lap_r4", "terms",
)
_FLOAT_FIELDS = _RULE_FIELDS[1:-1]
_TERM_FIELDS = ("kind", "weight", "freq", "center", "width", "phase")
_TERM_KINDS = frozenset(("sin", "cos", "tanh", "gauss", "poly", "step", "ring"))
_PORTABLE_ATLAS_FIELDS = (
    "class", "generation", "score_mode", "score", "source", "active", "edge",
    "life", "flow", "rotation", "memory", "recovery", "region", "entities",
    "tracks", "observer_id", "observer_archetype", "observer_note",
    "post_test_truth", "crystal_order", "defect_density", "defect_persistence",
    "defect_motion", "quasi_particle_score", "organism_lifetime",
    "organism_peak_largest", "organism_events", "organism_survived_probe",
    "information_survival", "identity_persistence", "legacy_score",
    "post_collapse_structure", "expansion_front_speed", "collapse_reason_hint",
)
_MIME_BY_SUFFIX = {".png": "image/png", ".gif": "image/gif"}
_process_lock = threading.RLock()


class WorldPortabilityError(RuntimeError):
    """A fail-closed validation or canonical integration error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorldPortabilityError(f"value is not deterministic JSON: {exc}") from exc


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldPortabilityError(f"canonical rule field {field!r} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise WorldPortabilityError(f"canonical rule field {field!r} must be finite")
    return 0.0 if result == 0.0 else result


def canonical_scientific_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Return the explicitly versioned scientific Rule-v1 identity payload.

    Local identity and lineage (``rule_id``, ``parent_a``, ``parent_b``) are
    excluded exactly as in ARCHON's existing ``rule_signature`` contract.
    """
    if not isinstance(rule, dict):
        raise WorldPortabilityError("canonical rule must be a JSON object")
    missing = [field for field in _RULE_FIELDS if field not in rule]
    if missing:
        raise WorldPortabilityError(f"canonical rule is missing fields: {', '.join(missing)}")
    seed = rule["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise WorldPortabilityError("canonical rule field 'seed' must be an integer")
    terms = rule["terms"]
    if not isinstance(terms, list) or not (1 <= len(terms) <= 64):
        raise WorldPortabilityError("canonical rule terms must contain 1..64 entries")
    clean_terms: list[dict[str, Any]] = []
    for index, term in enumerate(terms):
        if not isinstance(term, dict) or any(field not in term for field in _TERM_FIELDS):
            raise WorldPortabilityError(f"canonical rule term {index} is incomplete")
        kind = term["kind"]
        if not isinstance(kind, str) or kind not in _TERM_KINDS:
            raise WorldPortabilityError(f"canonical rule term {index} has invalid kind")
        clean_terms.append({
            "kind": kind,
            **{field: _number(term[field], f"terms[{index}].{field}") for field in _TERM_FIELDS[1:]},
        })
    return {
        "seed": seed,
        **{field: _number(rule[field], field) for field in _FLOAT_FIELDS},
        "terms": clean_terms,
    }


def compute_world_uid(rule: dict[str, Any], identity_version: int = IDENTITY_VERSION) -> str:
    if identity_version != IDENTITY_VERSION:
        raise WorldPortabilityError(f"unsupported identity version: {identity_version}")
    identity = {
        "identity_version": IDENTITY_VERSION,
        "canonical_rule": canonical_scientific_rule(rule),
    }
    return "WORLD-" + hashlib.sha256(_json_bytes(identity)).hexdigest().upper()


def _legacy_genome_hash(rule: dict[str, Any]) -> str:
    payload = dict(rule)
    payload.pop("rule_id", None)
    payload.pop("parent_a", None)
    payload.pop("parent_b", None)
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n")


def _slug(value: Any) -> str:
    text = "".join(char.lower() if char.isalnum() else "_" for char in str(value or ""))
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")[:50] or "imported_world"


def _read_json(path: Path, expected: type, default: Any) -> Any:
    if not path.is_file():
        return deepcopy(default)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorldPortabilityError(f"invalid canonical JSON {path}: {exc}") from exc
    if not isinstance(result, expected):
        raise WorldPortabilityError(f"invalid canonical JSON type in {path}")
    return result


def _safe_preview(name: str, data: bytes) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in _MIME_BY_SUFFIX or len(data) > MAX_PREVIEW_BYTES:
        raise WorldPortabilityError("preview must be a bounded PNG or GIF")
    if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise WorldPortabilityError("preview.png has an invalid signature")
    if suffix == ".gif" and not data.startswith((b"GIF87a", b"GIF89a")):
        raise WorldPortabilityError("preview.gif has an invalid signature")
    return _MIME_BY_SUFFIX[suffix]


def _portable_value(value: Any, *, depth: int = 0) -> Any:
    """Bound JSON metadata and remove installation-specific absolute paths."""
    if depth > 8:
        raise WorldPortabilityError("portable metadata nesting is too deep")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise WorldPortabilityError("portable metadata contains a non-finite number")
        return value
    if isinstance(value, str):
        text = value[:4096]
        if text.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:[\\/]", text):
            return None
        return text
    if isinstance(value, list):
        if len(value) > 1000:
            raise WorldPortabilityError("portable metadata list is too large")
        return [_portable_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 1000:
            raise WorldPortabilityError("portable metadata object is too large")
        return {
            str(key)[:256]: _portable_value(item, depth=depth + 1)
            for key, item in value.items()
            if isinstance(key, (str, int, float, bool))
        }
    raise WorldPortabilityError(f"portable metadata contains unsupported type: {type(value).__name__}")


class WorldPortabilityService:
    """Portable World operations over one existing canonical ARCHON Atlas."""

    def __init__(
        self,
        root: Path | str,
        *,
        world_atlas_dir: Path | str | None = None,
        knowledge_atlas_dir: Path | str | None = None,
    ):
        self.root = Path(root).resolve()
        self.atlas = Path(world_atlas_dir).resolve() if world_atlas_dir is not None else self.root / "Atlas" / "Worlds"
        self.knowledge = Path(knowledge_atlas_dir).resolve() if knowledge_atlas_dir is not None else self.root / "Atlas" / "Knowledge"
        self.index_path = self.atlas / "atlas_index.json"
        self.index_jsonl_path = self.atlas / "atlas_index.jsonl"
        self.allocator_path = self.knowledge / "rule_id_allocator.json"
        self.lock_path = self.atlas / ".world-portability.lock"
        self._recover_interrupted_imports()

    def _recover_interrupted_imports(self) -> None:
        """Roll back a process-interrupted multi-file commit before Atlas use."""
        if not self.atlas.is_dir() or not any(self.atlas.glob(".world-import-*")):
            return
        with self._exclusive_atlas():
            for transaction in sorted(self.atlas.glob(".world-import-*")):
                if not transaction.is_dir():
                    continue
                journal_path = transaction / "transaction.json"
                if not journal_path.is_file():
                    shutil.rmtree(transaction, ignore_errors=True)
                    continue
                journal = _read_json(journal_path, dict, {})
                if journal.get("schema") != "archon_world_import_transaction_v1":
                    raise WorldPortabilityError(f"invalid interrupted import journal: {journal_path}")
                if journal.get("phase") == "committed":
                    shutil.rmtree(transaction, ignore_errors=True)
                    continue
                raw_finals = journal.get("final_folders")
                if not isinstance(raw_finals, list):
                    raw_final = journal.get("final_folder")
                    raw_finals = [raw_final] if isinstance(raw_final, str) else None
                if not raw_finals or not all(isinstance(item, str) for item in raw_finals):
                    raise WorldPortabilityError(f"interrupted import journal has no target: {journal_path}")
                final_folders = []
                for raw_final in raw_finals:
                    final_folder = (self.root / raw_final).resolve()
                    try:
                        final_folder.relative_to(self.atlas.resolve())
                    except ValueError as exc:
                        raise WorldPortabilityError("interrupted import target escapes the World Atlas") from exc
                    final_folders.append(final_folder)
                targets = {
                    "index": self.index_path,
                    "index_jsonl": self.index_jsonl_path,
                    "allocator": self.allocator_path,
                }
                existed = journal.get("existed") if isinstance(journal.get("existed"), dict) else {}
                for name, target in targets.items():
                    backup = transaction / "backups" / name
                    if existed.get(name) is True:
                        if not backup.is_file():
                            raise WorldPortabilityError(f"interrupted import backup is missing: {name}")
                        _atomic_bytes(target, backup.read_bytes())
                    else:
                        try:
                            target.unlink()
                        except FileNotFoundError:
                            pass
                for final_folder in final_folders:
                    shutil.rmtree(final_folder, ignore_errors=True)
                shutil.rmtree(transaction, ignore_errors=True)

    def _source_version(self) -> str | None:
        path = self.root / "Packaging" / "distribution_contract.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return str(payload.get("product_version") or payload.get("studio_version") or "").strip() or None
        except Exception:
            return None

    def _index(self) -> list[dict[str, Any]]:
        rows = _read_json(self.index_path, list, [])
        return [row for row in rows if isinstance(row, dict)]

    def _folder_for(self, entry: dict[str, Any]) -> Path | None:
        raw = entry.get("folder")
        if isinstance(raw, str) and raw.strip():
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = self.root / candidate
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.root)
                if (resolved / "rule.json").is_file():
                    return resolved
            except (OSError, ValueError):
                pass
        try:
            rule_id = int(entry.get("rule_id"))
        except (TypeError, ValueError):
            return None
        key = str(entry.get("key") or "").strip()
        patterns = [f"rule_{rule_id:05d}_{key}"] if key else []
        patterns.append(f"rule_{rule_id:05d}_*")
        for pattern in patterns:
            for candidate in sorted(self.atlas.glob(f"*/{pattern}")):
                if (candidate / "rule.json").is_file():
                    return candidate.resolve()
        return None

    def _world_records(self):
        seen: set[Path] = set()
        for entry in self._index():
            folder = self._folder_for(entry)
            if folder is None:
                continue
            seen.add(folder)
            yield entry, folder, folder / "rule.json"
        if self.atlas.is_dir():
            for rule_path in sorted(self.atlas.glob("*/rule_*_*/rule.json")):
                folder = rule_path.parent.resolve()
                if folder in seen:
                    continue
                try:
                    payload = json.loads(rule_path.read_text(encoding="utf-8"))
                    rule_id = int(payload.get("rule_id"))
                except Exception:
                    continue
                yield {"rule_id": rule_id, "folder": folder.relative_to(self.root).as_posix()}, folder, rule_path

    def resolve_existing_world(self, world_uid: str) -> dict[str, Any] | None:
        if not _UID_RE.fullmatch(str(world_uid or "")):
            return None
        for entry, folder, rule_path in self._world_records():
            try:
                rule = json.loads(rule_path.read_text(encoding="utf-8"))
                derived = compute_world_uid(rule)
            except Exception:
                continue
            if derived == world_uid:
                return {
                    "world_uid": derived,
                    "local_rule_id": f"{int(rule['rule_id']):05d}",
                    "entry": entry,
                    "folder": folder,
                    "rule_path": rule_path,
                    "canonical_rule": canonical_scientific_rule(rule),
                }
        return None

    def _find_local_rule(self, rule_id: int | str) -> dict[str, Any]:
        try:
            wanted = int(rule_id)
        except (TypeError, ValueError) as exc:
            raise WorldPortabilityError(f"invalid local Rule ID: {rule_id!r}") from exc
        matches = []
        for entry, folder, rule_path in self._world_records():
            try:
                rule = json.loads(rule_path.read_text(encoding="utf-8"))
                if int(rule.get("rule_id")) == wanted:
                    matches.append((entry, folder, rule_path, rule))
            except Exception:
                continue
        if not matches:
            raise WorldPortabilityError(f"Rule {wanted:05d} is not present in the canonical World Atlas")
        if len(matches) > 1:
            uids = {compute_world_uid(item[3]) for item in matches}
            if len(uids) > 1:
                raise WorldPortabilityError(f"canonical Atlas contains conflicting Worlds for Rule {wanted:05d}")
        entry, folder, rule_path, rule = matches[0]
        return {"entry": entry, "folder": folder, "rule_path": rule_path, "rule": rule}

    def inspect_export(self, rule_id: int | str) -> dict[str, Any]:
        record = self._find_local_rule(rule_id)
        rule = record["rule"]
        uid = compute_world_uid(rule)
        preview_path = self._preview_path(record["entry"], record["folder"])
        return {
            "status": "VALID",
            "world_uid": uid,
            "local_rule_id": f"{int(rule['rule_id']):05d}",
            "has_preview": preview_path is not None,
            "preview_name": preview_path.name if preview_path else None,
            "source_archon_version": self._source_version(),
        }

    def _preview_path(self, entry: dict[str, Any], folder: Path) -> Path | None:
        candidates: list[Path] = []
        for key in ("preview_gif", "preview"):
            raw = entry.get(key)
            if isinstance(raw, str) and raw:
                path = Path(raw)
                candidates.append(path if path.is_absolute() else self.root / path)
        candidates.extend((folder / "preview.gif", folder / "preview.png"))
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.root)
                if resolved.is_file() and resolved.suffix.lower() in _MIME_BY_SUFFIX:
                    data = resolved.read_bytes()
                    _safe_preview(resolved.name, data)
                    return resolved
            except (OSError, ValueError, WorldPortabilityError):
                continue
        return None

    def export_world(self, rule_id: int | str, destination: Path | str | BinaryIO) -> dict[str, Any]:
        record = self._find_local_rule(rule_id)
        rule = record["rule"]
        canonical = canonical_scientific_rule(rule)
        uid = compute_world_uid(rule)
        entry = record["entry"]
        portable_atlas = {
            key: _portable_value(entry[key]) for key in _PORTABLE_ATLAS_FIELDS
            if key in entry and isinstance(entry[key], (str, int, float, bool, type(None), list, dict))
        }
        preview_path = self._preview_path(entry, record["folder"])
        preview_name = None
        preview_data = None
        preview_mime = None
        if preview_path is not None:
            preview_data = preview_path.read_bytes()
            preview_mime = _safe_preview(preview_path.name, preview_data)
            preview_name = "preview" + preview_path.suffix.lower()
        manifest: dict[str, Any] = {
            "format": FORMAT_ID,
            "format_version": FORMAT_VERSION,
            "world_uid": uid,
            "identity_version": IDENTITY_VERSION,
            "canonical_rule": canonical,
            "source_archon_version": self._source_version(),
            "original_local_rule_id": f"{int(rule['rule_id']):05d}",
            "exported_at": _utc_now(),
            "discovery_provenance": {
                key: deepcopy(entry.get(key)) for key in ("generation", "score_mode", "source")
                if entry.get(key) is not None
            },
            "portable_metadata": {"atlas": portable_atlas},
            "preview": ({"entry": preview_name, "media_type": preview_mime} if preview_name else None),
            "integrity": {
                "algorithm": "SHA-256",
                "files": ({preview_name: hashlib.sha256(preview_data).hexdigest()} if preview_name and preview_data else {}),
                "manifest_sha256": "",
            },
        }
        manifest["integrity"]["manifest_sha256"] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
        members = {"manifest.json": _json_bytes(manifest) + b"\n"}
        if preview_name and preview_data:
            members[preview_name] = preview_data
        output: BinaryIO
        close_output = False
        destination_path: Path | None = None
        if hasattr(destination, "write"):
            output = destination  # type: ignore[assignment]
        else:
            destination_path = Path(destination)
            if destination_path.suffix.lower() != WORLD_EXTENSION:
                destination_path = destination_path.with_suffix(WORLD_EXTENSION)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            output = io.BytesIO()
            close_output = True
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(members):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, members[name], compresslevel=9)
        if close_output:
            assert destination_path is not None and isinstance(output, io.BytesIO)
            _atomic_bytes(destination_path, output.getvalue())
        return {
            "status": "EXPORTED",
            "world_uid": uid,
            "local_rule_id": f"{int(rule['rule_id']):05d}",
            "path": str(destination_path) if destination_path else None,
            "has_preview": preview_name is not None,
        }

    def export_all_worlds(self, destination: Path | str | BinaryIO) -> dict[str, Any]:
        """Export every distinct canonical World as one portable collection.

        The collection is only an envelope: every member remains an ordinary,
        independently inspectable ``.archon-world`` package.
        """
        selected: list[tuple[int, str]] = []
        seen_uids: set[str] = set()
        for _entry, _folder, rule_path in self._world_records():
            try:
                payload = json.loads(rule_path.read_text(encoding="utf-8"))
                local_id = int(payload["rule_id"])
                uid = compute_world_uid(payload)
            except Exception:
                continue
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            selected.append((local_id, uid))
        selected.sort(key=lambda item: (item[0], item[1]))
        if len(selected) > 10000:
            raise WorldPortabilityError("World collection exceeds the 10,000 World safety limit")

        destination_path: Path | None = None
        temporary_path: Path | None = None
        archive_target: BinaryIO | Path
        if hasattr(destination, "write"):
            archive_target = destination  # type: ignore[assignment]
        else:
            destination_path = Path(destination)
            if destination_path.suffix.lower() != WORLD_COLLECTION_EXTENSION:
                destination_path = destination_path.with_suffix(WORLD_COLLECTION_EXTENSION)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            fd, raw_temp = tempfile.mkstemp(
                prefix=f".{destination_path.name}.", suffix=".tmp",
                dir=destination_path.parent,
            )
            os.close(fd)
            temporary_path = Path(raw_temp)
            archive_target = temporary_path

        exported_at = _utc_now()
        rows: list[dict[str, Any]] = []
        try:
            with zipfile.ZipFile(archive_target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for local_id, expected_uid in selected:
                    inner = io.BytesIO()
                    result = self.export_world(local_id, inner)
                    if result["world_uid"] != expected_uid:
                        raise WorldPortabilityError(f"World changed during collection export: Rule {local_id:05d}")
                    data = inner.getvalue()
                    member = f"worlds/Rule-{local_id:05d}-{expected_uid[6:18]}.archon-world"
                    info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data, compresslevel=9)
                    rows.append({
                        "world_uid": expected_uid,
                        "original_local_rule_id": f"{local_id:05d}",
                        "entry": member,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                    })
                manifest: dict[str, Any] = {
                    "format": "ARCHON_WORLD_COLLECTION",
                    "format_version": 1,
                    "world_package_format": FORMAT_ID,
                    "world_package_format_version": FORMAT_VERSION,
                    "identity_version": IDENTITY_VERSION,
                    "source_archon_version": self._source_version(),
                    "exported_at": exported_at,
                    "world_count": len(rows),
                    "worlds": rows,
                    "integrity": {"algorithm": "SHA-256", "manifest_sha256": ""},
                }
                manifest["integrity"]["manifest_sha256"] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
                info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, _json_bytes(manifest) + b"\n", compresslevel=9)
            if destination_path is not None and temporary_path is not None:
                os.replace(temporary_path, destination_path)
                temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
        return {
            "status": "EXPORTED_ALL",
            "world_count": len(rows),
            "path": str(destination_path) if destination_path else None,
            "exported_at": exported_at,
        }

    def _read_collection(self, source: Path | str | bytes | bytearray | BinaryIO) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
            if len(raw) > MAX_COLLECTION_BYTES:
                raise WorldPortabilityError("World collection exceeds the 4 GiB safety limit")
            archive_source: Any = io.BytesIO(raw)
        elif hasattr(source, "read"):
            archive_source = source
        else:
            path = Path(source)
            if path.stat().st_size > MAX_COLLECTION_BYTES:
                raise WorldPortabilityError("World collection exceeds the 4 GiB safety limit")
            archive_source = path
        try:
            with zipfile.ZipFile(archive_source, "r") as archive:
                infos = archive.infolist()
                if not infos or len(infos) > 10001:
                    raise WorldPortabilityError("World collection has an invalid entry count")
                names = [item.filename for item in infos]
                if len(names) != len(set(names)) or "manifest.json" not in names:
                    raise WorldPortabilityError("World collection requires exactly one manifest.json")
                if sum(item.file_size for item in infos) > MAX_COLLECTION_BYTES:
                    raise WorldPortabilityError("World collection expands beyond the 4 GiB safety limit")
                for item in infos:
                    path = PurePosixPath(item.filename)
                    allowed_shape = item.filename == "manifest.json" or (
                        len(path.parts) == 2 and path.parts[0] == "worlds" and path.suffix == WORLD_EXTENSION
                    )
                    if not allowed_shape or path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                        raise WorldPortabilityError("World collection contains an unsafe entry path")
                    if item.flag_bits & 1:
                        raise WorldPortabilityError("encrypted World collection entries are unsupported")
                    mode = item.external_attr >> 16
                    if mode and (mode & 0o170000) not in (0, 0o100000):
                        raise WorldPortabilityError("World collection contains a non-regular entry")
                    limit = 16 * 1024 * 1024 if item.filename == "manifest.json" else MAX_PACKAGE_BYTES
                    if item.file_size > limit:
                        raise WorldPortabilityError("World collection entry exceeds its safety limit")
                    if item.file_size > 1024 * 1024 and item.compress_size and item.file_size / item.compress_size > 200:
                        raise WorldPortabilityError("World collection compression ratio is unsafe")
                try:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise WorldPortabilityError(f"invalid World collection manifest: {exc}") from exc
                if not isinstance(manifest, dict) or manifest.get("format") != "ARCHON_WORLD_COLLECTION":
                    raise WorldPortabilityError("unrecognized World collection format")
                version = manifest.get("format_version")
                if isinstance(version, bool) or version != 1:
                    if isinstance(version, int) and version > 1:
                        raise ValueError(f"unsupported future World collection version: {version}")
                    raise WorldPortabilityError(f"unsupported World collection version: {version!r}")
                if manifest.get("world_package_format") != FORMAT_ID or manifest.get("world_package_format_version") != FORMAT_VERSION:
                    raise ValueError("unsupported embedded World package format")
                if manifest.get("identity_version") != IDENTITY_VERSION:
                    raise ValueError("unsupported World collection identity version")
                integrity = manifest.get("integrity")
                if not isinstance(integrity, dict) or integrity.get("algorithm") != "SHA-256":
                    raise WorldPortabilityError("World collection integrity contract is missing")
                recorded_manifest_hash = integrity.get("manifest_sha256")
                check = deepcopy(manifest)
                check["integrity"]["manifest_sha256"] = ""
                if not isinstance(recorded_manifest_hash, str) or hashlib.sha256(_json_bytes(check)).hexdigest() != recorded_manifest_hash:
                    raise WorldPortabilityError("World collection manifest checksum mismatch")
                rows = manifest.get("worlds")
                if not isinstance(rows, list) or manifest.get("world_count") != len(rows) or len(rows) > 10000:
                    raise WorldPortabilityError("World collection count does not match its manifest")
                declared_entries: set[str] = set()
                declared_uids: set[str] = set()
                validated_items: list[dict[str, Any]] = []
                for index, row in enumerate(rows):
                    if not isinstance(row, dict):
                        raise WorldPortabilityError(f"World collection row {index} is invalid")
                    entry = row.get("entry")
                    uid = row.get("world_uid")
                    if not isinstance(entry, str) or entry in declared_entries or entry not in names:
                        raise WorldPortabilityError(f"World collection row {index} has an invalid entry")
                    if not isinstance(uid, str) or uid in declared_uids or not _UID_RE.fullmatch(uid):
                        raise WorldPortabilityError(f"World collection row {index} has an invalid World UID")
                    data = archive.read(entry)
                    if row.get("bytes") != len(data) or row.get("sha256") != hashlib.sha256(data).hexdigest():
                        raise WorldPortabilityError(f"World collection member checksum mismatch: {entry}")
                    inner_manifest, preview_data, preview_name = self._read_package(data)
                    validated = self._validate_manifest(inner_manifest, preview_data, preview_name)
                    if validated["world_uid"] != uid or validated["original_rule_id"] != row.get("original_local_rule_id"):
                        raise WorldPortabilityError(f"World collection member identity mismatch: {entry}")
                    declared_entries.add(entry)
                    declared_uids.add(uid)
                    validated_items.append({
                        "manifest": inner_manifest,
                        "preview_data": preview_data,
                        "preview_name": preview_name,
                        "validated": validated,
                    })
                if set(names) != {"manifest.json", *declared_entries}:
                    raise WorldPortabilityError("World collection contains undeclared entries")
        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            raise WorldPortabilityError(f"corrupt ARCHON World collection: {exc}") from exc
        return manifest, validated_items

    def _collection_plan(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        used = self._used_rule_ids()
        next_id = self.allocate_local_rule_id()
        rows = []
        for item in items:
            validated = item["validated"]
            existing = self.resolve_existing_world(validated["world_uid"])
            if existing:
                rows.append({
                    "status": "ALREADY_EXISTS",
                    "world_uid": validated["world_uid"],
                    "original_rule_id": validated["original_rule_id"],
                    "existing_local_rule_id": existing["local_rule_id"],
                    "prospective_local_rule_id": None,
                })
                continue
            while next_id in used:
                next_id += 1
            rows.append({
                "status": "VALID_NEW",
                "world_uid": validated["world_uid"],
                "original_rule_id": validated["original_rule_id"],
                "existing_local_rule_id": None,
                "prospective_local_rule_id": f"{next_id:05d}",
            })
            used.add(next_id)
            next_id += 1
        return rows

    def inspect_world_collection(self, source: Path | str | bytes | bytearray | BinaryIO) -> dict[str, Any]:
        try:
            manifest, items = self._read_collection(source)
        except ValueError as exc:
            return {"status": "UNSUPPORTED_VERSION", "error": str(exc)}
        except (WorldPortabilityError, OSError) as exc:
            return {"status": "INVALID", "error": str(exc)}
        worlds = self._collection_plan(items)
        new_count = sum(row["status"] == "VALID_NEW" for row in worlds)
        existing_count = len(worlds) - new_count
        return {
            "status": "VALID_COLLECTION" if new_count else "ALREADY_EXISTS",
            "source_archon_version": manifest.get("source_archon_version"),
            "exported_at": manifest.get("exported_at"),
            "world_count": len(worlds),
            "new_count": new_count,
            "existing_count": existing_count,
            "worlds": worlds,
        }

    def import_world_collection(self, source: Path | str | bytes | bytearray | BinaryIO) -> dict[str, Any]:
        try:
            manifest, items = self._read_collection(source)
        except ValueError as exc:
            return {"status": "UNSUPPORTED_VERSION", "error": str(exc)}
        except (WorldPortabilityError, OSError) as exc:
            return {"status": "INVALID", "error": str(exc)}
        with self._exclusive_atlas():
            plan = self._collection_plan(items)
            new_pairs = [(item, row) for item, row in zip(items, plan) if row["status"] == "VALID_NEW"]
            if not new_pairs:
                return {
                    "status": "ALREADY_EXISTS", "world_count": len(plan),
                    "imported_count": 0, "existing_count": len(plan), "worlds": plan,
                }
            transaction_root = Path(tempfile.mkdtemp(prefix=".world-import-", dir=self.atlas))
            prepared: list[dict[str, Any]] = []
            index = self._index()
            imported_at = _utc_now()
            try:
                for position, (item, row) in enumerate(new_pairs):
                    local_id = int(row["prospective_local_rule_id"])
                    validated = item["validated"]
                    local_rule = {"rule_id": local_id, "parent_a": -1, "parent_b": -1, **validated["canonical_rule"]}
                    legacy_key = _legacy_genome_hash(local_rule)
                    clean_metadata = validated["portable_atlas"]
                    class_name = _slug(clean_metadata.get("class") or "imported_world")
                    relative_folder = Path("Atlas") / "Worlds" / class_name / f"rule_{local_id:05d}_{legacy_key}"
                    final_folder = self.root / relative_folder
                    if final_folder.exists():
                        raise WorldPortabilityError(f"target World folder already exists: {relative_folder.as_posix()}")
                    staged_folder = transaction_root / f"world-{position:05d}"
                    staged_folder.mkdir()
                    entry = {
                        **clean_metadata, "key": legacy_key, "world_uid": validated["world_uid"],
                        "rule_id": local_id, "folder": relative_folder.as_posix(),
                        "preview": None, "preview_gif": None,
                        "imported_from_world_uid": validated["world_uid"],
                        "original_rule_id": validated["original_rule_id"],
                        "source_archon_version": item["manifest"].get("source_archon_version"),
                        "imported_at": imported_at,
                    }
                    entry.setdefault("score", 0.0)
                    _atomic_json(staged_folder / "rule.json", local_rule)
                    _atomic_json(staged_folder / "metrics.json", clean_metadata)
                    _atomic_json(staged_folder / "portability.json", {
                        "schema": "archon_world_import_provenance_v1", "world_uid": validated["world_uid"],
                        "identity_version": IDENTITY_VERSION, "imported_from_world_uid": validated["world_uid"],
                        "original_rule_id": validated["original_rule_id"],
                        "source_archon_version": item["manifest"].get("source_archon_version"),
                        "exported_at": item["manifest"].get("exported_at"), "imported_at": imported_at,
                        "collection_exported_at": manifest.get("exported_at"),
                    })
                    _atomic_bytes(staged_folder / "report.txt", (
                        f"ARCHON portable World collection import\nWorld UID: {validated['world_uid']}\n"
                        f"Original Rule: {validated['original_rule_id']}\nLocal Rule: {local_id:05d}\n"
                    ).encode("utf-8"))
                    if item["preview_name"] and item["preview_data"] is not None:
                        preview_target = staged_folder / item["preview_name"]
                        _atomic_bytes(preview_target, item["preview_data"])
                        key = "preview_gif" if preview_target.suffix == ".gif" else "preview"
                        entry[key] = (relative_folder / item["preview_name"]).as_posix()
                    index.append(entry)
                    prepared.append({
                        "staged": staged_folder, "final": final_folder,
                        "relative": relative_folder, "entry": entry,
                        "local_id": local_id, "uid": validated["world_uid"], "row": row,
                    })
                index.sort(key=lambda record: float(record.get("score", 0.0) or 0.0), reverse=True)
                index_bytes = json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
                jsonl_bytes = b"".join(_json_bytes(record) + b"\n" for record in index)
                assignments = [(record["local_id"], record["uid"]) for record in prepared]
                allocator_bytes = json.dumps(self._allocator_after_imports(assignments), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
                backups = {
                    self.index_path: self.index_path.read_bytes() if self.index_path.exists() else None,
                    self.index_jsonl_path: self.index_jsonl_path.read_bytes() if self.index_jsonl_path.exists() else None,
                    self.allocator_path: self.allocator_path.read_bytes() if self.allocator_path.exists() else None,
                }
                backup_names = {self.index_path: "index", self.index_jsonl_path: "index_jsonl", self.allocator_path: "allocator"}
                backup_dir = transaction_root / "backups"
                backup_dir.mkdir()
                for path, previous in backups.items():
                    if previous is not None:
                        _atomic_bytes(backup_dir / backup_names[path], previous)
                journal = {
                    "schema": "archon_world_import_transaction_v1", "phase": "prepared",
                    "world_uids": [record["uid"] for record in prepared],
                    "final_folders": [record["relative"].as_posix() for record in prepared],
                    "existed": {backup_names[path]: previous is not None for path, previous in backups.items()},
                }
                _atomic_json(transaction_root / "transaction.json", journal)
                committed: list[Path] = []
                try:
                    for record in prepared:
                        record["final"].parent.mkdir(parents=True, exist_ok=True)
                        os.replace(record["staged"], record["final"])
                        committed.append(record["final"])
                    _atomic_bytes(self.index_path, index_bytes)
                    _atomic_bytes(self.index_jsonl_path, jsonl_bytes)
                    _atomic_bytes(self.allocator_path, allocator_bytes)
                    for record in prepared:
                        resolved = self.resolve_existing_world(record["uid"])
                        if not resolved or resolved["local_rule_id"] != f"{record['local_id']:05d}":
                            raise WorldPortabilityError("post-commit collection World resolution failed")
                    journal["phase"] = "committed"
                    _atomic_json(transaction_root / "transaction.json", journal)
                except Exception:
                    for path, previous in backups.items():
                        if previous is None:
                            try:
                                path.unlink()
                            except FileNotFoundError:
                                pass
                        else:
                            _atomic_bytes(path, previous)
                    for folder in committed:
                        shutil.rmtree(folder, ignore_errors=True)
                    raise
            finally:
                shutil.rmtree(transaction_root, ignore_errors=True)
            imported_by_uid = {record["uid"]: record for record in prepared}
            result_rows = []
            for row in plan:
                record = imported_by_uid.get(row["world_uid"])
                if record:
                    result_rows.append({
                        **row, "status": "IMPORTED",
                        "local_rule_id": f"{record['local_id']:05d}",
                        "prospective_local_rule_id": None,
                    })
                else:
                    result_rows.append(row)
            return {
                "status": "IMPORTED_COLLECTION", "world_count": len(plan),
                "imported_count": len(prepared), "existing_count": len(plan) - len(prepared),
                "worlds": result_rows,
            }

    def _read_package(self, source: Path | str | bytes | bytearray | BinaryIO) -> tuple[dict[str, Any], bytes | None, str | None]:
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
        elif hasattr(source, "read"):
            raw = source.read(MAX_PACKAGE_BYTES + 1)  # type: ignore[union-attr]
        else:
            path = Path(source)
            if path.stat().st_size > MAX_PACKAGE_BYTES:
                raise WorldPortabilityError("package exceeds the 32 MiB limit")
            raw = path.read_bytes()
        if len(raw) > MAX_PACKAGE_BYTES:
            raise WorldPortabilityError("package exceeds the 32 MiB limit")
        try:
            with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
                infos = archive.infolist()
                if not infos or len(infos) > MAX_ZIP_ENTRIES:
                    raise WorldPortabilityError("package has an invalid entry count")
                names = [item.filename for item in infos]
                if len(names) != len(set(names)) or "manifest.json" not in names:
                    raise WorldPortabilityError("package requires exactly one manifest.json")
                for item in infos:
                    path = PurePosixPath(item.filename)
                    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1 or "\\" in item.filename:
                        raise WorldPortabilityError("package contains an unsafe path")
                    if item.flag_bits & 1:
                        raise WorldPortabilityError("encrypted package entries are unsupported")
                    mode = item.external_attr >> 16
                    if mode and (mode & 0o170000) not in (0, 0o100000):
                        raise WorldPortabilityError("package contains a non-regular entry")
                    limit = MAX_MANIFEST_BYTES if item.filename == "manifest.json" else MAX_PREVIEW_BYTES
                    if item.file_size > limit or item.compress_size > MAX_PACKAGE_BYTES:
                        raise WorldPortabilityError("package entry exceeds its safety limit")
                    if item.file_size > 1024 * 1024 and item.compress_size and item.file_size / item.compress_size > 200:
                        raise WorldPortabilityError("package compression ratio is unsafe")
                manifest_raw = archive.read("manifest.json")
                try:
                    manifest = json.loads(manifest_raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise WorldPortabilityError(f"invalid manifest JSON: {exc}") from exc
                if not isinstance(manifest, dict):
                    raise WorldPortabilityError("manifest must be an object")
                preview = manifest.get("preview")
                preview_name = preview.get("entry") if isinstance(preview, dict) else None
                allowed = {"manifest.json"}
                preview_data = None
                if preview_name is not None:
                    if not isinstance(preview_name, str) or preview_name not in names:
                        raise WorldPortabilityError("declared preview is missing")
                    allowed.add(preview_name)
                    preview_data = archive.read(preview_name)
                    mime = _safe_preview(preview_name, preview_data)
                    if preview.get("media_type") != mime:
                        raise WorldPortabilityError("preview media type mismatch")
                if set(names) != allowed:
                    raise WorldPortabilityError("package contains undeclared entries")
        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            raise WorldPortabilityError(f"corrupt ARCHON World package: {exc}") from exc
        return manifest, preview_data, preview_name

    def _validate_manifest(self, manifest: dict[str, Any], preview_data: bytes | None, preview_name: str | None) -> dict[str, Any]:
        if manifest.get("format") != FORMAT_ID:
            raise WorldPortabilityError("unrecognized portable World format")
        version = manifest.get("format_version")
        if isinstance(version, bool) or version != FORMAT_VERSION:
            if isinstance(version, int) and version > FORMAT_VERSION:
                raise ValueError(f"unsupported future format version: {version}")
            raise WorldPortabilityError(f"unsupported format version: {version!r}")
        if isinstance(manifest.get("identity_version"), bool) or manifest.get("identity_version") != IDENTITY_VERSION:
            raise ValueError(f"unsupported identity version: {manifest.get('identity_version')!r}")
        integrity = manifest.get("integrity")
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "SHA-256":
            raise WorldPortabilityError("missing SHA-256 integrity contract")
        recorded_manifest_hash = integrity.get("manifest_sha256")
        if not isinstance(recorded_manifest_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded_manifest_hash):
            raise WorldPortabilityError("invalid manifest checksum")
        check_manifest = deepcopy(manifest)
        check_manifest["integrity"]["manifest_sha256"] = ""
        if hashlib.sha256(_json_bytes(check_manifest)).hexdigest() != recorded_manifest_hash:
            raise WorldPortabilityError("manifest checksum mismatch")
        files = integrity.get("files")
        if not isinstance(files, dict) or set(files) != ({preview_name} if preview_name else set()):
            raise WorldPortabilityError("integrity file inventory mismatch")
        if preview_name and preview_data is not None:
            digest = files.get(preview_name)
            if not isinstance(digest, str) or hashlib.sha256(preview_data).hexdigest() != digest:
                raise WorldPortabilityError("preview checksum mismatch")
        canonical = canonical_scientific_rule(manifest.get("canonical_rule"))
        uid = compute_world_uid(canonical, int(manifest["identity_version"]))
        if manifest.get("world_uid") != uid or not _UID_RE.fullmatch(uid):
            raise WorldPortabilityError("World UID does not match the canonical scientific rule")
        original = manifest.get("original_local_rule_id")
        try:
            numeric_original = int(original)
            if numeric_original < 0:
                raise ValueError
            original_id = f"{numeric_original:05d}"
        except (TypeError, ValueError) as exc:
            raise WorldPortabilityError("invalid original local Rule ID") from exc
        source_version = manifest.get("source_archon_version")
        if source_version is not None and (not isinstance(source_version, str) or len(source_version) > 100):
            raise WorldPortabilityError("invalid source ARCHON version")
        metadata = manifest.get("portable_metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("atlas", {}), dict):
            raise WorldPortabilityError("portable metadata must be an object")
        clean_atlas = {
            key: _portable_value(metadata.get("atlas", {}).get(key))
            for key in _PORTABLE_ATLAS_FIELDS if key in metadata.get("atlas", {})
        }
        return {
            "world_uid": uid, "canonical_rule": canonical,
            "original_rule_id": original_id, "portable_atlas": clean_atlas,
        }

    def inspect_import(self, source: Path | str | bytes | bytearray | BinaryIO, *, include_preview_data: bool = False) -> dict[str, Any]:
        try:
            manifest, preview_data, preview_name = self._read_package(source)
            validated = self._validate_manifest(manifest, preview_data, preview_name)
        except ValueError as exc:
            return {"status": "UNSUPPORTED_VERSION", "error": str(exc)}
        except (WorldPortabilityError, OSError) as exc:
            return {"status": "INVALID", "error": str(exc)}
        existing = self.resolve_existing_world(validated["world_uid"])
        result = {
            "status": "ALREADY_EXISTS" if existing else "VALID_NEW",
            "world_uid": validated["world_uid"],
            "original_rule_id": validated["original_rule_id"],
            "source_archon_version": manifest.get("source_archon_version"),
            "exported_at": manifest.get("exported_at"),
            "metadata": {"atlas": validated["portable_atlas"]},
            "has_preview": preview_data is not None,
            "preview_media_type": (manifest.get("preview") or {}).get("media_type") if isinstance(manifest.get("preview"), dict) else None,
            "prospective_local_rule_id": None if existing else f"{self.allocate_local_rule_id():05d}",
            "existing_local_rule_id": existing["local_rule_id"] if existing else None,
        }
        if include_preview_data and preview_data is not None:
            import base64
            result["preview_base64"] = base64.b64encode(preview_data).decode("ascii")
        return result

    def _used_rule_ids(self) -> set[int]:
        result: set[int] = set()
        for entry, _folder, rule_path in self._world_records():
            for value in (entry.get("rule_id"),):
                try:
                    result.add(int(value))
                except (TypeError, ValueError):
                    pass
            try:
                result.add(int(json.loads(rule_path.read_text(encoding="utf-8"))["rule_id"]))
            except Exception:
                pass
        return result

    def allocate_local_rule_id(self) -> int:
        used = self._used_rule_ids()
        state = _read_json(self.allocator_path, dict, {})
        try:
            next_id = max(0, int(state.get("next_id", 0) or 0))
        except (TypeError, ValueError):
            next_id = 0
        if used:
            next_id = max(next_id, max(used) + 1)
        while next_id in used:
            next_id += 1
        return next_id

    @contextmanager
    def _exclusive_atlas(self):
        self.atlas.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 15.0
        token = _json_bytes({"pid": os.getpid(), "created_at": _utc_now()})
        with _process_lock:
            while True:
                try:
                    fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(token)
                    break
                except FileExistsError:
                    try:
                        stale = time.time() - self.lock_path.stat().st_mtime > 300
                        if not stale:
                            try:
                                lock_payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
                                pid = int(lock_payload.get("pid"))
                                os.kill(pid, 0)
                            except ProcessLookupError:
                                stale = True
                            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                                pass
                        if stale:
                            self.lock_path.unlink()
                            continue
                    except FileNotFoundError:
                        continue
                    if time.monotonic() >= deadline:
                        raise WorldPortabilityError("canonical World Atlas is busy")
                    time.sleep(0.05)
            try:
                yield
            finally:
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass

    def atlas_write_lock(self):
        """Public shared lock for canonical Atlas/allocator writers."""
        return self._exclusive_atlas()

    def _allocator_after_import(self, local_id: int, uid: str) -> dict[str, Any]:
        return self._allocator_after_imports([(local_id, uid)])

    def _allocator_after_imports(self, assignments: list[tuple[int, str]]) -> dict[str, Any]:
        state = _read_json(self.allocator_path, dict, {})
        history = state.get("reservations") if isinstance(state.get("reservations"), list) else []
        history = list(history)
        for local_id, uid in assignments:
            history.append({
                "search_run_id": f"WORLD1-import-{uid[6:18]}",
                "reserved_start": local_id,
                "reserved_end": local_id,
                "reserved_count": 1,
                "created_at": _utc_now(),
                "purpose": "world_import",
                "world_uid": uid,
            })
        highest_next = max((local_id + 1 for local_id, _uid in assignments), default=0)
        return {
            **state,
            "version": state.get("version") or "v1.0 persistent rule ID allocator",
            "next_id": max(highest_next, int(state.get("next_id", 0) or 0)),
            "last_search_run_id": state.get("last_search_run_id"),
            "reservations": history[-1000:],
        }

    def import_world(self, source: Path | str | bytes | bytearray | BinaryIO) -> dict[str, Any]:
        try:
            manifest, preview_data, preview_name = self._read_package(source)
            validated = self._validate_manifest(manifest, preview_data, preview_name)
        except ValueError as exc:
            return {"status": "UNSUPPORTED_VERSION", "error": str(exc)}
        except (WorldPortabilityError, OSError) as exc:
            return {"status": "INVALID", "error": str(exc)}
        with self._exclusive_atlas():
            existing = self.resolve_existing_world(validated["world_uid"])
            if existing:
                return {
                    "status": "ALREADY_EXISTS", "world_uid": validated["world_uid"],
                    "existing_local_rule_id": existing["local_rule_id"],
                }
            local_id = self.allocate_local_rule_id()
            canonical = validated["canonical_rule"]
            local_rule = {"rule_id": local_id, "parent_a": -1, "parent_b": -1, **canonical}
            legacy_key = _legacy_genome_hash(local_rule)
            clean_metadata = validated["portable_atlas"]
            class_name = _slug(clean_metadata.get("class") or "imported_world")
            relative_folder = Path("Atlas") / "Worlds" / class_name / f"rule_{local_id:05d}_{legacy_key}"
            final_folder = self.root / relative_folder
            if final_folder.exists():
                raise WorldPortabilityError(f"target World folder already exists: {relative_folder.as_posix()}")
            imported_at = _utc_now()
            entry = {
                **clean_metadata,
                "key": legacy_key,
                "world_uid": validated["world_uid"],
                "rule_id": local_id,
                "folder": relative_folder.as_posix(),
                "preview": None,
                "preview_gif": None,
                "imported_from_world_uid": validated["world_uid"],
                "original_rule_id": validated["original_rule_id"],
                "source_archon_version": manifest.get("source_archon_version"),
                "imported_at": imported_at,
            }
            if "score" not in entry:
                entry["score"] = 0.0
            transaction_root = Path(tempfile.mkdtemp(prefix=".world-import-", dir=self.atlas))
            staged_folder = transaction_root / "world"
            staged_folder.mkdir()
            try:
                _atomic_json(staged_folder / "rule.json", local_rule)
                _atomic_json(staged_folder / "metrics.json", clean_metadata)
                _atomic_json(staged_folder / "portability.json", {
                    "schema": "archon_world_import_provenance_v1",
                    "world_uid": validated["world_uid"],
                    "identity_version": IDENTITY_VERSION,
                    "imported_from_world_uid": validated["world_uid"],
                    "original_rule_id": validated["original_rule_id"],
                    "source_archon_version": manifest.get("source_archon_version"),
                    "exported_at": manifest.get("exported_at"),
                    "imported_at": imported_at,
                })
                _atomic_bytes(staged_folder / "report.txt", (
                    f"ARCHON portable World import\nWorld UID: {validated['world_uid']}\n"
                    f"Original Rule: {validated['original_rule_id']}\nLocal Rule: {local_id:05d}\n"
                ).encode("utf-8"))
                if preview_name and preview_data is not None:
                    preview_target = staged_folder / preview_name
                    _atomic_bytes(preview_target, preview_data)
                    key = "preview_gif" if preview_target.suffix == ".gif" else "preview"
                    entry[key] = (relative_folder / preview_name).as_posix()
                index = self._index()
                index.append(entry)
                index.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
                index_bytes = json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
                jsonl_bytes = b"".join(_json_bytes(row) + b"\n" for row in index)
                allocator_bytes = json.dumps(self._allocator_after_import(local_id, validated["world_uid"]), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
                backups = {
                    self.index_path: self.index_path.read_bytes() if self.index_path.exists() else None,
                    self.index_jsonl_path: self.index_jsonl_path.read_bytes() if self.index_jsonl_path.exists() else None,
                    self.allocator_path: self.allocator_path.read_bytes() if self.allocator_path.exists() else None,
                }
                backup_names = {
                    self.index_path: "index",
                    self.index_jsonl_path: "index_jsonl",
                    self.allocator_path: "allocator",
                }
                backup_dir = transaction_root / "backups"
                backup_dir.mkdir()
                for path, previous in backups.items():
                    if previous is not None:
                        _atomic_bytes(backup_dir / backup_names[path], previous)
                journal = {
                    "schema": "archon_world_import_transaction_v1",
                    "phase": "prepared",
                    "world_uid": validated["world_uid"],
                    "final_folder": relative_folder.as_posix(),
                    "existed": {backup_names[path]: previous is not None for path, previous in backups.items()},
                }
                _atomic_json(transaction_root / "transaction.json", journal)
                committed_folder = False
                try:
                    final_folder.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged_folder, final_folder)
                    committed_folder = True
                    _atomic_bytes(self.index_path, index_bytes)
                    _atomic_bytes(self.index_jsonl_path, jsonl_bytes)
                    _atomic_bytes(self.allocator_path, allocator_bytes)
                    resolved = self.resolve_existing_world(validated["world_uid"])
                    if not resolved or resolved["local_rule_id"] != f"{local_id:05d}" or not resolved["rule_path"].is_file():
                        raise WorldPortabilityError("post-commit canonical World resolution failed")
                    journal["phase"] = "committed"
                    _atomic_json(transaction_root / "transaction.json", journal)
                except Exception:
                    for path, previous in backups.items():
                        if previous is None:
                            try:
                                path.unlink()
                            except FileNotFoundError:
                                pass
                        else:
                            _atomic_bytes(path, previous)
                    if committed_folder:
                        shutil.rmtree(final_folder, ignore_errors=True)
                    raise
            finally:
                shutil.rmtree(transaction_root, ignore_errors=True)
            return {
                "status": "IMPORTED",
                "world_uid": validated["world_uid"],
                "local_rule_id": f"{local_id:05d}",
                "original_rule_id": validated["original_rule_id"],
                "folder": relative_folder.as_posix(),
            }
