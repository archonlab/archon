# ARCHON Studio Operator Guide — STUDIO20.5

ARCHON Studio is a local presentation, control and reporting layer downstream of Project ARCHON canonical scientific data. It does not replace Universe Search, Observer, Analyzer, the Atlas, or their evidence contracts.

## Quick start

1. From the ARCHON root run `./ARCHON_STUDIO.sh` for desktop mode. Use `./STUDIO.sh` only when you explicitly want the browser/web launcher.
2. If the frontend dependencies are not installed yet, run `cd archon-studio && npm ci` once, then launch Studio again.
3. A fresh release with no `Atlas/Worlds/atlas_index.json` is valid. Studio should show **No research yet** rather than fail.
4. Open **Search** and run Universe Search to retain the first worlds.
5. Use **Observer** inside Studio as a Rule preview. Preview artifacts are isolated from canonical Evidence unless the Rule is handed to Observer Launcher for reviewed observation.
6. Run **Analyzer** after observations or experiments. Feed, Evidence, Mechanisms, Predictions and Research Writer then expose the downstream state.

## Portable Worlds (WORLD1)

Open a retained World in **Worlds** and choose **Export World** to download a
local `.archon-world` package. Use the persistent **Import World** action to
inspect a package before any state changes, review its stable World UID and
prospective local Rule ID, then confirm the import. A duplicate opens the
already-existing local World instead of creating another copy. Packages are
offline files and never include arbitrary Results trees. See
`Docs/WORLD1_PORTABLE_WORLDS.md` for the headless interface and the
three-installation acceptance procedure.

To archive or transfer the complete World library, open **Settings** and choose
**Export All Worlds**. Studio downloads one `.archon-worlds` collection whose
members are ordinary, independently verifiable `.archon-world` packages. The
collection does not contain Results, observations, caches, or Studio settings.

## Canonical research chain

Studio presents the chain:

`World → Rule → Experiment → Evidence → Mechanism → Prediction`

Every human-readable view should preserve links or provenance back to canonical objects. Normalized Studio JSON is a UI contract, not a replacement for the source files.

## Global Search

Press `Ctrl+K` on Linux/Windows or `Cmd+K` on macOS. Exact Rule IDs, experiment IDs and GP prediction IDs are especially effective.

## Observer Preview

The Studio Observer page is intentionally a preview surface for retained Rules. Stopping an embedded preview offers:

- **Save and stop** — keep preview artifacts under `Results/Studio/saved_previews`.
- **Stop without saving** — discard preview artifacts.
- **Cancel** — continue the preview.

Saved previews do not become canonical Evidence automatically.

**Open this Rule in Observer Launcher** transfers the Rule and launch settings into the active Observer Launcher profile. It is a context handoff, not a live checkpoint: tick, RNG and grid state are not resumed.

## Research Writer

Research Writer generates current summaries, Research Director briefings, activity digests and object reports from the normalized canonical snapshot. It must not invent evidence, upgrade confidence, or turn a visual pattern into a scientific claim.

## Adapter Manager

Adapter Manager stores local external-engine registrations in `Config/Studio/adapters.json`. Contract-ready adapters declare `archon_adapter.json` using schema `archon_adapter_manifest_v1`.

Current Studio treats declared adapter entrypoints as metadata only. Connected does not mean executable.

## Settings

Studio stores local preferences in `Config/Studio/settings.json` using schema `archon_studio_settings_v1`.

Preferences include:

- optional researcher name and project label;
- preferred engine UI (`embedded`, `native`, or neutral `ask`);
- Studio surface appearance (Midnight, Graphite, or Daylight);
- interface density;
- reduced-motion preference;
- first-run onboarding state.

These settings do not modify Atlas/Knowledge, scientific metrics, experiments, evidence, or Analyzer conclusions.

## Runtime diagnostics

Open **Settings → Runtime Diagnostics** to inspect:

- Python and local tool availability;
- Search / Observer / Analyzer launcher presence;
- Atlas and Knowledge first-run state;
- ARCHON / Results / Atlas / Config paths;
- writable-state checks and free disk space;
- whether a license file is present in the current release tree.

Folder-open actions are allowlisted to the ARCHON root, Results, Atlas and Config directories. Studio does not accept an arbitrary filesystem path from the browser for this action.

## Troubleshooting

### Runtime bridge offline

Launch Studio with `./ARCHON_STUDIO.sh` for the normal desktop workflow. The launcher owns the runtime lifecycle and closes Studio-owned engine processes when the app window exits. `./STUDIO.sh` remains the production browser/diagnostic launcher.

### No Atlas yet

This is a valid first-run state. Start Universe Search. Studio will rebuild the normalized snapshot after canonical source files appear.

### Frontend dependencies missing

Run:

```bash
cd archon-studio
npm ci
cd ..
./STUDIO.sh
```

## Local-state boundary

Studio-generated settings, adapter registry, runtime logs, previews and presentation caches are local UI/operator state. They must not be silently promoted into canonical scientific evidence.


## STUDIO14 production frontend

Build the frontend once from a development checkout:

```bash
./STUDIO_BUILD_PRODUCTION.sh
```

The builder uses the local frontend dependencies to produce `archon-studio/dist/` and then seals the bundle with `archon-studio-build.json`. The seal includes a hash of the current Studio source contract, so `./STUDIO.sh` rejects a stale bundle after frontend source changes.

The production bundle deliberately excludes `public/studio/snapshot.json` and preview assets. Canonical research state remains live and is served by `Tools/archon_studio_runtime.py` from `/studio/*`. Normal `./ARCHON_STUDIO.sh` and `./STUDIO.sh` startup no longer invoke npm, Vite, Wrangler or `node_modules`. The desktop launcher owns the Python runtime in-process; the web launcher starts the same production runtime as a subprocess.


### Desktop launcher lifecycle

`./ARCHON_STUDIO.sh` runs `Tools/archon_studio_desktop.py`. It verifies the sealed production bundle, rebuilds the live snapshot, hosts Studio on `127.0.0.1:8765`, and opens a dedicated Chromium-family `--app` window when available. Closing that window shuts down the in-process runtime and any Studio-owned Search/Observer/Analyzer child processes.

If no Chromium-family app-mode browser is installed, STUDIO15 opens the system browser and keeps a small native Tk launcher window with **Open Studio** and **Quit Studio** controls so runtime ownership remains explicit. On Linux, `./STUDIO_INSTALL_DESKTOP.sh` installs an **ARCHON Studio** application-menu entry for the current checkout.

## STUDIO15 desktop launcher and release readiness

Run the cumulative regression and readiness audit from the ARCHON root:

```bash
./STUDIO_REGRESSION.sh
```

The audit is read-only with respect to canonical scientific state. It checks the normalized snapshot, runtime bridge, localhost API contracts, zero-research cold start, current Studio regressions, TypeScript/Python syntax, portable source paths and release packaging state. The latest report is written to `Results/Studio/release_readiness.json` and appears in **Settings → STUDIO15 Release Readiness**.

A successful STUDIO15 result may report **READY_FOR_PACKAGING** while final release remains blocked. The production frontend and desktop launcher are ready; remaining distribution work is tracked separately:

- keep `archon-studio/dist/` current with `./STUDIO_BUILD_PRODUCTION.sh` (the production frontend no longer uses `npm run dev`);
- keep the STUDIO15 desktop launcher in the release manifest and platform packaging;
- integrate Studio files into the clean release whitelist / dependency closure.

These are packaging tasks, not scientific-runtime failures.
