# WORLD1 — Portable World acceptance

ARCHON portable Worlds are local, offline `.archon-world` files. The file stores
the canonical scientific Rule definition, its stable `WORLD-<SHA-256>` identity,
selected portable Atlas metadata, optional PNG/GIF preview, provenance, and
checksums. It never contains Results trees, caches, executable serialization,
settings, logs, PIDs, or machine-specific paths.

## Identity contract

Identity version 1 hashes deterministic UTF-8 JSON with sorted keys and compact
separators:

```json
{"canonical_rule": {"...": "scientifically complete Rule fields"}, "identity_version": 1}
```

`rule_id`, `parent_a`, and `parent_b` are deliberately excluded, matching the
current canonical `Universe_Search.universe_search_core.rule_signature`
scientific-genome contract. Score, discovery time, previews, observations, and
all installation-local facts are also excluded. Numeric values are finite and
normalized to the current Rule-v1 field types before SHA-256 is computed.

## Headless verification

```text
python Tools/archon_world.py inspect-export 00042
python Tools/archon_world.py export 00042 World-00042.archon-world
python Tools/archon_world.py inspect-import World-00042.archon-world
python Tools/archon_world.py import World-00042.archon-world
python Tools/archon_world.py export-all ARCHON-All-Worlds.archon-worlds
python Tools/archon_world.py inspect-import-all ARCHON-All-Worlds.archon-worlds
python Tools/archon_world.py import-all ARCHON-All-Worlds.archon-worlds
```

Studio **Settings → Import World Collection / Export All Worlds** exposes both
directions of the same collection format. Collection inspection validates every
member without mutation and shows new/duplicate counts plus the prospective or
existing local Rule IDs. Import commits all new Worlds as one Atlas transaction;
if any member or commit step fails, no member is left partially imported.

The collection manifest lists every scientifically distinct World member with
its World UID, original local Rule ID, byte size, and SHA-256. Each member is a
normal `.archon-world` package and can be extracted and imported independently.

Inspection never changes Atlas state. Import validates the ZIP structure,
manifest checksum, preview checksum and independently recomputed World UID before
it acquires the Atlas commit lock.

## Three-installation manual acceptance

1. In installation A, open the World detail and choose **Export World**. Save the
   resulting `.archon-world` file. Record the displayed Rule ID and World UID.
2. Transfer only that file to installation B. Choose **Import World** and select
   it. Before confirming, verify the original ID, source version, World UID,
   preview (when present), and proposed local Rule ID.
3. Confirm import. Open the imported World in Studio and compare its canonical
   Rule definition (or use `Tools/archon_world.py inspect-*`) with A. The World
   UID must be identical. B's Rule ID may differ and must not overwrite an
   occupied ID.
4. Launch the imported local Rule through Studio's normal Observer action (or
   Observer Launcher). It must resolve via `Atlas/Worlds/**/rule.json` and run as
   an ordinary canonical World.
5. Import the same package into B again. Inspection/import must report
   `ALREADY_EXISTS` with the same B-local Rule ID; Atlas and preview counts must
   not change.
6. Import the same package into installation C. Its World UID must equal A and B;
   its collision-free local Rule ID may differ from both.

Do not point development tools at A, B, or C automatically. Each installation's
operator performs these steps locally.

For a complete library transfer, use **Export All Worlds** in A and **Import
World Collection** in B or C. Confirm the inspection counts before import. A
repeated collection import must report every member as already present and make
no canonical changes.
