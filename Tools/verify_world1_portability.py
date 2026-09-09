#!/usr/bin/env python3
"""Fail-closed WORLD1 identity, package, Atlas, Studio and Observer verifier."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import World_Portability.service as portability_module  # noqa: E402
from World_Portability import WorldPortabilityService, compute_world_uid  # noqa: E402
from Tools.archon_studio_snapshot import build_snapshot  # noqa: E402
from Tools.archon_studio_runtime import StudioRequestHandler, StudioRuntimeBridge, StudioRuntimeHTTPServer  # noqa: E402


def rule(rule_id: int, *, seed: int = 123, diffusion: float = 0.25) -> dict:
    return {
        "rule_id": rule_id,
        "parent_a": 12,
        "parent_b": 34,
        "seed": seed,
        "diffusion": diffusion,
        "inertia": 0.3,
        "damping": 0.99,
        "decay": 0.01,
        "noise": 0.001,
        "bias": 0.0,
        "sharpen": -0.05,
        "threshold_push": 0.02,
        "w_avg_r1": 0.1,
        "w_avg_r4": 0.2,
        "w_avg_r12": 0.3,
        "w_var_r1": -0.1,
        "w_var_r4": 0.15,
        "w_lap_r1": -0.2,
        "w_lap_r4": 0.21,
        "terms": [
            {"kind": "sin", "weight": 0.1, "freq": 2.0, "center": 0.5, "width": 0.1, "phase": 0.0},
            {"kind": "gauss", "weight": -0.03, "freq": 4.0, "center": 0.2, "width": 0.04, "phase": 1.2},
        ],
    }


def legacy_key(payload: dict) -> str:
    value = dict(payload)
    for field in ("rule_id", "parent_a", "parent_b"):
        value.pop(field, None)
    return hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]


def add_world(root: Path, payload: dict, *, score: float = 88.5, preview: bool = True) -> Path:
    key = legacy_key(payload)
    relative = Path("Atlas/Worlds/test_world") / f"rule_{payload['rule_id']:05d}_{key}"
    folder = root / relative
    folder.mkdir(parents=True)
    (folder / "rule.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (folder / "metrics.json").write_text(json.dumps({"score": score}), encoding="utf-8")
    preview_path = None
    if preview:
        preview_path = folder / "preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    index_path = root / "Atlas/Worlds/atlas_index.json"
    rows = json.loads(index_path.read_text()) if index_path.exists() else []
    rows.append({
        "key": key, "rule_id": payload["rule_id"], "class": "Test world",
        "generation": 3, "score_mode": "observer_niches", "score": score,
        "source": "test", "folder": relative.as_posix(),
        "preview": relative.joinpath("preview.png").as_posix() if preview_path else None,
        "preview_gif": None, "active": 0.7, "memory": 0.4,
    })
    index_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (root / "Atlas/Worlds/atlas_index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return folder


def package_bytes(service: WorldPortabilityService, rule_id: int) -> bytes:
    output = io.BytesIO()
    service.export_world(rule_id, output)
    return output.getvalue()


def collection_bytes(service: WorldPortabilityService) -> bytes:
    output = io.BytesIO()
    service.export_all_worlds(output)
    return output.getvalue()


def corrupt_collection_member(collection: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(collection), "r") as source:
        members = {name: source.read(name) for name in source.namelist()}
    member = next(name for name in members if name.startswith("worlds/"))
    members[member] += b"tampered"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in members.items():
            target.writestr(name, data)
    return output.getvalue()


def rewrite_manifest(package: bytes, mutator, *, repair_checksum: bool = False) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(package), "r")
    members = {name: source.read(name) for name in source.namelist()}
    source.close()
    manifest = json.loads(members["manifest.json"])
    mutator(manifest)
    if repair_checksum:
        manifest["integrity"]["manifest_sha256"] = ""
        manifest["integrity"]["manifest_sha256"] = hashlib.sha256(portability_module._json_bytes(manifest)).hexdigest()
    members["manifest.json"] = portability_module._json_bytes(manifest) + b"\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in members.items():
            target.writestr(name, data)
    return output.getvalue()


class World1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="archon-world1-")
        self.base = Path(self.temp.name)
        self.a = self.base / "A"
        self.b = self.base / "B"
        self.c = self.base / "C"
        for root in (self.a, self.b, self.c):
            root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_a_b_c_identity_contract(self):
        first = rule(42)
        second = deepcopy(first)
        second.update({"rule_id": 991, "parent_a": -1, "parent_b": -1, "score": 1, "discovered_at": "tomorrow", "preview": "/machine/path"})
        self.assertEqual(compute_world_uid(first), compute_world_uid(second))
        changed = deepcopy(first)
        changed["diffusion"] += 0.0001
        self.assertNotEqual(compute_world_uid(first), compute_world_uid(changed))
        add_world(self.a, first)
        add_world(self.c, second)
        self.assertEqual(
            WorldPortabilityService(self.a).inspect_export(42)["world_uid"],
            WorldPortabilityService(self.c).inspect_export(991)["world_uid"],
        )

    def test_d_e_round_trip_and_local_collision(self):
        original = rule(42)
        add_world(self.a, original)
        add_world(self.b, rule(42, seed=999))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        service_b = WorldPortabilityService(self.b)
        inspected = service_b.inspect_import(package)
        self.assertEqual(inspected["status"], "VALID_NEW")
        self.assertNotEqual(inspected["prospective_local_rule_id"], "00042")
        imported = service_b.import_world(package)
        self.assertEqual(imported["status"], "IMPORTED")
        self.assertNotEqual(imported["local_rule_id"], "00042")
        resolved = service_b.resolve_existing_world(compute_world_uid(original))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["canonical_rule"], portability_module.canonical_scientific_rule(original))

    def test_search_allocator_and_import_share_the_canonical_id_convention(self):
        add_world(self.a, rule(42))
        env = dict(os.environ)
        env["ARCHON_WORLD_ATLAS_DIR"] = str(self.b / "Atlas/Worlds")
        env["ARCHON_KNOWLEDGE_ATLAS_DIR"] = str(self.b / "Atlas/Knowledge")
        script = (
            "from Universe_Search.universe_search_v34_closed_research_cycle import reserve_rule_id_range; "
            "assert reserve_rule_id_range(3) == (0, 2)"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=ROOT, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        imported = WorldPortabilityService(self.b).import_world(package_bytes(WorldPortabilityService(self.a), 42))
        self.assertEqual(imported["local_rule_id"], "00003")

    def test_f_repeated_import_is_idempotent(self):
        add_world(self.a, rule(42))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        service = WorldPortabilityService(self.b)
        first = service.import_world(package)
        before = (service.index_path.read_bytes(), len(list(service.atlas.glob("*/rule_*_*"))))
        second = service.import_world(package)
        after = (service.index_path.read_bytes(), len(list(service.atlas.glob("*/rule_*_*"))))
        self.assertEqual(first["status"], "IMPORTED")
        self.assertEqual(second["status"], "ALREADY_EXISTS")
        self.assertEqual(before, after)

    def test_world1_1_collection_exports_all_distinct_worlds(self):
        add_world(self.a, rule(42))
        add_world(self.a, rule(43, seed=430))
        add_world(self.a, rule(99))  # same scientific World as Rule 00042
        output = io.BytesIO()
        result = WorldPortabilityService(self.a).export_all_worlds(output)
        self.assertEqual(result["status"], "EXPORTED_ALL")
        self.assertEqual(result["world_count"], 2)
        with zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["format"], "ARCHON_WORLD_COLLECTION")
            self.assertEqual(manifest["world_count"], 2)
            check = deepcopy(manifest)
            recorded = check["integrity"]["manifest_sha256"]
            check["integrity"]["manifest_sha256"] = ""
            self.assertEqual(hashlib.sha256(portability_module._json_bytes(check)).hexdigest(), recorded)
            for row in manifest["worlds"]:
                package = archive.read(row["entry"])
                self.assertEqual(hashlib.sha256(package).hexdigest(), row["sha256"])
                self.assertEqual(WorldPortabilityService(self.c).inspect_import(package)["status"], "VALID_NEW")

    def test_world1_1_collection_inspect_mixed_import_and_deduplication(self):
        add_world(self.a, rule(42))
        add_world(self.a, rule(43, seed=430))
        add_world(self.b, rule(73))  # independently discovered duplicate of Rule 00042
        service_b = WorldPortabilityService(self.b)
        collection = collection_bytes(WorldPortabilityService(self.a))
        before = service_b.index_path.read_bytes()
        inspected = service_b.inspect_world_collection(collection)
        self.assertEqual(inspected["status"], "VALID_COLLECTION")
        self.assertEqual((inspected["world_count"], inspected["new_count"], inspected["existing_count"]), (2, 1, 1))
        self.assertEqual(before, service_b.index_path.read_bytes(), "collection inspection mutated the Atlas")
        imported = service_b.import_world_collection(collection)
        self.assertEqual(imported["status"], "IMPORTED_COLLECTION")
        self.assertEqual((imported["imported_count"], imported["existing_count"]), (1, 1))
        self.assertEqual(len(service_b._index()), 2)
        second = service_b.import_world_collection(collection)
        self.assertEqual(second["status"], "ALREADY_EXISTS")
        self.assertEqual((second["imported_count"], second["existing_count"]), (0, 2))
        self.assertEqual(len(service_b._index()), 2)

    def test_world1_1_collection_tamper_rejected_without_partial_state(self):
        add_world(self.a, rule(42))
        add_world(self.a, rule(43, seed=430))
        service_b = WorldPortabilityService(self.b)
        corrupted = corrupt_collection_member(collection_bytes(WorldPortabilityService(self.a)))
        before = list(self.b.rglob("*"))
        self.assertEqual(service_b.inspect_world_collection(corrupted)["status"], "INVALID")
        self.assertEqual(service_b.import_world_collection(corrupted)["status"], "INVALID")
        self.assertEqual(before, list(self.b.rglob("*")))

    def test_world1_1_collection_transaction_rolls_back_every_world(self):
        add_world(self.a, rule(42))
        add_world(self.a, rule(43, seed=430))
        service_b = WorldPortabilityService(self.b)
        real_atomic = portability_module._atomic_bytes
        failed = {"done": False}

        def injected(path, data):
            if Path(path) == service_b.index_jsonl_path and not failed["done"]:
                failed["done"] = True
                raise OSError("injected collection commit failure")
            return real_atomic(path, data)

        portability_module._atomic_bytes = injected
        try:
            with self.assertRaises(OSError):
                service_b.import_world_collection(collection_bytes(WorldPortabilityService(self.a)))
        finally:
            portability_module._atomic_bytes = real_atomic
        self.assertFalse(service_b.index_path.exists())
        self.assertFalse(service_b.index_jsonl_path.exists())
        self.assertFalse(service_b.allocator_path.exists())
        self.assertEqual(list(service_b.atlas.glob("*/rule_*_*")), [])

    def test_g_independent_discovery_deduplication(self):
        add_world(self.a, rule(42))
        add_world(self.b, rule(73))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        inspected = WorldPortabilityService(self.b).inspect_import(package)
        self.assertEqual(inspected["status"], "ALREADY_EXISTS")
        self.assertEqual(inspected["existing_local_rule_id"], "00073")

    def test_h_i_j_tamper_corrupt_and_future_version(self):
        add_world(self.a, rule(42))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        service = WorldPortabilityService(self.b)
        before = list(self.b.rglob("*"))
        tampered = rewrite_manifest(package, lambda manifest: manifest["canonical_rule"].update({"diffusion": 0.9}))
        self.assertEqual(service.inspect_import(tampered)["status"], "INVALID")
        self.assertEqual(service.import_world(tampered)["status"], "INVALID")
        self.assertEqual(service.inspect_import(package[:47])["status"], "INVALID")
        future = rewrite_manifest(package, lambda manifest: manifest.update({"format_version": 999}), repair_checksum=True)
        self.assertEqual(service.inspect_import(future)["status"], "UNSUPPORTED_VERSION")
        self.assertEqual(before, list(self.b.rglob("*")))

    def test_k_l_missing_preview_and_cold_start(self):
        add_world(self.a, rule(42), preview=False)
        service_a = WorldPortabilityService(self.a)
        package = package_bytes(service_a, 42)
        self.assertFalse(service_a.inspect_export(42)["has_preview"])
        before = list(self.b.rglob("*"))
        inspected = WorldPortabilityService(self.b).inspect_import(package)
        self.assertEqual(inspected["status"], "VALID_NEW")
        self.assertEqual(before, list(self.b.rglob("*")), "inspection mutated cold-start state")
        imported = WorldPortabilityService(self.b).import_world(package)
        self.assertEqual(imported["status"], "IMPORTED")
        self.assertTrue((self.b / imported["folder"] / "rule.json").is_file())

    def test_m_n_observer_and_studio_canonical_paths(self):
        add_world(self.a, rule(42))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        imported = WorldPortabilityService(self.b).import_world(package)
        local_id = int(imported["local_rule_id"])
        import Observer.observer_launcher as observer_launcher
        original_atlas = observer_launcher.WORLD_ATLAS_DIR
        try:
            observer_launcher.WORLD_ATLAS_DIR = self.b / "Atlas/Worlds"
            resolved = observer_launcher.find_rule_file(local_id)
        finally:
            observer_launcher.WORLD_ATLAS_DIR = original_atlas
        self.assertIsNotNone(resolved)
        snapshot = build_snapshot(self.b, self.b / "archon-studio/public/studio")
        world = next(item for item in snapshot["worlds"] if item["rule_id"] == imported["local_rule_id"])
        self.assertEqual(world["world_uid"], imported["world_uid"])

    def test_transaction_rolls_back_all_canonical_state(self):
        add_world(self.a, rule(42))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        service = WorldPortabilityService(self.b)
        real_atomic = portability_module._atomic_bytes
        failed = {"done": False}

        def injected(path, data):
            if Path(path) == service.index_jsonl_path and not failed["done"]:
                failed["done"] = True
                raise OSError("injected commit failure")
            return real_atomic(path, data)

        portability_module._atomic_bytes = injected
        try:
            with self.assertRaises(OSError):
                service.import_world(package)
        finally:
            portability_module._atomic_bytes = real_atomic
        self.assertFalse(service.index_path.exists())
        self.assertFalse(service.index_jsonl_path.exists())
        self.assertFalse(service.allocator_path.exists())
        self.assertEqual(list(service.atlas.glob("*/rule_*_*")), [])

    def test_interrupted_process_commit_is_recovered_on_next_service_start(self):
        add_world(self.b, rule(7, seed=700))
        service = WorldPortabilityService(self.b)
        service.knowledge.mkdir(parents=True, exist_ok=True)
        service.allocator_path.write_text(json.dumps({"next_id": 8}), encoding="utf-8")
        originals = {
            "index": service.index_path.read_bytes(),
            "index_jsonl": service.index_jsonl_path.read_bytes(),
            "allocator": service.allocator_path.read_bytes(),
        }
        transaction = service.atlas / ".world-import-crash-fixture"
        backups = transaction / "backups"
        backups.mkdir(parents=True)
        for name, data in originals.items():
            (backups / name).write_bytes(data)
        orphan_relative = Path("Atlas/Worlds/imported_world/rule_00008_deadbeefdead")
        orphan = self.b / orphan_relative
        orphan.mkdir(parents=True)
        (orphan / "rule.json").write_text(json.dumps(rule(8, seed=800)), encoding="utf-8")
        (transaction / "transaction.json").write_text(json.dumps({
            "schema": "archon_world_import_transaction_v1", "phase": "prepared",
            "world_uid": compute_world_uid(rule(8, seed=800)),
            "final_folder": orphan_relative.as_posix(),
            "existed": {"index": True, "index_jsonl": True, "allocator": True},
        }), encoding="utf-8")
        service.index_path.write_text("[]", encoding="utf-8")
        service.index_jsonl_path.write_text("", encoding="utf-8")
        service.allocator_path.write_text(json.dumps({"next_id": 9}), encoding="utf-8")
        WorldPortabilityService(self.b)
        self.assertFalse(orphan.exists())
        self.assertFalse(transaction.exists())
        self.assertEqual(service.index_path.read_bytes(), originals["index"])
        self.assertEqual(service.index_jsonl_path.read_bytes(), originals["index_jsonl"])
        self.assertEqual(service.allocator_path.read_bytes(), originals["allocator"])

    def test_studio_http_import_inspection_commit_and_export(self):
        add_world(self.a, rule(42))
        package = package_bytes(WorldPortabilityService(self.a), 42)
        bridge = StudioRuntimeBridge(self.b)
        try:
            server = StudioRuntimeHTTPServer(("127.0.0.1", 0), StudioRequestHandler, bridge)
        except PermissionError:
            self.skipTest("local loopback sockets are disabled by the test sandbox")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            inspect_request = urllib.request.Request(
                base + "/api/studio/worlds/import/inspect", data=package,
                method="POST", headers={"Content-Type": "application/vnd.archon.world+zip"},
            )
            inspected = json.loads(urllib.request.urlopen(inspect_request, timeout=5).read())
            self.assertEqual(inspected["status"], "VALID_NEW")
            import_request = urllib.request.Request(
                base + "/api/studio/worlds/import", data=package,
                method="POST", headers={"Content-Type": "application/vnd.archon.world+zip"},
            )
            imported = json.loads(urllib.request.urlopen(import_request, timeout=5).read())
            self.assertEqual(imported["status"], "IMPORTED")
            exported = urllib.request.urlopen(
                base + f"/api/studio/worlds/{imported['local_rule_id']}/export", timeout=5,
            )
            self.assertEqual(exported.headers.get_content_type(), "application/vnd.archon.world+zip")
            self.assertEqual(WorldPortabilityService(self.c).inspect_import(exported.read())["status"], "VALID_NEW")
            exported_all = urllib.request.urlopen(base + "/api/studio/worlds/export-all", timeout=5)
            self.assertEqual(exported_all.headers.get_content_type(), "application/vnd.archon.world-collection+zip")
            with zipfile.ZipFile(io.BytesIO(exported_all.read())) as collection:
                self.assertEqual(json.loads(collection.read("manifest.json"))["world_count"], 1)
            add_world(self.a, rule(43, seed=430))
            collection = collection_bytes(WorldPortabilityService(self.a))
            inspect_all_request = urllib.request.Request(
                base + "/api/studio/worlds/import-all/inspect", data=collection,
                method="POST", headers={"Content-Type": "application/vnd.archon.world-collection+zip"},
            )
            inspected_all = json.loads(urllib.request.urlopen(inspect_all_request, timeout=5).read())
            self.assertEqual((inspected_all["new_count"], inspected_all["existing_count"]), (1, 1))
            import_all_request = urllib.request.Request(
                base + "/api/studio/worlds/import-all", data=collection,
                method="POST", headers={"Content-Type": "application/vnd.archon.world-collection+zip"},
            )
            imported_all = json.loads(urllib.request.urlopen(import_all_request, timeout=5).read())
            self.assertEqual(imported_all["status"], "IMPORTED_COLLECTION")
            self.assertEqual((imported_all["imported_count"], imported_all["existing_count"]), (1, 1))
        finally:
            server.shutdown()
            server.server_close()
            bridge.shutdown_event.set()
            thread.join(timeout=3)


def release_contract_checks() -> None:
    core = ROOT / "Universe_Search/universe_search_core.py"
    expected = {
        core: "f2a715465c9506dc63a4317b3de22049f1c55719b2c87a7eacfb16a693ac871b",
    }
    for path, digest in expected.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise AssertionError(f"scientific Search file changed: {path.relative_to(ROOT)}")
    cycle_source = (ROOT / "Universe_Search/universe_search_v34_closed_research_cycle.py").read_text(encoding="utf-8")
    if "POPULATION = base.POPULATION" not in cycle_source or "GENERATIONS = base.GENERATIONS" not in cycle_source:
        raise AssertionError("scientific Search budget contract changed")
    if "def emit_search_runtime_event(" not in cycle_source:
        raise AssertionError("real Search operational telemetry contract missing")
    source = (ROOT / "World_Portability/service.py").read_text(encoding="utf-8")
    for forbidden in ("pickle", "subprocess", "requests", "urllib.request"):
        if forbidden in source:
            raise AssertionError(f"unsafe/offline portability dependency present: {forbidden}")


def main() -> int:
    release_contract_checks()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(World1Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 2
    print("PASS: WORLD1 portable identity, package integrity, transactional Atlas import, Observer resolution and Studio publication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
