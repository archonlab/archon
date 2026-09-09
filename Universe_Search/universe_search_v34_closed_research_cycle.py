#!/usr/bin/env python3
# Universe Search v34.5 - Search Mode + Prompt Pause Integrity
# Put this file in the same folder as universe_search_core.py

import json
import math
import os
import random
import re
import sys
import time
import hashlib
import collections
import atexit
import signal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from archon_paths import SEARCH_RESULTS_DIR, WORLD_ATLAS_DIR, KNOWLEDGE_ATLAS_DIR, ensure_layout
from World_Portability import WorldPortabilityService
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

try:
    from Universe_Search import universe_search_core as base
except Exception as e:
    print('Could not import universe_search_core.py')
    print('Put this file in the same folder as universe_search_core.py')
    print('Import error:', repr(e))
    raise

try:
    from Universe_Search import research_bridge
except Exception as e:
    research_bridge = None
    print('[ResearchBridge] optional module unavailable; legacy search remains active:', repr(e))

try:
    from Universe_Search import evolution_policy
except Exception as e:
    evolution_policy = None
    print('[EvolutionPolicy] optional module unavailable; guided selection falls back safely:', repr(e))

try:
    from Observer import observer_ecology
except Exception as e:
    observer_ecology = None
    print('[ObserverEcology] optional module unavailable; ecology foundation disabled:', repr(e))

try:
    from Observer import observer_ecosystem
except Exception as e:
    observer_ecosystem = None
    print('[ObserverEcosystem] optional module unavailable; ecosystem layer disabled:', repr(e))

try:
    from Observer import observer_civilization
except Exception as e:
    observer_civilization = None
    print('[ObserverCivilization] optional module unavailable; civilization layer disabled:', repr(e))

try:
    from Observer import observer_institutions
except Exception as e:
    observer_institutions = None
    print('[ObserverInstitutions] optional module unavailable; institutions layer disabled:', repr(e))

try:
    from Observer import observer_network
except Exception as e:
    observer_network = None
    print('[ObserverNetwork] optional module unavailable; scientific network layer disabled:', repr(e))

try:
    from Universe_Search import network_dynamics
except Exception as e:
    network_dynamics = None
    print('[NetworkDynamics] optional module unavailable; scientific dynamics layer disabled:', repr(e))

try:
    from Universe_Search import discovery_engine
except Exception as e:
    discovery_engine = None
    print('[DiscoveryEngine] optional module unavailable; discovery layer disabled:', repr(e))

try:
    from Universe_Search import research_programs
except Exception as e:
    research_programs = None
    print('[ResearchPrograms] optional module unavailable; research program layer disabled:', repr(e))

try:
    from Universe_Search import research_teams
except Exception as e:
    research_teams = None
    print('[ResearchTeams] optional module unavailable; research team layer disabled:', repr(e))

try:
    from Universe_Search import experiment_engine
except Exception as e:
    experiment_engine = None
    print('[ExperimentEngine] optional module unavailable; experiment layer disabled:', repr(e))

try:
    from Universe_Search import theory_engine
except Exception as e:
    theory_engine = None
    print('[TheoryEngine] optional module unavailable; theory layer disabled:', repr(e))

try:
    from Universe_Search import paradigm_engine
except Exception as e:
    paradigm_engine = None
    print('[ParadigmEngine] optional module unavailable; paradigm layer disabled:', repr(e))

try:
    from Universe_Search import research_cycle
except Exception as e:
    research_cycle = None
    print('[ResearchCycle] optional module unavailable; closed loop disabled:', repr(e))

try:
    from Universe_Search import scientific_state_builder
except Exception as e:
    scientific_state_builder = None
    print('[ScientificState] optional module unavailable; adaptive state disabled:', repr(e))

try:
    from Universe_Search import search_job_loader
except Exception as e:
    search_job_loader = None
    print('[SearchMode] optional module unavailable; ordinary legacy search remains active:', repr(e))

try:
    from Universe_Search import target_scoring
except Exception as e:
    target_scoring = None
    print('[TargetScoring] optional module unavailable; target bonus disabled safely:', repr(e))

# ---------------- Settings ----------------

ensure_layout()
OUT_DIR = SEARCH_RESULTS_DIR
ATLAS_DIR = WORLD_ATLAS_DIR
CHECKPOINT_FILE = OUT_DIR / 'checkpoint_observer_niches.json'
ATLAS_INDEX_FILE = ATLAS_DIR / 'atlas_index.json'
ATLAS_INDEX_JSONL = ATLAS_DIR / 'atlas_index.jsonl'
RULE_ID_ALLOCATOR_FILE = KNOWLEDGE_ATLAS_DIR / 'rule_id_allocator.json'
CRYSTAL_CACHE_FILE = OUT_DIR / 'crystal_defect_cache.json'
DIVERSITY_SKELETON_FILE = OUT_DIR / 'diversity_skeleton.json'
ORGANISM_CACHE_FILE = OUT_DIR / 'organism_life_cache.json'
INFORMATION_CACHE_FILE = OUT_DIR / 'information_dynamics_cache.json'
REFERENCE_CONTROL_REGISTRY_FILE = KNOWLEDGE_ATLAS_DIR / 'reference_control_registry.json'
_reference_control_cache = None
_genome_registry_cache = None
SEARCH_RUN_ID = f"search_{int(time.time())}_{os.getpid()}"
RUN_HISTORY_DIR = OUT_DIR / 'search_runs' / SEARCH_RUN_ID
SEARCH_RUNTIME_PREFIX = 'ARCHON_SEARCH_RUNTIME_JSON='

PARALLEL = True
WORKERS = max(1, min(6, (os.cpu_count() or 2) // 2 or 1))

# Prevent worker processes from writing shared cache files.
MAIN_PID = int(os.environ.get('UNIVERSE_SEARCH_MAIN_PID', os.getpid()))

# Graceful pause request. SIGTERM/SIGINT stop active evaluation workers, discard
# the incomplete generation, and preserve the last scientifically complete
# state. Resume then evaluates that generation again from its original
# population.
PAUSE_REQUESTED = False


class SearchPauseRequested(RuntimeError):
    """Internal control flow used to leave an incomplete generation safely."""


def _request_graceful_pause(signum, _frame):
    global PAUSE_REQUESTED
    if not PAUSE_REQUESTED:
        PAUSE_REQUESTED = True
        print(
            f'\n[Search] graceful pause requested by signal {signum}. '
            'Stopping active evaluations and saving a safe checkpoint...'
        )


signal.signal(signal.SIGTERM, _request_graceful_pause)
signal.signal(signal.SIGINT, _request_graceful_pause)

ATLAS_TOP_GLOBAL = 6
ATLAS_TOP_NICHES = 8
ATLAS_PREVIEW_TICKS = 900
ATLAS_PREVIEW_CELL = 5
ATLAS_MIN_SCORE = 60.0
ATLAS_SAVE_GIF = True

# Keep this modest. GIF generation runs in the main process.
ATLAS_GIF_TOP_LIMIT = 3
ATLAS_GIF_TICKS = 600
ATLAS_GIF_FRAMES = 24
ATLAS_GIF_STRIDE = 8
ATLAS_GIF_CELL = 4

CRYSTAL_DEFECT_ANALYSIS = True
CRYSTAL_DEFECT_BONUS = 28.0
CRYSTAL_BURN_TICKS = 360
CRYSTAL_FRAMES = 28
CRYSTAL_FRAME_STRIDE = 6
CRYSTAL_MAX_PERIOD = 8
CRYSTAL_DEFECT_TOL = 0.22
_crystal_cache = None
NOVELTY_ARCHIVE_MAXLEN = 2000
CRYSTAL_CACHE_MAX_ITEMS = 5000

# Organism probe: quick post-score replay that rewards long-lived localized structures.
ORGANISM_ANALYSIS = True
ORGANISM_BONUS = 42.0
ORGANISM_TICKS = 2200
ORGANISM_SAMPLE_EVERY = 20
ORGANISM_DEFECT_THRESHOLD = 0.18
ORGANISM_MIN_CELLS = 8
ORGANISM_COLLAPSE_GRACE = 200
ORGANISM_CACHE_MAX_ITEMS = 5000
_organism_cache = None

# Information probe: asks what survives time, collapse, and transformation.
INFORMATION_ANALYSIS = True
INFORMATION_BONUS = 36.0
INFORMATION_TICKS = ORGANISM_TICKS
INFORMATION_SAMPLE_EVERY = ORGANISM_SAMPLE_EVERY
INFORMATION_HISTORY_LIMIT = 96
INFORMATION_CACHE_MAX_ITEMS = 5000
_information_cache = None

POPULATION = base.POPULATION
GENERATIONS = base.GENERATIONS
KEEP_TOP = base.KEEP_TOP
ELITES = base.ELITES
RANDOM_IMMIGRANTS = base.RANDOM_IMMIGRANTS
OBSERVER_COUNT = base.OBSERVER_COUNT
OBSERVER_ELITES = base.OBSERVER_ELITES

# ---------------- Helpers ----------------

def now_s():
    return time.strftime('%H:%M:%S')


def emit_search_runtime_event(event, **fields):
    """Emit PID-bound operational telemetry without affecting Search science."""
    payload = {
        'schema': 'archon_search_runtime_v1',
        'event': str(event),
        'pid': os.getpid(),
        'search_run_id': SEARCH_RUN_ID,
        **fields,
    }
    print(SEARCH_RUNTIME_PREFIX + json.dumps(payload, sort_keys=True), flush=True)


def configure_base_paths():
    base.OUT_DIR = OUT_DIR
    base.HUMAN_FAV_FILE = OUT_DIR / 'human_favorites.json'
    base.OBSERVER_ARCHIVE_FILE = OUT_DIR / 'observer_profiles.json'


def atomic_write_text(path, text, encoding='utf-8'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def atomic_write_json(path, payload, indent=2):
    atomic_write_text(path, json.dumps(payload, indent=indent, ensure_ascii=False), encoding='utf-8')


def rule_hash(rule):
    """Stable genome hash. rule_id is excluded by base.rule_signature()."""
    raw = base.rule_signature(rule).encode('utf-8')
    return hashlib.sha1(raw).hexdigest()[:12]


def _build_genome_registry(force=False):
    """Map genome hash -> canonical Atlas identity.

    When historical duplicates exist, the smallest rule ID is treated as the
    canonical identity. This preserves old reference rules such as 00251.
    """
    global _genome_registry_cache
    if _genome_registry_cache is not None and not force:
        return _genome_registry_cache

    registry = {}

    def register(rule_id, genome_hash, folder=None):
        try:
            rid = int(rule_id)
        except Exception:
            return
        h = str(genome_hash or '').strip()
        if not h:
            return
        current = registry.get(h)
        candidate = {
            'rule_id': rid,
            'folder': str(folder).replace('\\', '/') if folder else None,
        }
        if current is None or rid < int(current.get('rule_id', rid)):
            registry[h] = candidate

    # Index is fast, but old entries may be incomplete.
    for entry in load_atlas_index():
        if not isinstance(entry, dict):
            continue
        register(entry.get('rule_id'), entry.get('key'), entry.get('folder'))

    # rule.json is the source of truth for historical Atlas content.
    if ATLAS_DIR.exists():
        for path in ATLAS_DIR.rglob('rule.json'):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                rule = base.rule_from_dict(payload)
                register(payload.get('rule_id'), rule_hash(rule), path.parent)
            except Exception:
                continue

    _genome_registry_cache = registry
    return registry


def _canonical_identity_for_rule(rule):
    h = rule_hash(rule)
    record = _build_genome_registry().get(h)
    if not record:
        return h, int(rule.rule_id), None
    return h, int(record['rule_id']), record.get('folder')


def _clone_rule_with_id(rule, rule_id):
    payload = base.rule_to_dict(rule)
    payload['rule_id'] = int(rule_id)
    return base.rule_from_dict(payload)


def canonicalize_evaluated_results(results):
    """Replace historical duplicate IDs with their canonical Atlas IDs.

    The actual evaluated ID remains in metrics['evaluated_rule_id'], so run
    provenance is not lost. Scientific layers receive canonical identities and
    therefore cannot count an unchanged seed genome as a new discovery.
    """
    registry = _build_genome_registry()
    canonicalized = []
    duplicate_count = 0

    for score, rule, metrics in results:
        h = rule_hash(rule)
        original_id = int(rule.rule_id)
        record = registry.get(h)
        canonical_id = int(record['rule_id']) if record else original_id

        metrics['genome_hash'] = h
        metrics['evaluated_rule_id'] = original_id
        metrics['canonical_rule_id'] = canonical_id
        metrics['is_existing_genome'] = record is not None
        metrics['duplicate_of'] = canonical_id if canonical_id != original_id else None

        if canonical_id != original_id:
            rule = _clone_rule_with_id(rule, canonical_id)
            duplicate_count += 1

        canonicalized.append((score, rule, metrics))

    if duplicate_count:
        print(
            f'[GenomeDedup] canonicalized {duplicate_count} evaluated clone(s); '
            'scores remain as run evidence, no new canonical rules created.'
        )
    return canonicalized


def _write_duplicate_evidence(
    canonical_folder,
    *,
    gen,
    score_mode,
    source,
    score,
    evaluated_rule_id,
    canonical_rule_id,
    genome_hash,
    metrics,
):
    if not canonical_folder:
        return None
    evidence_dir = Path(canonical_folder) / 'search_evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / (
        f'{SEARCH_RUN_ID}_g{int(gen):02d}_'
        f'eval_{int(evaluated_rule_id):05d}.json'
    )
    payload = {
        'schema': 'archon_existing_genome_evaluation_v1',
        'search_run_id': SEARCH_RUN_ID,
        'generation': int(gen),
        'score_mode': score_mode,
        'source': source,
        'score': float(score),
        'genome_hash': genome_hash,
        'evaluated_rule_id': int(evaluated_rule_id),
        'canonical_rule_id': int(canonical_rule_id),
        'duplicate_of': int(canonical_rule_id),
        'metrics': metrics,
    }
    atomic_write_json(path, payload, indent=2)
    return path


def _existing_rule_id_high_watermark():
    """Find the largest rule ID ever persisted by Search or Atlas."""
    highest = -1
    if ATLAS_DIR.exists():
        for path in ATLAS_DIR.rglob('rule.json'):
            m = re.search(r'rule_(\d+)_', str(path.parent.name))
            if m:
                highest = max(highest, int(m.group(1)))
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                highest = max(highest, int(payload.get('rule_id', -1)))
            except Exception:
                pass
    def walk(obj):
        if isinstance(obj, dict):
            yield obj
            for value in obj.values():
                yield from walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from walk(value)

    for path in (ATLAS_INDEX_FILE, CHECKPOINT_FILE):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        for node in walk(payload):
            if isinstance(node, dict) and node.get('rule_id') is not None:
                try: highest = max(highest, int(node['rule_id']))
                except Exception: pass
            if isinstance(node, dict) and node.get('next_id') is not None:
                try: highest = max(highest, int(node['next_id']) - 1)
                except Exception: pass
    return highest


def _reserve_rule_id_range_unlocked(count):
    """Atomically reserve IDs for a fresh run; gaps are safer than reuse."""
    count = max(1, int(count))
    state = {}
    if RULE_ID_ALLOCATOR_FILE.exists():
        try:
            state = json.loads(RULE_ID_ALLOCATOR_FILE.read_text(encoding='utf-8'))
        except Exception:
            state = {}
    persisted_next = int(state.get('next_id', 0) or 0)
    observed_next = _existing_rule_id_high_watermark() + 1
    start = max(persisted_next, observed_next)
    end = start + count - 1
    history = state.get('reservations', []) if isinstance(state.get('reservations'), list) else []
    history.append({
        'search_run_id': SEARCH_RUN_ID,
        'reserved_start': start,
        'reserved_end': end,
        'reserved_count': count,
        'created_at': now_s(),
    })
    payload = {
        'version': 'v1.0 persistent rule ID allocator',
        'next_id': end + 1,
        'last_search_run_id': SEARCH_RUN_ID,
        'reservations': history[-1000:],
    }
    atomic_write_json(RULE_ID_ALLOCATOR_FILE, payload, indent=2)
    print(f'[RuleID] reserved unique range {start:05d}..{end:05d} for {SEARCH_RUN_ID}')
    return start, end


def reserve_rule_id_range(count):
    """Reserve through the shared Atlas writer lock used by WORLD1 imports."""
    service = WorldPortabilityService(
        PROJECT_ROOT,
        world_atlas_dir=ATLAS_DIR,
        knowledge_atlas_dir=KNOWLEDGE_ATLAS_DIR,
    )
    with service.atlas_write_lock():
        return _reserve_rule_id_range_unlocked(count)


def slug(s):
    s = ''.join(ch.lower() if ch.isalnum() else '_' for ch in str(s))
    while '__' in s:
        s = s.replace('__', '_')
    return s.strip('_')[:50] or 'unknown'


def stars(x, max_value=1.0):
    v = max(0.0, min(1.0, float(x) / max_value))
    n = int(round(v * 5))
    return '★' * n + '☆' * (5 - n)


def load_crystal_cache():
    global _crystal_cache
    if _crystal_cache is not None:
        return _crystal_cache
    if CRYSTAL_CACHE_FILE.exists():
        try:
            _crystal_cache = json.loads(CRYSTAL_CACHE_FILE.read_text(encoding='utf-8'))
        except Exception:
            _crystal_cache = {}
    else:
        _crystal_cache = {}
    return _crystal_cache


def save_crystal_cache():
    if os.getpid() != MAIN_PID or _crystal_cache is None:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = list(_crystal_cache.items())[-CRYSTAL_CACHE_MAX_ITEMS:]
    atomic_write_json(CRYSTAL_CACHE_FILE, dict(items), indent=2)


atexit.register(save_crystal_cache)


def load_organism_cache():
    global _organism_cache
    if _organism_cache is not None:
        return _organism_cache
    if ORGANISM_CACHE_FILE.exists():
        try:
            _organism_cache = json.loads(ORGANISM_CACHE_FILE.read_text(encoding='utf-8'))
        except Exception:
            _organism_cache = {}
    else:
        _organism_cache = {}
    return _organism_cache


def save_organism_cache():
    if os.getpid() != MAIN_PID or _organism_cache is None:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = list(_organism_cache.items())[-ORGANISM_CACHE_MAX_ITEMS:]
    atomic_write_json(ORGANISM_CACHE_FILE, dict(items), indent=2)


atexit.register(save_organism_cache)


def load_information_cache():
    global _information_cache
    if _information_cache is not None:
        return _information_cache
    if INFORMATION_CACHE_FILE.exists():
        try:
            _information_cache = json.loads(INFORMATION_CACHE_FILE.read_text(encoding='utf-8'))
        except Exception:
            _information_cache = {}
    else:
        _information_cache = {}
    return _information_cache


def save_information_cache():
    if os.getpid() != MAIN_PID or _information_cache is None:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = list(_information_cache.items())[-INFORMATION_CACHE_MAX_ITEMS:]
    atomic_write_json(INFORMATION_CACHE_FILE, dict(items), indent=2)


atexit.register(save_information_cache)


def empty_organism_metrics(error=None):
    return {
        'organism_probe_ticks': ORGANISM_TICKS,
        'organism_lifetime': 0,
        'organism_survived_probe': False,
        'organism_collapse_tick': None,
        'organism_peak_objects': 0,
        'organism_peak_largest': 0,
        'organism_peak_defects': 0,
        'organism_events': 0,
        'organism_health_end': 0.0,
        'organism_bonus': 0.0,
        'organism_cache_hit': False,
        'organism_analysis_error': error,
    }


def _median(vals):
    vals = sorted(vals)
    n = len(vals)
    if not n:
        return 0.0
    mid = n // 2
    return float(vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2)


def _organism_mask(frame, threshold=ORGANISM_DEFECT_THRESHOLD):
    even, odd = [], []
    for y in range(base.H):
        row = frame[y]
        for x in range(base.W):
            if (x + y) & 1:
                odd.append(float(row[x]))
            else:
                even.append(float(row[x]))
    even_med, odd_med = _median(even), _median(odd)
    mask = [[False] * base.W for _ in range(base.H)]
    count = 0
    for y in range(base.H):
        row = frame[y]
        for x in range(base.W):
            bg = odd_med if ((x + y) & 1) else even_med
            if abs(float(row[x]) - bg) >= threshold:
                mask[y][x] = True
                count += 1
    return mask, count


def _organism_components(mask, min_cells=ORGANISM_MIN_CELLS):
    seen = [[False] * base.W for _ in range(base.H)]
    sizes = []
    for y0 in range(base.H):
        for x0 in range(base.W):
            if not mask[y0][x0] or seen[y0][x0]:
                continue
            q = collections.deque([(x0, y0)])
            seen[y0][x0] = True
            size = 0
            while q:
                x, y = q.popleft()
                size += 1
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx = (x + dx) % base.W
                    ny = (y + dy) % base.H
                    if mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            if size >= min_cells:
                sizes.append(size)
    sizes.sort(reverse=True)
    return sizes


def analyze_organism_life(rule):
    """Fast survival probe: rewards localized long-lived structures, not full-field noise."""
    cache = load_organism_cache()
    key = rule_hash(rule)
    if key in cache:
        out = dict(empty_organism_metrics())
        out.update(cache[key])
        out['organism_cache_hit'] = True
        return out

    try:
        sim = base.FieldSim(rule)
        birth_tick = None
        last_alive = None
        collapse_tick = None
        peak_objects = 0
        peak_largest = 0
        peak_defects = 0
        events = 0
        prev_objects = None
        final_largest = 0

        for tick in range(0, ORGANISM_TICKS + 1):
            if tick % ORGANISM_SAMPLE_EVERY == 0:
                frame = _field_to_matrix(sim)
                mask, defects = _organism_mask(frame)
                sizes = _organism_components(mask)
                objects = len(sizes)
                largest = sizes[0] if sizes else 0
                final_largest = largest
                alive = largest >= ORGANISM_MIN_CELLS

                if prev_objects is not None and objects != prev_objects:
                    events += 1
                prev_objects = objects

                if alive:
                    if birth_tick is None:
                        birth_tick = tick
                    last_alive = tick
                    peak_objects = max(peak_objects, objects)
                    peak_largest = max(peak_largest, largest)
                    peak_defects = max(peak_defects, defects)
                elif birth_tick is not None and last_alive is not None:
                    if tick - last_alive >= ORGANISM_COLLAPSE_GRACE:
                        collapse_tick = last_alive
                        break
            if tick < ORGANISM_TICKS:
                sim.step()

        lifetime = 0 if birth_tick is None or last_alive is None else max(0, last_alive - birth_tick)
        survived = birth_tick is not None and collapse_tick is None and last_alive is not None and last_alive >= ORGANISM_TICKS - ORGANISM_SAMPLE_EVERY
        health_end = (final_largest / peak_largest) if peak_largest else 0.0

        # Avoid rewarding full-field soup too much; localized long-lived structures get the meat.
        life_ratio = min(1.0, lifetime / max(1, ORGANISM_TICKS))
        size_factor = min(1.0, math.log1p(peak_largest) / math.log1p(base.W * base.H * 0.35)) if peak_largest else 0.0
        locality_factor = 1.0
        if peak_largest > base.W * base.H * 0.65:
            locality_factor = 0.35
        event_factor = min(1.0, events / 10.0)
        survived_factor = 0.20 if survived else 0.0
        bonus = ORGANISM_BONUS * (0.58 * life_ratio + 0.22 * size_factor + 0.12 * event_factor + survived_factor) * locality_factor

        out = {
            'organism_probe_ticks': ORGANISM_TICKS,
            'organism_lifetime': int(lifetime),
            'organism_survived_probe': bool(survived),
            'organism_collapse_tick': collapse_tick,
            'organism_peak_objects': int(peak_objects),
            'organism_peak_largest': int(peak_largest),
            'organism_peak_defects': int(peak_defects),
            'organism_events': int(events),
            'organism_health_end': round(float(health_end), 6),
            'organism_bonus': round(float(bonus), 6),
            'organism_cache_hit': False,
            'organism_analysis_error': None,
        }
        if os.getpid() == MAIN_PID:
            cache[key] = {k: v for k, v in out.items() if k not in ('organism_cache_hit',)}
        return out
    except Exception as e:
        out = empty_organism_metrics(repr(e))
        return out


def _mask_count(mask):
    return sum(1 for y in range(base.H) for x in range(base.W) if mask[y][x])


def _mask_entropy(mask):
    total = max(1, base.W * base.H)
    p = _mask_count(mask) / total
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p)))


def _mask_centroid_radius(mask):
    pts = []
    for y in range(base.H):
        for x in range(base.W):
            if mask[y][x]:
                pts.append((x, y))
    if not pts:
        return None, 0.0
    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    radii = []
    for x, y in pts:
        dx = abs(x - cx); dy = abs(y - cy)
        dx = min(dx, base.W - dx); dy = min(dy, base.H - dy)
        radii.append(math.sqrt(dx * dx + dy * dy))
    return (cx, cy), (sum(radii) / len(radii) if radii else 0.0)


def empty_information_metrics(error=None):
    return {
        'information_probe_ticks': INFORMATION_TICKS,
        'information_samples': 0,
        'information_entropy_mean': 0.0,
        'information_entropy_peak': 0.0,
        'information_temporal_stability': 0.0,
        'identity_persistence': 0.0,
        'legacy_score': 0.0,
        'post_collapse_structure': 0.0,
        'information_survival': 0.0,
        'expansion_front_speed': 0.0,
        'collapse_reason_hint': 'unknown',
        'information_bonus': 0.0,
        'information_cache_hit': False,
        'information_analysis_error': error,
    }


def analyze_information_dynamics(rule):
    """Information probe: what remains similar, useful, or structured across time and collapse."""
    if not INFORMATION_ANALYSIS:
        return empty_information_metrics('disabled')
    cache = load_information_cache()
    key = rule_hash(rule)
    if key in cache:
        out = dict(empty_information_metrics())
        out.update(cache[key])
        out['information_cache_hit'] = True
        return out

    try:
        sim = base.FieldSim(rule)
        samples = []
        prev_mask = None
        temporal = []
        first_alive_tick = None
        last_alive_tick = None
        peak = None
        collapse_tick = None
        dead_streak = 0
        events = 0
        prev_objects = None

        for tick in range(0, INFORMATION_TICKS + 1):
            if tick % INFORMATION_SAMPLE_EVERY == 0:
                frame = _field_to_matrix(sim)
                mask, defects = _organism_mask(frame)
                sizes = _organism_components(mask)
                objects = len(sizes)
                largest = sizes[0] if sizes else 0
                alive = largest >= ORGANISM_MIN_CELLS
                entropy = _mask_entropy(mask)
                _, radius = _mask_centroid_radius(mask)
                record = {'tick': tick, 'mask': mask, 'defects': defects, 'objects': objects, 'largest': largest, 'alive': alive, 'entropy': entropy, 'radius': radius}
                samples.append(record)
                if len(samples) > INFORMATION_HISTORY_LIMIT:
                    samples.pop(0)

                if prev_mask is not None:
                    temporal.append(_jaccard(prev_mask, mask))
                prev_mask = mask

                if prev_objects is not None and objects != prev_objects:
                    events += 1
                prev_objects = objects

                if alive:
                    if first_alive_tick is None:
                        first_alive_tick = tick
                    last_alive_tick = tick
                    dead_streak = 0
                    if peak is None or largest > peak['largest']:
                        peak = record
                elif first_alive_tick is not None:
                    dead_streak += INFORMATION_SAMPLE_EVERY
                    if collapse_tick is None and dead_streak >= ORGANISM_COLLAPSE_GRACE:
                        collapse_tick = last_alive_tick
                        # Do not break: legacy needs post-collapse samples.

            if tick < INFORMATION_TICKS:
                sim.step()

        if not samples:
            return empty_information_metrics('no samples')

        entropies = [r['entropy'] for r in samples]
        entropy_mean = sum(entropies) / len(entropies)
        entropy_peak = max(entropies) if entropies else 0.0
        temporal_stability = sum(temporal) / len(temporal) if temporal else 0.0

        peak = peak or max(samples, key=lambda r: r['largest'])
        after_peak = [r for r in samples if r['tick'] >= peak['tick']]
        identity_persistence = sum(_jaccard(peak['mask'], r['mask']) for r in after_peak) / len(after_peak) if after_peak else 0.0

        final = samples[-1]
        peak_largest = max(1, peak['largest'])
        post_collapse_structure = min(1.0, final['largest'] / peak_largest)
        final_similarity = _jaccard(peak['mask'], final['mask'])
        leftover_density = min(1.0, final['defects'] / max(1, peak['defects'])) if peak['defects'] else 0.0
        legacy_score = max(0.0, min(1.0, 0.55 * final_similarity + 0.30 * post_collapse_structure + 0.15 * leftover_density))

        first = next((r for r in samples if r['alive']), samples[0])
        dt = max(1, peak['tick'] - first['tick'])
        expansion_front_speed = max(0.0, min(1.0, (peak['radius'] - first['radius']) / dt * 20.0))
        entropy_balance = max(0.0, 1.0 - abs(entropy_mean - 0.55) / 0.55)
        event_factor = min(1.0, events / 12.0)
        information_survival = max(0.0, min(1.0, 0.34 * temporal_stability + 0.24 * identity_persistence + 0.18 * legacy_score + 0.14 * entropy_balance + 0.10 * event_factor))

        if collapse_tick is None and final['alive']:
            reason = 'survived_probe'
        elif final['defects'] < max(8, peak.get('defects', 0) * 0.10):
            reason = 'faded_to_empty_or_smooth'
        elif final['largest'] > peak_largest * 0.75 and final_similarity < 0.25:
            reason = 'identity_drift'
        elif final['objects'] > peak.get('objects', 0) + 2:
            reason = 'fragmentation'
        elif final['largest'] < peak_largest * 0.30:
            reason = 'structural_collapse'
        else:
            reason = 'transformed_or_unclear'

        bonus = INFORMATION_BONUS * information_survival
        out = {
            'information_probe_ticks': INFORMATION_TICKS,
            'information_samples': int(len(samples)),
            'information_entropy_mean': round(float(entropy_mean), 6),
            'information_entropy_peak': round(float(entropy_peak), 6),
            'information_temporal_stability': round(float(temporal_stability), 6),
            'identity_persistence': round(float(identity_persistence), 6),
            'legacy_score': round(float(legacy_score), 6),
            'post_collapse_structure': round(float(post_collapse_structure), 6),
            'information_survival': round(float(information_survival), 6),
            'expansion_front_speed': round(float(expansion_front_speed), 6),
            'collapse_reason_hint': reason,
            'information_bonus': round(float(bonus), 6),
            'information_cache_hit': False,
            'information_analysis_error': None,
        }
        if os.getpid() == MAIN_PID:
            cache[key] = {k: v for k, v in out.items() if k not in ('information_cache_hit',)}
        return out
    except Exception as e:
        return empty_information_metrics(repr(e))


def merge_information_into_main_cache(rule, metrics):
    if os.getpid() != MAIN_PID or not isinstance(metrics, dict):
        return
    if metrics.get('information_cache_hit'):
        return
    cache = load_information_cache()
    key = rule_hash(rule)
    payload = {k: v for k, v in metrics.items() if k.startswith('information_') or k in ('identity_persistence', 'legacy_score', 'post_collapse_structure', 'expansion_front_speed', 'collapse_reason_hint')}
    cache[key] = payload


def merge_organism_into_main_cache(rule, metrics):
    if os.getpid() != MAIN_PID or not isinstance(metrics, dict):
        return
    if metrics.get('organism_cache_hit'):
        return
    cache = load_organism_cache()
    key = rule_hash(rule)
    payload = {k: v for k, v in metrics.items() if k.startswith('organism_')}
    cache[key] = payload


def empty_crystal_metrics(error=None):
    return {
        'crystal_order': 0.0,
        'crystal_period_x': 0,
        'crystal_period_y': 0,
        'crystal_error': 1.0,
        'defect_density': 0.0,
        'defect_density_var': 0.0,
        'defect_persistence': 0.0,
        'defect_motion': 0.0,
        'defect_density_window': 0.0,
        'quasi_particle_score': 0.0,
        'crystal_cache_hit': False,
        'crystal_analysis_error': error,
    }


def safe_crystal_metrics(metrics):
    out = empty_crystal_metrics(metrics.get('crystal_analysis_error') if isinstance(metrics, dict) else 'invalid crystal metrics')
    if isinstance(metrics, dict):
        out.update(metrics)
    return out


def merge_crystal_into_main_cache(rule, metrics):
    if os.getpid() != MAIN_PID or not isinstance(metrics, dict):
        return
    if metrics.get('crystal_cache_hit'):
        return
    cache = load_crystal_cache()
    key = rule_hash(rule)
    cached_payload = {k: v for k, v in metrics.items() if k.startswith('crystal_') or k.startswith('defect_') or k == 'quasi_particle_score'}
    cache[key] = cached_payload


def classify_world(m):
    active = m.get('active', 0.0)
    edge = m.get('edge', 0.0)
    life = m.get('ms_local_life', 0.0)
    flow = m.get('ms_flow', 0.0)
    rot = m.get('ms_rotation_flow', 0.0)
    mem = max(0.0, m.get('memory_trace_score', 0.0)) / 120.0
    tracks = m.get('persistent_tracks', 0)
    ent_q = m.get('best_entity_quality', 0.0)
    reg = m.get('best_region_score', 0.0)
    cr = m.get('cosmic_recovery', 0.0)
    nested = m.get('nested_score_raw', 0.0)

    if active > 0.96 and edge < 0.04: return 'Degenerate Smooth Soup'
    if active < 0.02: return 'Dead Empty Field'
    if tracks >= 30 and ent_q >= 0.65 and life >= 0.55:
        if mem >= 0.55: return 'Entity Memory Ecology'
        return 'Persistent Entity Garden'
    if flow > 0.08 and rot > 0.06 and life >= 0.55: return 'Rotating Flow World'
    if flow > 0.08 and life >= 0.50: return 'Flow World'
    if mem >= 0.60 and cr >= 0.45: return 'Recovery Memory World'
    if reg >= 0.45 and nested >= 0.55: return 'Living Boundary Region'
    if nested >= 0.60 and life >= 0.50: return 'Nested Local Life'

    qps = m.get('quasi_particle_score', 0.0)
    xtal = m.get('crystal_order', 0.0)
    dd = m.get('defect_density', 0.0)
    if qps >= 0.42 and xtal >= 0.55: return 'Crystal Defect Ecology'
    if xtal >= 0.72 and 0.005 <= dd <= 0.22: return 'Almost Crystal With Defects'
    if xtal >= 0.78 and dd < 0.005: return 'Clean Crystal'
    if cr >= 0.65: return 'Resilient Scaffold'
    return 'Weird Unknown'


def _field_to_matrix(sim):
    return [[float(sim.a[y][x]) for x in range(base.W)] for y in range(base.H)]


def _best_crystal_unit(frame, max_period=CRYSTAL_MAX_PERIOD):
    H, W = base.H, base.W
    best = None
    for py in range(1, max_period + 1):
        for px in range(1, max_period + 1):
            sums = [[0.0 for _ in range(px)] for __ in range(py)]
            counts = [[0 for _ in range(px)] for __ in range(py)]
            for y in range(H):
                yy = y % py
                row = frame[y]
                for x in range(W):
                    xx = x % px
                    sums[yy][xx] += row[x]
                    counts[yy][xx] += 1
            tile = [[sums[y][x] / max(1, counts[y][x]) for x in range(px)] for y in range(py)]
            err = 0.0
            for y in range(H):
                ty = y % py
                row = frame[y]
                for x in range(W):
                    err += abs(row[x] - tile[ty][x % px])
            err /= max(1, W * H)
            parsimony = 1.0 - 0.018 * (px * py - 1)
            order = max(0.0, (1.0 - err / 0.50) * parsimony)
            if best is None or order > best[0]:
                recon = [[tile[y % py][x % px] for x in range(W)] for y in range(H)]
                best = (order, px, py, err, recon)
    return best


def _mask_stats(mask):
    H, W = base.H, base.W
    n = 0
    sx = 0.0
    sy = 0.0
    for y in range(H):
        row = mask[y]
        for x, v in enumerate(row):
            if v:
                n += 1
                sx += x
                sy += y
    if n <= 0: return 0, None
    return n, (sx / n, sy / n)


def _jaccard(a, b):
    inter = 0
    union = 0
    for y in range(base.H):
        ar = a[y]; br = b[y]
        for x in range(base.W):
            av = ar[x]; bv = br[x]
            if av or bv:
                union += 1
                if av and bv: inter += 1
    return inter / union if union else 0.0


def analyze_crystal_defects(rule):
    if not CRYSTAL_DEFECT_ANALYSIS:
        return {}
    try:
        sim = base.FieldSim(rule)
        for _ in range(CRYSTAL_BURN_TICKS):
            sim.step()

        frames = []
        for _ in range(CRYSTAL_FRAMES):
            frames.append(_field_to_matrix(sim))
            for __ in range(CRYSTAL_FRAME_STRIDE):
                sim.step()

        order, px, py, err, recon = _best_crystal_unit(frames[-1])
        masks = []
        densities = []
        centroids = []
        for frame in frames:
            mask = []
            n = 0
            for y in range(base.H):
                row = []
                for x in range(base.W):
                    is_defect = abs(frame[y][x] - recon[y][x]) > CRYSTAL_DEFECT_TOL
                    row.append(is_defect)
                    if is_defect: n += 1
                mask.append(row)
            masks.append(mask)
            densities.append(n / max(1, base.W * base.H))
            _, c = _mask_stats(mask)
            centroids.append(c)

        density = sum(densities) / len(densities)
        density_var = sum((d - density) ** 2 for d in densities) / len(densities)
        if len(masks) > 1:
            persistence = sum(_jaccard(masks[i], masks[i + 1]) for i in range(len(masks) - 1)) / (len(masks) - 1)
        else:
            persistence = 0.0

        moves = []
        for a, b in zip(centroids, centroids[1:]):
            if a is not None and b is not None:
                dx = abs(a[0] - b[0]); dy = abs(a[1] - b[1])
                dx = min(dx, base.W - dx); dy = min(dy, base.H - dy)
                moves.append(math.sqrt(dx * dx + dy * dy) / max(base.W, base.H))
        motion = min(1.0, (sum(moves) / len(moves)) * 8.0) if moves else 0.0

        if density <= 0.0: density_window = 0.0
        elif density < 0.015: density_window = density / 0.015
        elif density <= 0.18: density_window = 1.0
        elif density < 0.34: density_window = 1.0 - (density - 0.18) / 0.16
        else: density_window = 0.0
        density_window = max(0.0, min(1.0, density_window))

        persistence_window = max(0.0, 1.0 - abs(persistence - 0.45) / 0.45)
        dynamics = max(persistence_window, min(1.0, 0.55 * persistence + 0.45 * motion))
        quasi = max(0.0, min(1.0, order * density_window * dynamics))

        return {
            'crystal_order': round(order, 6),
            'crystal_period_x': px,
            'crystal_period_y': py,
            'crystal_error': round(err, 6),
            'defect_density': round(density, 6),
            'defect_density_var': round(density_var, 8),
            'defect_persistence': round(persistence, 6),
            'defect_motion': round(motion, 6),
            'defect_density_window': round(density_window, 6),
            'quasi_particle_score': round(quasi, 6),
        }
    except Exception as e:
        return {'crystal_analysis_error': repr(e)}


def atlas_report_text(rule, score, metrics, gen, score_mode, source):
    klass = classify_world(metrics)
    lines = [
        f'World: Rule {rule.rule_id:05d}',
        f'Class: {klass}',
        f'Discovered/updated in generation: {gen}',
        f'Source: {source}',
        f'Score: {score:.3f}',
        '',
        'Core signals:',
        f'  Life:        {stars(metrics.get("ms_local_life",0))}  {metrics.get("ms_local_life",0):.3f}',
        f'  Memory:      {stars(max(0,metrics.get("memory_trace_score",0))/120)}  {metrics.get("memory_trace_score",0):.1f}',
        f'  Flow:        {stars(metrics.get("ms_flow",0), 0.35)}  {metrics.get("ms_flow",0):.4f}',
        f'  Rotation:    {stars(metrics.get("ms_rotation_flow",0), 0.25)}  {metrics.get("ms_rotation_flow",0):.4f}',
        f'  Recovery:    {stars(metrics.get("cosmic_recovery",0))}  {metrics.get("cosmic_recovery",0):.3f}',
        f'  Region:      {stars(metrics.get("best_region_score",0))}  {metrics.get("best_region_score",0):.3f}',
        f'  Entity Q:    {stars(metrics.get("best_entity_quality",0))}  {metrics.get("best_entity_quality",0):.3f}',
        f'  Crystal:     {stars(metrics.get("crystal_order",0))}  {metrics.get("crystal_order",0):.3f}',
        f'  Defects:     {stars(metrics.get("defect_density_window",0))}  density={metrics.get("defect_density",0):.4f} persist={metrics.get("defect_persistence",0):.3f} move={metrics.get("defect_motion",0):.3f}',
        f'  Quasi-score: {stars(metrics.get("quasi_particle_score",0))}  {metrics.get("quasi_particle_score",0):.3f}',
        f'  Info survive:{stars(metrics.get("information_survival",0))}  surv={metrics.get("information_survival",0):.3f} id={metrics.get("identity_persistence",0):.3f} legacy={metrics.get("legacy_score",0):.3f}',
        '',
        'Raw metrics:'
    ]
    for k in ['active','edge','boundary_activity','islands','nested_score_raw','ms_local_life','persistent_tracks','entity_count','best_entity_quality','best_region_score','macro_scaffold','memory_trace_score','cosmic_recovery','crystal_order','crystal_period_x','crystal_period_y','crystal_error','defect_density','defect_persistence','defect_motion','quasi_particle_score','observer_id','observer_score','observer_archetype','post_test_truth','organism_lifetime','organism_survived_probe','organism_peak_objects','organism_peak_largest','organism_events','organism_health_end','organism_bonus','information_entropy_mean','information_temporal_stability','identity_persistence','legacy_score','post_collapse_structure','information_survival','expansion_front_speed','collapse_reason_hint','information_bonus']:
        if k in metrics:
            lines.append(f'  {k}: {metrics[k]}')
    lines.extend([
        '',
        'Observer note:',
        f'  {metrics.get("observer_note", "no note")}',
        '',
        'Rule lineage:',
        f'  parent_a: {rule.parent_a}',
        f'  parent_b: {rule.parent_b}',
        f'  seed: {rule.seed}',
        '',
        'Interpretation:',
        '  This is an automatically generated field note. Open the rule in the viewer',
        '  before treating this classification as real. The Atlas is a map, not a verdict.'
    ])
    return '\n'.join(lines) + '\n'


def cell_rgb_from_value(a):
    blue = int((1.0 - a) * 230)
    yellow = int(a * 255)
    green = int(120 + 90 * (1.0 - abs(a - 0.5) * 2))
    return yellow, green, blue


def save_preview_png(rule, path, ticks=ATLAS_PREVIEW_TICKS, cell=ATLAS_PREVIEW_CELL):
    try:
        from PIL import Image
    except Exception:
        return False
    sim = base.FieldSim(rule)
    for _ in range(ticks):
        sim.step()
    img = Image.new('RGB', (base.W, base.H))
    pix = img.load()
    for y in range(base.H):
        for x in range(base.W):
            pix[x, y] = cell_rgb_from_value(sim.a[y][x])
    img = img.resize((base.W * cell, base.H * cell), Image.Resampling.NEAREST)
    img.save(path)
    return True


def save_preview_gif(rule, path, ticks=ATLAS_GIF_TICKS, frames=ATLAS_GIF_FRAMES, stride=ATLAS_GIF_STRIDE, cell=ATLAS_GIF_CELL):
    try:
        from PIL import Image
    except Exception:
        return False
    sim = base.FieldSim(rule)
    for _ in range(ticks):
        sim.step()
    images = []
    for _ in range(frames):
        img = Image.new('RGB', (base.W, base.H))
        pix = img.load()
        for y in range(base.H):
            for x in range(base.W):
                pix[x, y] = cell_rgb_from_value(sim.a[y][x])
        img = img.resize((base.W * cell, base.H * cell), Image.Resampling.NEAREST)
        images.append(img)
        for __ in range(stride):
            sim.step()
    if not images: return False
    images[0].save(path, save_all=True, append_images=images[1:], duration=80, loop=0)
    return True


def load_atlas_index():
    if ATLAS_INDEX_FILE.exists():
        try: return json.loads(ATLAS_INDEX_FILE.read_text(encoding='utf-8'))
        except Exception: return []
    return []


def save_atlas_index(index):
    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    index_sorted = sorted(index, key=lambda x: x.get('score', 0.0), reverse=True)
    atomic_write_json(ATLAS_INDEX_FILE, index_sorted, indent=2)
    jsonl_text = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in index_sorted)
    atomic_write_text(ATLAS_INDEX_JSONL, jsonl_text, encoding='utf-8')


def add_to_atlas(gen, score_mode, items):
    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    index = load_atlas_index()
    by_key = {item.get('key'): item for item in index if item.get('key')}
    hashes_by_id = {}
    for existing in index:
        try:
            existing_id = int(existing.get('rule_id'))
        except Exception:
            continue
        existing_hash = str(existing.get('key') or '')
        if existing_hash:
            hashes_by_id.setdefault(existing_id, set()).add(existing_hash)
    added = []
    for atlas_rank, (source, score, rule, metrics) in enumerate(items, 1):
        if metrics.get('eval_error') is not None:
            continue
        if score < ATLAS_MIN_SCORE and metrics.get('post_test_truth', 0) in (None, 0):
            continue
        h = rule_hash(rule)
        evaluated_rule_id = int(metrics.get('evaluated_rule_id', rule.rule_id))
        registry = _build_genome_registry()
        existing_identity = registry.get(h)

        if existing_identity is not None:
            canonical_rule_id = int(existing_identity['rule_id'])
            canonical_folder = existing_identity.get('folder')
            metrics['genome_hash'] = h
            metrics['evaluated_rule_id'] = evaluated_rule_id
            metrics['canonical_rule_id'] = canonical_rule_id
            metrics['is_existing_genome'] = True
            metrics['duplicate_of'] = (
                canonical_rule_id
                if evaluated_rule_id != canonical_rule_id
                else None
            )
            evidence_path = _write_duplicate_evidence(
                canonical_folder,
                gen=gen,
                score_mode=score_mode,
                source=source,
                score=score,
                evaluated_rule_id=evaluated_rule_id,
                canonical_rule_id=canonical_rule_id,
                genome_hash=h,
                metrics=metrics,
            )
            existing_entry = by_key.get(h)
            if existing_entry is not None:
                existing_entry['last_evaluated_run'] = SEARCH_RUN_ID
                existing_entry['last_evaluated_generation'] = gen
                existing_entry['last_evaluated_score'] = score
                existing_entry['evaluation_count'] = int(
                    existing_entry.get('evaluation_count', 0) or 0
                ) + 1
                if evidence_path is not None:
                    existing_entry['latest_evidence'] = str(
                        evidence_path
                    ).replace('\\', '/')
            print(
                f'  atlas dedup: evaluated {evaluated_rule_id:05d} '
                f'is existing genome {canonical_rule_id:05d} ({h}); '
                'stored evidence only'
            )
            continue

        conflicting = hashes_by_id.get(int(rule.rule_id), set()) - {h}
        if conflicting:
            raise RuntimeError(
                f'Rule ID collision blocked: {rule.rule_id:05d} maps to {h}, '
                f'but Atlas already has {sorted(conflicting)}. Start a fresh run with the persistent allocator.'
            )
        klass = classify_world(metrics)
        key = h
        folder = ATLAS_DIR / f'{slug(klass)}' / f'rule_{rule.rule_id:05d}_{h}'
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write_json(folder / 'rule.json', base.rule_to_dict(rule), indent=2)
        atomic_write_json(folder / 'metrics.json', metrics, indent=2)
        atomic_write_text(folder / 'report.txt', atlas_report_text(rule, score, metrics, gen, score_mode, source), encoding='utf-8')

        preview_path = folder / 'preview.png'
        if not preview_path.exists():
            save_preview_png(rule, preview_path)

        gif_path = folder / 'preview.gif'
        make_gif = ATLAS_SAVE_GIF and atlas_rank <= ATLAS_GIF_TOP_LIMIT
        if make_gif and not gif_path.exists():
            save_preview_gif(rule, gif_path)

        entry = {
            'key': key, 'rule_id': rule.rule_id, 'class': klass, 'generation': gen,
            'score_mode': score_mode, 'score': score, 'source': source,
            'folder': str(folder).replace('\\', '/'),
            'preview': str(preview_path).replace('\\', '/') if preview_path.exists() else None,
            'preview_gif': str(gif_path).replace('\\', '/') if gif_path.exists() else None,
            'active': metrics.get('active'), 'edge': metrics.get('edge'), 'life': metrics.get('ms_local_life'),
            'flow': metrics.get('ms_flow'), 'rotation': metrics.get('ms_rotation_flow'), 'memory': metrics.get('memory_trace_score'),
            'recovery': metrics.get('cosmic_recovery'), 'region': metrics.get('best_region_score'), 'entities': metrics.get('entity_count'),
            'tracks': metrics.get('persistent_tracks'), 'observer_id': metrics.get('observer_id'), 'observer_archetype': metrics.get('observer_archetype'),
            'observer_note': metrics.get('observer_note'), 'post_test_truth': metrics.get('post_test_truth'), 'crystal_order': metrics.get('crystal_order'),
            'defect_density': metrics.get('defect_density'), 'defect_persistence': metrics.get('defect_persistence'), 'defect_motion': metrics.get('defect_motion'),
            'quasi_particle_score': metrics.get('quasi_particle_score'),
            'organism_lifetime': metrics.get('organism_lifetime'), 'organism_peak_largest': metrics.get('organism_peak_largest'),
            'organism_events': metrics.get('organism_events'), 'organism_survived_probe': metrics.get('organism_survived_probe'),
            'information_survival': metrics.get('information_survival'), 'identity_persistence': metrics.get('identity_persistence'),
            'legacy_score': metrics.get('legacy_score'), 'post_collapse_structure': metrics.get('post_collapse_structure'),
            'expansion_front_speed': metrics.get('expansion_front_speed'), 'collapse_reason_hint': metrics.get('collapse_reason_hint'),
        }
        if key not in by_key or score > by_key[key].get('score', -1e9):
            by_key[key] = entry
        added.append(entry)
        hashes_by_id.setdefault(int(rule.rule_id), set()).add(h)
        _build_genome_registry()[h] = {
            'rule_id': int(rule.rule_id),
            'folder': str(folder).replace('\\', '/'),
        }
    save_atlas_index(list(by_key.values()))
    if added:
        print(f'  atlas: {len(added)} entries touched; index={ATLAS_INDEX_FILE}')


def select_atlas_items(results, score_mode):
    chosen = []
    seen = set()
    results = [r for r in results if r[2].get('eval_error') is None]
    for score, rule, metrics in results[:ATLAS_TOP_GLOBAL]:
        sig = base.rule_signature(rule)
        if sig not in seen:
            chosen.append(('global_top', score, rule, metrics)); seen.add(sig)
    if score_mode == 'observer_niches':
        for niche, (score, rule, metrics) in base.niche_champions(results)[:ATLAS_TOP_NICHES]:
            sig = base.rule_signature(rule)
            if sig not in seen:
                chosen.append((f'niche:{niche}', score, rule, metrics)); seen.add(sig)
    records = [
        ('record_tracks', lambda m: m.get('persistent_tracks', 0)),
        ('record_flow', lambda m: m.get('ms_flow', 0.0)),
        ('record_memory', lambda m: m.get('memory_trace_score', 0.0)),
        ('record_recovery', lambda m: m.get('cosmic_recovery', 0.0)),
        ('record_region', lambda m: m.get('best_region_score', 0.0)),
        ('record_quasiparticle', lambda m: m.get('quasi_particle_score', 0.0)),
        ('record_crystal_defects', lambda m: m.get('crystal_order', 0.0) * m.get('defect_density_window', 0.0)),
        ('record_organism_lifetime', lambda m: m.get('organism_lifetime', 0.0)),
        ('record_organism_size', lambda m: m.get('organism_peak_largest', 0.0)),
        ('record_information_survival', lambda m: m.get('information_survival', 0.0)),
        ('record_identity_persistence', lambda m: m.get('identity_persistence', 0.0)),
        ('record_legacy_score', lambda m: m.get('legacy_score', 0.0)),
    ]
    for name, fn in records:
        if not results: continue
        score, rule, metrics = max(results, key=lambda x: fn(x[2]))
        sig = base.rule_signature(rule)
        if sig not in seen and fn(metrics) > 0:
            chosen.append((name, score, rule, metrics)); seen.add(sig)
    return chosen

# ---------------- Parallel Evaluation ----------------

def evaluate_one_worker(args):
    configure_base_paths()
    idx, rule_dict, internal_mode, cached_crystal, cached_organism = args
    rule = base.rule_from_dict(rule_dict)
    try:
        score, metrics, _ = base.score_rule(rule, internal_mode)
        metrics['eval_error'] = None
        metrics['evaluation_status'] = 'EVALUATED'
    except base.FieldBackendError:
        # A backend/runtime failure invalidates the evaluator, not the candidate.
        # Let the parent abort Search without producing low-score evidence.
        raise
    except Exception as e:
        metrics = {
            'active': 0.0, 'edge': 0.0, 'boundary_activity': 0.0, 'islands': 0,
            'ms_local_life': 0.0, 'ms_flow': 0.0, 'ms_rotation_flow': 0.0,
            'memory_trace_score': 0.0, 'cosmic_recovery': 0.0,
            'degeneracy_penalty': 999.0, 'degeneracy_penalty_raw': 999.0,
            'eval_error': repr(e),
            'evaluation_status': 'CANDIDATE_ERROR',
        }
        metrics.update(empty_crystal_metrics('skipped because score_rule failed'))
        return idx, -1e9, base.rule_to_dict(rule), metrics

    if CRYSTAL_DEFECT_ANALYSIS:
        if isinstance(cached_crystal, dict):
            crystal = safe_crystal_metrics(cached_crystal)
            crystal['crystal_cache_hit'] = True
        else:
            try:
                crystal = safe_crystal_metrics(analyze_crystal_defects(rule))
                crystal['crystal_cache_hit'] = False
            except Exception as e:
                crystal = empty_crystal_metrics(repr(e))
        metrics.update(crystal)
    else:
        metrics.update(empty_crystal_metrics('disabled'))

    if ORGANISM_ANALYSIS:
        if isinstance(cached_organism, dict):
            org = dict(empty_organism_metrics())
            org.update(cached_organism)
            org['organism_cache_hit'] = True
        else:
            org = analyze_organism_life(rule)
        metrics.update(org)
    else:
        metrics.update(empty_organism_metrics('disabled'))

    if INFORMATION_ANALYSIS:
        info = analyze_information_dynamics(rule)
        metrics.update(info)
    else:
        metrics.update(empty_information_metrics('disabled'))

    return idx, score, base.rule_to_dict(rule), metrics


def evaluate_population(population, internal_mode, workers=WORKERS):
    if PAUSE_REQUESTED:
        raise SearchPauseRequested()

    crystal_cache = load_crystal_cache() if CRYSTAL_DEFECT_ANALYSIS else {}
    organism_cache = load_organism_cache() if ORGANISM_ANALYSIS else {}
    load_information_cache() if INFORMATION_ANALYSIS else {}
    jobs = []
    for i, r in enumerate(population):
        rh = rule_hash(r)
        cached = crystal_cache.get(rh) if CRYSTAL_DEFECT_ANALYSIS else None
        cached_org = organism_cache.get(rh) if ORGANISM_ANALYSIS else None
        jobs.append((i, base.rule_to_dict(r), internal_mode, cached, cached_org))

    if not PARALLEL or workers <= 1:
        out = []
        for job in jobs:
            if PAUSE_REQUESTED:
                raise SearchPauseRequested()
            out.append(evaluate_one_worker(job))
            print(f'    eval {len(out):03d}/{len(jobs)} done [{now_s()}]', flush=True)
        out.sort(key=lambda x: x[0])
        return out

    out = []
    total = len(jobs)
    completed = 0
    failed = 0
    started_at = time.monotonic()
    last_progress_at = started_at

    print(
        f'  parallel eval: workers={workers}, jobs={total} [{now_s()}]',
        flush=True,
    )

    ex = ProcessPoolExecutor(max_workers=workers)
    pending = set()
    normal_shutdown = False
    try:
        pending = {
            ex.submit(evaluate_one_worker, job)
            for job in jobs
        }

        while pending:
            if PAUSE_REQUESTED:
                queued = sum(1 for fut in pending if fut.cancel())
                worker_processes = list(
                    (getattr(ex, '_processes', None) or {}).values()
                )
                # Do not use the executor context manager here: its __exit__
                # waits for every running evaluation, which made Close appear
                # to ignore SIGTERM for many minutes.
                ex.shutdown(wait=False, cancel_futures=True)
                stopped = 0
                for process in worker_processes:
                    if process.is_alive():
                        # Workers inherit the parent's graceful SIGTERM handler
                        # on Linux, so terminate() would merely set their local
                        # pause flag and let the expensive evaluation continue.
                        # Their incomplete outputs are intentionally discarded,
                        # making an immediate worker kill safe here.
                        process.kill()
                        stopped += 1
                deadline = time.monotonic() + 2.0
                for process in worker_processes:
                    remaining = max(0.0, deadline - time.monotonic())
                    process.join(timeout=remaining)
                print(
                    f'    eval pause: kept={completed}, '
                    f'cancelled_queued={queued}, stopped_workers='
                    f'{stopped} [{now_s()}]',
                    flush=True,
                )
                raise SearchPauseRequested()

            done, pending = wait(
                pending,
                timeout=1.0,
                return_when=FIRST_COMPLETED,
            )

            if not done:
                elapsed = int(time.monotonic() - started_at)
                idle = int(time.monotonic() - last_progress_at)
                if elapsed > 0 and elapsed % 30 == 0:
                    print(
                        f'    eval heartbeat: {completed:03d}/{total} done, '
                        f'{len(pending):03d} running/pending, '
                        f'elapsed={elapsed}s, no_completion_for={idle}s '
                        f'[{now_s()}]',
                        flush=True,
                    )
                continue

            for fut in done:
                completed += 1
                try:
                    out.append(fut.result())
                except base.FieldBackendError:
                    # Do not convert evaluator infrastructure failure into a
                    # partial generation or a scientific candidate failure.
                    raise
                except Exception as e:
                    failed += 1
                    print(
                        f'    eval {completed:03d}/{total} failed hard: '
                        f'{repr(e)} [{now_s()}]',
                        flush=True,
                    )

            last_progress_at = time.monotonic()

            # Frequent enough to reassure the user, sparse enough not to flood output.
            if completed % 5 == 0 or not pending:
                elapsed = int(time.monotonic() - started_at)
                print(
                    f'    eval {completed:03d}/{total} done '
                    f'(failed={failed}, elapsed={elapsed}s) [{now_s()}]',
                    flush=True,
                )
        normal_shutdown = True
    finally:
        if normal_shutdown:
            ex.shutdown(wait=True)
        elif not PAUSE_REQUESTED:
            ex.shutdown(wait=False, cancel_futures=True)

    out.sort(key=lambda x: x[0])
    return out

# ---------------- Diversity Skeleton ----------------

def _vec_distance(a, b):
    n = min(len(a), len(b))
    if n <= 0: return 0.0
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(n)) / n)


def load_diversity_skeleton():
    if DIVERSITY_SKELETON_FILE.exists():
        try: return json.loads(DIVERSITY_SKELETON_FILE.read_text(encoding='utf-8'))
        except Exception: return []
    return []


def save_diversity_skeleton(skeleton):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DIVERSITY_SKELETON_FILE, skeleton, indent=2)


def update_diversity_skeleton(skeleton, results, gen, limit=140):
    existing = {item.get('key') for item in skeleton}
    existing_vecs = [item.get('vector', []) for item in skeleton if item.get('vector')]
    candidates = []
    for score, rule, metrics in results:
        if metrics.get('eval_error') is not None:
            continue
        vec = base.metric_feature_vector(metrics)
        key = rule_hash(rule)
        if key in existing:
            continue
        far = 1.0 if not existing_vecs else min(_vec_distance(vec, v) for v in existing_vecs)
        weird = max(
            metrics.get('in_generation_diversity', 0.0),
            metrics.get('novelty_behavior', 0.0),
            metrics.get('quasi_particle_score', 0.0),
            metrics.get('information_survival', 0.0),
            metrics.get('legacy_score', 0.0),
        )
        keep_score = float(score) * 0.015 + far * 55.0 + weird * 25.0
        candidates.append((keep_score, key, score, rule, metrics, vec, far, weird))

    candidates.sort(key=lambda x: x[0], reverse=True)
    for _, key, score, rule, metrics, vec, far, weird in candidates[:20]:
        skeleton.append({
            'key': key, 'generation': gen, 'rule_id': rule.rule_id, 'score': score,
            'class': classify_world(metrics), 'diversity_distance': round(far, 6), 'weirdness': round(weird, 6),
            'vector': vec,
            'metrics': {
                'life': metrics.get('ms_local_life'), 'memory': metrics.get('memory_trace_score'),
                'flow': metrics.get('ms_flow'), 'recovery': metrics.get('cosmic_recovery'),
                'crystal_order': metrics.get('crystal_order'), 'defect_density': metrics.get('defect_density'),
                'quasi_particle_score': metrics.get('quasi_particle_score'),
            'organism_lifetime': metrics.get('organism_lifetime'), 'organism_peak_largest': metrics.get('organism_peak_largest'),
            'organism_events': metrics.get('organism_events'), 'organism_survived_probe': metrics.get('organism_survived_probe'),
                'information_survival': metrics.get('information_survival'), 'identity_persistence': metrics.get('identity_persistence'),
                'legacy_score': metrics.get('legacy_score'), 'post_collapse_structure': metrics.get('post_collapse_structure'),
            },
            'rule': base.rule_to_dict(rule),
        })
    skeleton.sort(key=lambda x: (x.get('weirdness', 0.0), x.get('diversity_distance', 0.0), x.get('score', 0.0)), reverse=True)
    skeleton = skeleton[:limit]
    save_diversity_skeleton(skeleton)
    return skeleton

# ---------------- Checkpoint ----------------

def _checkpoint_search_identity(search_config):
    if search_job_loader is not None and hasattr(
        search_job_loader,
        'search_config_identity',
    ):
        return search_job_loader.search_config_identity(search_config)
    return {
        'schema': 'archon_search_config_identity_v1',
        'search_mode': getattr(search_config, 'search_mode', 'ordinary'),
        'requested_score_mode': getattr(
            search_config,
            'requested_score_mode',
            None,
        ),
    }


def save_checkpoint(gen, score_mode, population, observer_population, next_id, next_observer_id, best_ever, novelty_archive, diversity_skeleton=None, search_config=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'completed_generation': gen, 'score_mode': score_mode,
        'search_config_identity': _checkpoint_search_identity(search_config),
        'search_run_id': SEARCH_RUN_ID,
        'population': [base.rule_to_dict(r) for r in population],
        'observer_population': observer_population, 'next_id': next_id, 'next_observer_id': next_observer_id,
        'best_ever': None if best_ever is None else {
            'score': best_ever[0], 'rule': base.rule_to_dict(best_ever[1]), 'metrics': best_ever[2],
        },
        'novelty_archive': list(novelty_archive), 'diversity_skeleton': diversity_skeleton or [],
        'random_state': repr(random.getstate()),
    }
    atomic_write_json(CHECKPOINT_FILE, payload, indent=2)
    atomic_write_json(RUN_HISTORY_DIR / CHECKPOINT_FILE.name, payload, indent=2)
    print(f'  checkpoint saved securely: {CHECKPOINT_FILE}')


def load_checkpoint(expected_mode, expected_search_config=None):
    if not CHECKPOINT_FILE.exists(): return None
    data = json.loads(CHECKPOINT_FILE.read_text(encoding='utf-8'))
    if data.get('score_mode') != expected_mode:
        print(f'Checkpoint mode mismatch: {data.get("score_mode")} != {expected_mode}')
        return None
    expected_identity = _checkpoint_search_identity(expected_search_config)
    stored_identity = data.get('search_config_identity')
    if not isinstance(stored_identity, dict):
        if expected_identity.get('search_mode') != 'ordinary':
            print(
                'Checkpoint Search mode is unknown (legacy checkpoint); '
                f'cannot safely resume as {expected_identity.get("search_mode")}.'
            )
            return None
        print(
            '[SearchMode] legacy ordinary checkpoint has no mode identity; '
            'resuming with compatibility guard.'
        )
    elif stored_identity.get('sha256') != expected_identity.get('sha256'):
        print(
            'Checkpoint Search configuration mismatch: '
            f'stored={stored_identity.get("search_mode", "unknown")}/'
            f'{stored_identity.get("job_id") or "-"} '
            f'requested={expected_identity.get("search_mode", "unknown")}/'
            f'{expected_identity.get("job_id") or "-"}'
        )
        return None
    population = [base.rule_from_dict(d) for d in data['population']]
    best = data.get('best_ever')
    best_ever = None
    if best:
        best_ever = (best['score'], base.rule_from_dict(best['rule']), best['metrics'])
    return {
        'start_gen': int(data.get('completed_generation', 0)) + 1,
        'population': population,
        'observer_population': data.get('observer_population') or base.make_observer_population(),
        'next_id': int(data.get('next_id', len(population))),
        'next_observer_id': int(data.get('next_observer_id', base.OBSERVER_COUNT)),
        'best_ever': best_ever,
        'novelty_archive': data.get('novelty_archive', []),
        'diversity_skeleton': data.get('diversity_skeleton', []),
    }


# ---------------- Research Bridge + Evolution Policy + Strategy v24.3 ----------------

def load_research_bridge_plan():
    """Load Research Director suggestions without changing legacy search behavior."""
    if research_bridge is None:
        return None
    try:
        script_dir = Path(__file__).resolve().parent
        return research_bridge.load_research_plan(script_dir=script_dir, cwd=Path.cwd(), verbose=True)
    except Exception as e:
        print(f'[ResearchBridge] failed to load director plan; using legacy search: {e!r}')
        return None


def save_research_bridge_status(plan):
    if research_bridge is None or plan is None:
        return
    try:
        path = research_bridge.write_bridge_status(OUT_DIR, plan)
        print(f'[ResearchBridge] status saved: {path}')
    except Exception as e:
        print(f'[ResearchBridge] failed to save bridge status: {e!r}')


def announce_and_save_initial_evolution_policy(plan):
    """v24.3: build and save policy + strategy immediately, before generation 1 starts.

    This proves the adaptive layer is connected even during a long first evaluation.
    The actual policy is still rebuilt after each generation using the real elite count.
    """
    if evolution_policy is None:
        print('[EvolutionPolicy] module not available; adaptive evolution disabled')
        return None
    if not plan or not getattr(plan, 'active', False):
        print('[EvolutionPolicy] no active Research Director plan; legacy evolution')
        return None
    try:
        policy = evolution_policy.build_evolution_policy(
            plan,
            population_size=POPULATION,
            elite_count=max(2, ELITES),
            random_immigrants=RANDOM_IMMIGRANTS,
        )
        path = evolution_policy.write_policy_snapshot(
            OUT_DIR,
            policy,
            extra={'phase': 'startup', 'script': Path(__file__).name},
        )
        print(
            f'[EvolutionPolicy] v26.0 loaded | mode={getattr(policy, "mode", "?")} '
            f'explore={getattr(policy, "explore_ratio", 0):.2f} '
            f'exploit={getattr(policy, "exploit_ratio", 0):.2f} '
            f'control={getattr(policy, "control_ratio", 0):.2f} '
            f'local={getattr(policy, "local_ratio", 0):.2f}'
        )
        print(
            f'[EvolutionPolicy] params | mutation={getattr(policy, "mutation_rate", 0):.3f} '
            f'intensity={getattr(policy, "mutation_intensity", 0):.3f} '
            f'crossover={getattr(policy, "crossover_bias", 0):.2f} '
            f'targets x/e/c/l={getattr(policy, "target_explore", 0)}/'
            f'{getattr(policy, "target_exploit", 0)}/'
            f'{getattr(policy, "target_control", 0)}/'
            f'{getattr(policy, "target_local", 0)}'
        )
        print(f'[EvolutionPolicy] status saved: {path}')
        try:
            strategy = evolution_policy.build_evolution_strategy(policy)
            spath = evolution_policy.write_strategy_snapshot(
                OUT_DIR,
                policy,
                strategy,
                extra={'phase': 'startup', 'script': Path(__file__).name},
            )
            print(
                f'[EvolutionStrategy] v26.0 strategy={strategy.name} | '
                f'goal={strategy.goal} | mutation_profile={strategy.mutation_profile} '
                f'selection={strategy.selection_profile}'
            )
            print(f'[EvolutionStrategy] status saved: {spath}')
        except Exception as e:
            print(f'[EvolutionStrategy] failed to initialise strategy: {e!r}')
        return policy
    except Exception as e:
        print(f'[EvolutionPolicy] failed to initialise policy; falling back safely: {e!r}')
        return None



def initialize_observer_ecology_foundation(observer_population=None):
    """v25.3: create folder-safe observer species registry without changing evolution."""
    if observer_ecology is None:
        print('[ObserverEcology] module not available; folder-safe ecology disabled')
        return None
    try:
        status = observer_ecology.initialize_ecology(
            OUT_DIR,
            observer_population=observer_population,
            script=Path(__file__).name,
        )
        observer_ecology.print_status('ObserverEcology', status)
        print(f'[ObserverEcology] status saved: {OUT_DIR / "observer_ecology_status.json"}')
        return status
    except Exception as e:
        print(f'[ObserverEcology] failed to initialise ecology foundation: {e!r}')
        return None



def initialize_observer_ecosystem(observer_population=None):
    """v25.4: initialize folder-safe observer ecosystem layer above ecology."""
    if observer_ecosystem is None:
        print('[ObserverEcosystem] module not available; ecosystem disabled')
        return None
    try:
        status = observer_ecosystem.initialize_ecosystem(
            OUT_DIR,
            observer_population=observer_population,
            script=Path(__file__).name,
        )
        observer_ecosystem.print_status('ObserverEcosystem', status)
        print(f'[ObserverEcosystem] status saved: {OUT_DIR / "ecosystem_status.json"}')
        return status
    except Exception as e:
        print(f'[ObserverEcosystem] failed to initialise ecosystem: {e!r}')
        return None




def initialize_observer_civilization(observer_population=None):
    """v26.0: initialize folder-safe observer civilization layer above ecosystem."""
    if observer_civilization is None:
        print('[ObserverCivilization] module not available; civilization disabled')
        return None
    try:
        status = observer_civilization.initialize_civilization(
            OUT_DIR,
            observer_population=observer_population,
            script=Path(__file__).name,
        )
        observer_civilization.print_status('ObserverCivilization', status)
        print(f'[ObserverCivilization] status saved: {OUT_DIR / "observer_civilization_status.json"}')
        return status
    except Exception as e:
        print(f'[ObserverCivilization] failed to initialise civilization: {e!r}')
        return None


def apply_observer_civilization_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v26.0: apply gentle knowledge-civilization ordering/annotations over ecosystem population."""
    if observer_civilization is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_civilization, 'apply_civilization_layer'):
            return observer_population
        new_pop, report = observer_civilization.apply_civilization_layer(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ObserverCivilization] v26.0 applied | "
            f"stage={report.get('stage')} "
            f"maturity={report.get('maturity',0):.3f} "
            f"schools={report.get('school_count',0)} "
            f"memory={report.get('collective_memory_score',0):.3f} "
            f"exchange={report.get('knowledge_exchange_score',0):.3f} "
            f"lead={report.get('leading_school') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ObserverCivilization] failed; keeping ecosystem population: {e!r}')
        return observer_population




def initialize_observer_institutions(observer_population=None):
    """v27.0: initialize folder-safe knowledge institutions above observer civilization."""
    if observer_institutions is None:
        print('[ObserverInstitutions] module not available; institutions disabled')
        return None
    try:
        status = observer_institutions.initialize_institutions(
            OUT_DIR,
            observer_population=observer_population,
            script=Path(__file__).name,
        )
        observer_institutions.print_status('ObserverInstitutions', status)
        print(f'[ObserverInstitutions] status saved: {OUT_DIR / "observer_institutions_status.json"}')
        return status
    except Exception as e:
        print(f'[ObserverInstitutions] failed to initialise institutions: {e!r}')
        return None


def apply_observer_institution_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v27.0: apply gentle institution-level ordering/annotations over observer civilization."""
    if observer_institutions is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_institutions, 'apply_institution_layer'):
            return observer_population
        new_pop, report = observer_institutions.apply_institution_layer(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ObserverInstitutions] v27.0 applied | "
            f"stage={report.get('stage')} "
            f"maturity={report.get('institutional_maturity',0):.3f} "
            f"institutions={report.get('institution_count',0)} "
            f"archive={report.get('archive_entries',0)} "
            f"reuse={report.get('knowledge_reuse',0):.3f} "
            f"lead={report.get('leading_institution') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ObserverInstitutions] failed; keeping civilization population: {e!r}')
        return observer_population



def initialize_observer_network(observer_population=None):
    """v28.0: initialize folder-safe scientific network above knowledge institutions."""
    if observer_network is None:
        print('[ObserverNetwork] module not available; scientific network disabled')
        return None
    try:
        status = observer_network.initialize_network(
            OUT_DIR,
            observer_population=observer_population,
            script=Path(__file__).name,
        )
        observer_network.print_status('ObserverNetwork', status)
        print(f'[ObserverNetwork] status saved: {OUT_DIR / "observer_network_status.json"}')
        return status
    except Exception as e:
        print(f'[ObserverNetwork] failed to initialise network: {e!r}')
        return None



def initialize_network_dynamics(observer_population=None):
    """v28.1: initialize scientific dynamics layer above observer_network."""
    if network_dynamics is None:
        print('[NetworkDynamics] module not available; scientific dynamics disabled')
        return None
    try:
        status = network_dynamics.initialize_dynamics(
            OUT_DIR,
            script=Path(__file__).name,
        )
        network_dynamics.print_status('NetworkDynamics', status)
        print(f'[NetworkDynamics] status saved: {OUT_DIR / "network_dynamics_status.json"}')
        return status
    except Exception as e:
        print(f'[NetworkDynamics] failed to initialise dynamics: {e!r}')
        return None


def apply_network_dynamics_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v28.1: create institution events and scientific network history safely."""
    if network_dynamics is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(network_dynamics, 'apply_network_dynamics'):
            return observer_population
        new_pop, report = network_dynamics.apply_network_dynamics(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[NetworkDynamics] v28.1 applied | "
            f"phase={report.get('dynamic_phase') or '-'} "
            f"events={report.get('event_count',0)} "
            f"total={report.get('total_event_count',0)} "
            f"dynamism={report.get('network_dynamism',0):.3f} "
            f"volatility={report.get('network_volatility',0):.3f}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[NetworkDynamics] failed; keeping network population: {e!r}')
        return observer_population



def initialize_discovery_engine(observer_population=None):
    """v28.2: initialize persistent discovery objects above scientific dynamics."""
    if discovery_engine is None:
        print('[DiscoveryEngine] module not available; discovery layer disabled')
        return None
    try:
        status = discovery_engine.initialize_discovery(
            OUT_DIR,
            script=Path(__file__).name,
        )
        discovery_engine.print_status('DiscoveryEngine', status)
        print(f'[DiscoveryEngine] status saved: {OUT_DIR / "discovery_status.json"}')
        return status
    except Exception as e:
        print(f'[DiscoveryEngine] failed to initialise discovery layer: {e!r}')
        return None


def apply_discovery_engine_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v28.2: turn high-value results into persistent discovery objects safely."""
    if discovery_engine is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(discovery_engine, 'apply_discovery_layer'):
            return observer_population
        new_pop, report = discovery_engine.apply_discovery_layer(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[DiscoveryEngine] v28.2 applied | "
            f"new={report.get('new_discoveries',0)} "
            f"total={report.get('discovery_count',0)} "
            f"mean_conf={report.get('mean_confidence',0):.3f} "
            f"lead={report.get('leading_discovery') or '-'} "
            f"topic={report.get('leading_topic') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[DiscoveryEngine] failed; keeping scientific network population: {e!r}')
        return observer_population


def initialize_research_programs(observer_population=None):
    """v29.0: initialize long-horizon research programs above DiscoveryEngine."""
    if research_programs is None:
        print('[ResearchPrograms] module not available; research program layer disabled')
        return None
    try:
        status = research_programs.initialize_programs(
            OUT_DIR,
            script=Path(__file__).name,
        )
        research_programs.print_status('ResearchPrograms', status)
        print(f'[ResearchPrograms] status saved: {OUT_DIR / "research_programs_status.json"}')
        return status
    except Exception as e:
        print(f'[ResearchPrograms] failed to initialise research programs: {e!r}')
        return None


def apply_research_programs_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v29.0: convert discoveries into persistent research programs safely."""
    if research_programs is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(research_programs, 'apply_research_programs'):
            return observer_population
        new_pop, report = research_programs.apply_research_programs(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ResearchPrograms] v29.0 applied | "
            f"programs={report.get('program_count',0)} "
            f"created={report.get('created_programs',0)} "
            f"active={report.get('active_programs',0)} "
            f"mean_progress={report.get('mean_progress',0):.3f} "
            f"lead={report.get('leading_program') or '-'} "
            f"topic={report.get('leading_topic') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ResearchPrograms] failed; keeping discovery-layer population: {e!r}')
        return observer_population


def initialize_research_teams(observer_population=None):
    """v30.0: initialize research teams above long-horizon programs."""
    if research_teams is None:
        print('[ResearchTeams] module not available; research team layer disabled')
        return None
    try:
        status = research_teams.initialize_teams(
            OUT_DIR,
            script=Path(__file__).name,
        )
        research_teams.print_status('ResearchTeams', status)
        print(f'[ResearchTeams] status saved: {OUT_DIR / "research_teams_status.json"}')
        return status
    except Exception as e:
        print(f'[ResearchTeams] failed to initialise research teams: {e!r}')
        return None


def apply_research_teams_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v30.0: assign observers to persistent research teams safely."""
    if research_teams is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(research_teams, 'apply_research_teams'):
            return observer_population
        new_pop, report = research_teams.apply_research_teams(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ResearchTeams] v30.0 applied | "
            f"teams={report.get('team_count',0)} "
            f"created={report.get('created_teams',0)} "
            f"active={report.get('active_teams',0)} "
            f"productivity={report.get('mean_productivity',0):.3f} "
            f"lead={report.get('leading_team') or '-'} "
            f"topic={report.get('leading_topic') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ResearchTeams] failed; keeping research-program population: {e!r}')
        return observer_population


def initialize_experiment_engine(observer_population=None):
    """v31.0: initialize experiment engine above research teams."""
    if experiment_engine is None:
        print('[ExperimentEngine] module not available; experiment layer disabled')
        return None
    try:
        status = experiment_engine.initialize_experiments(
            OUT_DIR,
            script=Path(__file__).name,
        )
        experiment_engine.print_status('ExperimentEngine', status)
        print(f'[ExperimentEngine] status saved: {OUT_DIR / "experiment_status.json"}')
        return status
    except Exception as e:
        print(f'[ExperimentEngine] failed to initialise experiment layer: {e!r}')
        return None


def apply_experiment_engine_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v31.0: turn team activity into explicit experiment records safely."""
    if experiment_engine is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(experiment_engine, 'apply_experiment_engine'):
            return observer_population
        new_pop, report = experiment_engine.apply_experiment_engine(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ExperimentEngine] v31.0 applied | "
            f"experiments={report.get('experiment_count',0)} "
            f"new={report.get('new_experiments',0)} "
            f"success={report.get('successful_experiments',0)} "
            f"confidence={report.get('mean_confidence',0):.3f} "
            f"best={report.get('best_topic') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ExperimentEngine] failed; keeping research-team population: {e!r}')
        return observer_population


def initialize_theory_engine(observer_population=None):
    """v32.0: initialize theory formation above ExperimentEngine."""
    if theory_engine is None:
        print('[TheoryEngine] module not available; theory layer disabled')
        return None
    try:
        status = theory_engine.initialize_theories(
            OUT_DIR,
            script=Path(__file__).name,
        )
        theory_engine.print_status('TheoryEngine', status)
        print(f'[TheoryEngine] status saved: {OUT_DIR / "theory_engine_status.json"}')
        return status
    except Exception as e:
        print(f'[TheoryEngine] failed to initialise theory layer: {e!r}')
        return None


def apply_theory_engine_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v32.0: turn experiments/discoveries/programs into theory candidates safely."""
    if theory_engine is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(theory_engine, 'apply_theory_engine'):
            return observer_population
        new_pop, report = theory_engine.apply_theory_engine(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[TheoryEngine] v32.0 applied | "
            f"theories={report.get('theories',0)} "
            f"active={report.get('active_theories',0)} "
            f"created={report.get('created',0)} "
            f"lead={report.get('lead_topic') or '-'} "
            f"confidence={float(report.get('lead_confidence') or 0):.3f} "
            f"phase={report.get('phase','-')}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[TheoryEngine] failed; keeping experiment-layer population: {e!r}')
        return observer_population



def initialize_paradigm_engine(observer_population=None):
    """v33.0: initialize paradigm formation above TheoryEngine."""
    if paradigm_engine is None:
        print('[ParadigmEngine] module not available; paradigm layer disabled')
        return None
    try:
        status = paradigm_engine.initialize_paradigms(
            OUT_DIR,
            script=Path(__file__).name,
        )
        paradigm_engine.print_status('ParadigmEngine', status)
        print(f'[ParadigmEngine] status saved: {OUT_DIR / "paradigm_engine_status.json"}')
        return status
    except Exception as e:
        print(f'[ParadigmEngine] failed to initialise paradigm layer: {e!r}')
        return None


def apply_paradigm_engine_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v33.0: group theories/discoveries/programs into broader paradigms safely."""
    if paradigm_engine is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(paradigm_engine, 'apply_paradigm_engine'):
            return observer_population
        new_pop, report = paradigm_engine.apply_paradigm_engine(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ParadigmEngine] v33.0 applied | "
            f"paradigms={report.get('paradigms',0)} "
            f"active={report.get('active_paradigms',0)} "
            f"created={report.get('created',0)} "
            f"dominant={report.get('dominant_topic') or '-'} "
            f"coherence={float(report.get('coherence') or 0):.3f} "
            f"phase={report.get('phase','-')}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ParadigmEngine] failed; keeping theory-layer population: {e!r}')
        return observer_population


def initialize_research_cycle(observer_population=None):
    """v34.0: initialize closed research feedback loop above ParadigmEngine."""
    if research_cycle is None:
        print('[ResearchCycle] module not available; closed research cycle disabled')
        return None
    try:
        status = research_cycle.initialize_research_cycle(
            OUT_DIR,
            script=Path(__file__).name,
        )
        research_cycle.print_status('ResearchCycle', status)
        print(f'[ResearchCycle] status saved: {OUT_DIR / "research_cycle_status.json"}')
        return status
    except Exception as e:
        print(f'[ResearchCycle] failed to initialise closed cycle: {e!r}')
        return None


def build_generation_scientific_state(
    gen,
    score_mode,
    clean_results,
    best_ever,
    guided_info=None,
    cycle_state=None,
    persist=True,
):
    """Build a per-generation scientific state.

    Preview passes must use ``persist=False``.  Only the final pass is allowed
    to advance current_state/history; otherwise a second build in the same
    generation compares the generation with itself and destroys its deltas.
    """
    if scientific_state_builder is None:
        return None
    try:
        build_state = (
            scientific_state_builder.build_and_write_scientific_state
            if persist
            else scientific_state_builder.build_scientific_state
        )
        state = build_state(
            results_dir=OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            clean_results=clean_results,
            best_ever=best_ever,
            guided_info=guided_info,
            cycle_state=cycle_state,
            search_run_id=SEARCH_RUN_ID,
        )
        print(
            f"[ScientificState{' ' if persist else ' Preview '}] gen={gen} "
            f"trend={state.adaptive_trend} "
            f"progress={state.progress_score:.3f} stagnation={state.stagnation_generations} "
            f"new_discoveries={state.new_discoveries} positive_trials={state.positive_trials} "
            f"score_gain={state.score_gain:+.3f} novelty_gain={state.novelty_gain:+.3f} "
            f"diversity_gain={state.diversity_gain:+.3f}"
        )
        return state
    except Exception as e:
        print(f"[ScientificState] failed to build generation state: {e!r}")
        return None


def apply_research_cycle_layer(
    gen,
    score_mode,
    observer_population,
    clean_results,
    guided_info=None,
    scientific_state=None,
):
    """Run the scientific cycle and return both observers and fresh cycle state."""
    if research_cycle is None:
        return observer_population, None
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if scientific_state is not None:
            context['scientific_state'] = (
                scientific_state.to_dict()
                if hasattr(scientific_state, 'to_dict')
                else scientific_state
            )
        if not hasattr(research_cycle, 'apply_research_cycle'):
            return observer_population, None
        new_pop, report = research_cycle.apply_research_cycle(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        metrics = report.get('metrics', {}) if isinstance(report, dict) else {}
        directives = report.get('directives', []) if isinstance(report, dict) else []
        lead = directives[0].get('id') if directives else '-'
        print(
            f"[ResearchCycle] v34.2 applied | "
            f"phase={report.get('phase','-')} "
            f"closure={float(metrics.get('closure') or 0):.3f} "
            f"knowledge={float(metrics.get('knowledge') or 0):.3f} "
            f"trend={metrics.get('adaptive_trend','-')} "
            f"directives={len(directives)} lead={lead}"
        )
        return new_pop or observer_population, report
    except Exception as e:
        print(f'[ResearchCycle] failed; keeping paradigm-layer population: {e!r}')
        return observer_population, None


def refresh_research_plan_from_cycle(plan, cycle_state, generation):
    """Refresh in-run intent so the next population uses the latest cycle state."""
    if plan is None or not isinstance(cycle_state, dict) or research_cycle is None:
        return plan
    try:
        if not hasattr(research_cycle, 'apply_cycle_state_to_research_plan'):
            return plan
        updated = research_cycle.apply_cycle_state_to_research_plan(plan, cycle_state)
        save_research_bridge_status(updated)
        directives = cycle_state.get('directives', []) or []
        phase = cycle_state.get('phase', '-')
        print(
            f'[ResearchCycle] gen={generation} policy intent refreshed | '
            f'phase={phase} directives={len(directives)}'
        )
        return updated
    except Exception as e:
        print(f'[ResearchCycle] failed to refresh policy intent: {e!r}')
        return plan


def apply_observer_network_layer(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v28.0: build scientific institution network and annotate observer population safely."""
    if observer_network is None or not observer_population:
        return observer_population
    try:
        context = {}
        if isinstance(guided_info, dict):
            context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_network, 'apply_network_layer'):
            return observer_population
        new_pop, report = observer_network.apply_network_layer(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            context=context,
        )
        print(
            f"[ObserverNetwork] v28.0 applied | "
            f"institutions={report.get('institution_count',0)} "
            f"edges={report.get('edge_count',0)} "
            f"density={report.get('network_density',0):.3f} "
            f"health={report.get('network_health',0):.3f} "
            f"central={report.get('central_institution') or '-'} "
            f"mode={report.get('dominant_relation') or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ObserverNetwork] failed; keeping institution population: {e!r}')
        return observer_population

def apply_observer_ecosystem_dynamics(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v25.4: apply gentle ecosystem-level ordering/annotations over species dynamics."""
    if observer_ecosystem is None or not observer_population:
        return observer_population
    try:
        strategy_context = {}
        if isinstance(guided_info, dict):
            strategy_context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_ecosystem, 'apply_ecosystem_dynamics'):
            return observer_population
        new_pop, report = observer_ecosystem.apply_ecosystem_dynamics(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            strategy=strategy_context,
        )
        print(
            f"[ObserverEcosystem] v25.4 applied | "
            f"health={report.get('ecosystem_health',0):.3f} "
            f"dominant={report.get('dominant_species') or '-'} "
            f"species={report.get('species_count',0)} "
            f"keystone={','.join(report.get('keystone_species') or []) or '-'} "
            f"risk={','.join(report.get('at_risk_species') or []) or '-'}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[ObserverEcosystem] failed; keeping ecological-selection population: {e!r}')
        return observer_population


def record_observer_ecology_generation(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v25.3: observe observer species per generation. No selection/scoring effects yet."""
    if observer_ecology is None:
        return None
    try:
        strategy_context = {}
        if isinstance(guided_info, dict):
            strategy_context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        status = observer_ecology.record_generation_ecology(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            strategy=strategy_context,
        )
        print(
            f'[ObserverEcology] gen={gen} safe snapshot | '
            f'species={status.get("species_count",0)} observers={status.get("observer_count",0)} '
            f'dominant={status.get("dominant_species") or "-"} valid={status.get("valid_worlds",0)}'
        )
        return status
    except Exception as e:
        print(f'[ObserverEcology] generation snapshot failed: {e!r}')
        return None


def apply_observer_ecological_selection(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v25.3: apply conservative species-level selection pressure to observers.

    It returns a reordered/annotated observer population. It does not rename files,
    does not delete lineage history, and falls back to the original population on any error.
    """
    if observer_ecology is None or not observer_population:
        return observer_population
    try:
        strategy_context = {}
        if isinstance(guided_info, dict):
            strategy_context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_ecology, 'apply_ecological_selection'):
            return observer_population
        new_pop, report = observer_ecology.apply_ecological_selection(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            strategy=strategy_context,
        )
        strong = report.get('strongest_species') or {}
        weak = report.get('highest_extinction_risk') or {}
        print(
            f"[EcologicalSelection] v25.3 applied | "
            f"dominant={report.get('dominant_species') or '-'} "
            f"strong={strong.get('species','-')}:{strong.get('ecological_fitness',0)} "
            f"weak={weak.get('species','-')}:{weak.get('extinction_risk',0)} "
            f"species={report.get('species_count',0)} observers={report.get('observer_count',0)}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[EcologicalSelection] failed; keeping original observer population: {e!r}')
        return observer_population


def apply_research_bridge_generation_notes(plan, gen, clean_results):
    """v24.1 uses this hook to report guided selection ratios and per-generation state."""
    if not plan or not getattr(plan, 'active', False):
        return
    try:
        ratios = getattr(plan, 'ratios', {}) or {}
        print(
            f'[ResearchBridge] gen={gen} guided selection | '
            f'explore={ratios.get("explore", 0):.2f} '
            f'exploit={ratios.get("exploit", 0):.2f} '
            f'control={ratios.get("control", 0):.2f} '
            f'valid={len(clean_results)}'
        )
    except Exception as e:
        print(f'[ResearchBridge] generation note failed: {e!r}')


# ---------------- Adaptive Evolution v24.2 ----------------

def _clone_rule_with_new_id(rule, next_id):
    """Best-effort rule clone for negative-control / replication buckets."""
    try:
        d = base.rule_to_dict(rule)
        if isinstance(d, dict):
            d['rule_id'] = next_id
            return base.rule_from_dict(d)
    except Exception:
        pass
    return base.make_random_rule(next_id)


def _safe_ratio(plan, name, default=0.0):
    try:
        if not plan or not getattr(plan, 'active', False):
            return default
        ratios = getattr(plan, 'ratios', {}) or {}
        return max(0.0, float(ratios.get(name, default) or default))
    except Exception:
        return default


def _mutate_scalar(v, policy):
    """Tiny generic scalar mutator used only for local-neighbourhood candidates.

    It is intentionally conservative. If the rule schema rejects the result,
    caller falls back to random/crossover, so the search loop stays safe.
    """
    try:
        rate = float(getattr(policy, 'mutation_rate', 0.06) or 0.06)
        intensity = float(getattr(policy, 'mutation_intensity', 0.08) or 0.08)
    except Exception:
        rate, intensity = 0.06, 0.08

    if isinstance(v, bool):
        return (not v) if random.random() < min(0.30, rate) else v
    if isinstance(v, int) and not isinstance(v, bool):
        if random.random() >= rate:
            return v
        if v in (0, 1):
            return 1 - v
        span = max(1, int(round((abs(v) + 1) * intensity)))
        return int(v + random.randint(-span, span))
    if isinstance(v, float):
        if random.random() >= rate:
            return v
        step = (abs(v) + 1.0) * intensity
        nv = v + random.gauss(0.0, step)
        # A very wide clamp avoids infinities without assuming exact schema.
        return max(-1e6, min(1e6, float(nv)))
    return v


def _mutate_obj(obj, policy, depth=0):
    if depth > 8:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ('rule_id', 'id', 'name'):
                out[k] = v
            else:
                out[k] = _mutate_obj(v, policy, depth + 1)
        return out
    if isinstance(obj, list):
        out = [_mutate_obj(v, policy, depth + 1) for v in obj]
        # Occasionally perturb one extra position in arrays/lists.
        try:
            if out and random.random() < min(0.25, float(getattr(policy, 'mutation_rate', 0.06)) * 2):
                i = random.randrange(len(out))
                out[i] = _mutate_obj(out[i], policy, depth + 1)
        except Exception:
            pass
        return out
    if isinstance(obj, tuple):
        return tuple(_mutate_obj(list(obj), policy, depth + 1))
    return _mutate_scalar(obj, policy)


def _adaptive_mutate_rule(rule, next_id, policy):
    """Create a nearby rule candidate. Conservative and schema-safe."""
    try:
        d = base.rule_to_dict(rule)
        if isinstance(d, dict):
            d = _mutate_obj(d, policy)
            d['rule_id'] = next_id
            return base.rule_from_dict(d)
    except Exception:
        pass
    return base.make_random_rule(next_id)


def _build_policy(plan, elite_count):
    if evolution_policy is None:
        return None
    try:
        return evolution_policy.build_evolution_policy(
            plan,
            population_size=POPULATION,
            elite_count=elite_count,
            random_immigrants=RANDOM_IMMIGRANTS,
        )
    except Exception as e:
        print(f'[EvolutionPolicy] failed to build policy; using v24.1 selection: {e!r}')
        return None


def _append_guided_selection_log(plan, payload):
    try:
        if evolution_policy is not None and hasattr(evolution_policy, 'append_policy_log'):
            evolution_policy.append_policy_log(OUT_DIR, payload)
        if research_bridge is not None and hasattr(research_bridge, 'write_selection_status'):
            research_bridge.write_selection_status(OUT_DIR, payload)
        else:
            path = OUT_DIR / 'research_guided_selection_log.json'
            data = []
            if path.exists():
                try:
                    old = json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(old, list):
                        data = old
                except Exception:
                    data = []
            data.append(payload)
            data = data[-200:]
            atomic_write_json(path, data, indent=2)
    except Exception as e:
        print(f'[ResearchBridge] selection log failed: {e!r}')



def _reference_rule_payload(value):
    if not isinstance(value, dict):
        return None
    for key in ("rule", "rule_payload", "genome"):
        if isinstance(value.get(key), dict):
            return value[key]
    if "terms" in value and "rule_id" in value:
        return value
    return None


def _load_reference_control_pool():
    """Load qualified controls from the Analyzer registry and Atlas rule.json files."""
    global _reference_control_cache
    if _reference_control_cache is not None:
        return _reference_control_cache

    pool = []
    if not REFERENCE_CONTROL_REGISTRY_FILE.exists():
        _reference_control_cache = pool
        return pool

    try:
        registry = json.loads(REFERENCE_CONTROL_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ReferenceControls] registry read failed: {e!r}")
        _reference_control_cache = pool
        return pool

    qualified = {}
    for class_id, item in (registry.get("classes") or {}).items():
        if not isinstance(item, dict) or item.get("status") != "qualified":
            continue
        qualified[class_id] = [
            str(c.get("rule_id"))
            for c in item.get("candidates", [])
            if isinstance(c, dict) and c.get("qualified") and c.get("rule_id") is not None
        ]

    wanted = {rid for ids in qualified.values() for rid in ids}
    if not wanted:
        _reference_control_cache = pool
        return pool

    rule_files = {}
    try:
        for path in ATLAS_DIR.rglob("rule.json"):
            name = path.parent.name
            if not name.startswith("rule_"):
                continue
            parts = name.split("_")
            if len(parts) < 2:
                continue
            rid = parts[1]
            if rid in wanted and rid not in rule_files:
                rule_files[rid] = path
    except Exception as e:
        print(f"[ReferenceControls] Atlas scan failed: {e!r}")

    for class_id in ("extinction", "persistent_dynamics", "credible_emergence"):
        for rid in qualified.get(class_id, []):
            path = rule_files.get(rid)
            if path is None:
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = _reference_rule_payload(raw)
                if payload is None:
                    continue
                rule = base.rule_from_dict(payload)
                pool.append({
                    "class_id": class_id,
                    "rule_id": rid,
                    "source": str(path),
                    "rule": rule,
                })
            except Exception:
                continue

    _reference_control_cache = pool
    print(
        f"[ReferenceControls] loaded {len(pool)} qualified rule payload(s) "
        f"from {REFERENCE_CONTROL_REGISTRY_FILE}"
    )
    return pool


def _balanced_reference_controls(pool):
    by_class = {}
    for item in pool:
        by_class.setdefault(item.get("class_id", "unknown"), []).append(item)
    ordered = []
    while any(by_class.values()):
        for class_id in ("extinction", "persistent_dynamics", "credible_emergence"):
            items = by_class.get(class_id) or []
            if items:
                ordered.append(items.pop(0))
    return ordered


def _legacy_ratio_counts(plan, remaining):
    explore_r = _safe_ratio(plan, 'explore', 0.0)
    exploit_r = _safe_ratio(plan, 'exploit', 0.0)
    control_r = _safe_ratio(plan, 'control', 0.0)
    total_r = explore_r + exploit_r + control_r
    if total_r <= 0:
        return None
    explore_r, exploit_r, control_r = explore_r / total_r, exploit_r / total_r, control_r / total_r
    target_explore = int(round(remaining * explore_r))
    target_control = int(round(remaining * control_r))
    target_exploit = max(0, remaining - target_explore - target_control)
    target_explore = max(target_explore, min(RANDOM_IMMIGRANTS, remaining))
    overflow = max(0, target_explore + target_control + target_exploit - remaining)
    if overflow:
        target_exploit = max(0, target_exploit - overflow)
    return {
        'explore': target_explore,
        'exploit': target_exploit,
        'control': target_control,
        'local': 0,
        'ratios': {'explore': round(explore_r, 3), 'exploit': round(exploit_r, 3), 'control': round(control_r, 3)},
    }


def build_research_guided_population(plan, clean_results, elites, next_id):
    """Build next generation using Director policy.

    v24.2 keeps scoring/evaluation untouched, but turns Research Director intent into
    adaptive generation policy:
      exploit: crossover elite candidates
      local: mutate elite candidates in local neighbourhoods
      explore: independent random candidates
      control: qualified reference controls, with lower-tail fallback
    """
    if not plan or not getattr(plan, 'active', False):
        return None, next_id, None

    newpop = list(elites)
    remaining = max(0, POPULATION - len(newpop))
    if remaining <= 0:
        return newpop[:POPULATION], next_id, {'mode': 'research_guided_adaptive', 'made': {'elite': len(newpop)}}

    policy = _build_policy(plan, len(newpop))
    if policy is not None:
        strategy = None
        try:
            if hasattr(evolution_policy, 'write_policy_snapshot'):
                evolution_policy.write_policy_snapshot(OUT_DIR, policy)
            if hasattr(evolution_policy, 'build_evolution_strategy'):
                strategy = evolution_policy.build_evolution_strategy(policy)
            if strategy is not None and hasattr(evolution_policy, 'write_strategy_snapshot'):
                evolution_policy.write_strategy_snapshot(
                    OUT_DIR,
                    policy,
                    strategy,
                    extra={'phase': 'generation_build'},
                )
        except Exception as e:
            print(f'[EvolutionPolicy] failed to write policy/strategy snapshot: {e!r}')
        target_explore = int(getattr(policy, 'target_explore', 0))
        target_exploit = int(getattr(policy, 'target_exploit', 0))
        target_control = int(getattr(policy, 'target_control', 0))
        target_local = int(getattr(policy, 'target_local', 0))
        ratios = {
            'explore': round(float(getattr(policy, 'explore_ratio', 0.0)), 3),
            'exploit': round(float(getattr(policy, 'exploit_ratio', 0.0)), 3),
            'control': round(float(getattr(policy, 'control_ratio', 0.0)), 3),
            'local': round(float(getattr(policy, 'local_ratio', 0.0)), 3),
        }
    else:
        counts = _legacy_ratio_counts(plan, remaining)
        if counts is None:
            return None, next_id, None
        target_explore = counts['explore']
        target_exploit = counts['exploit']
        target_control = counts['control']
        target_local = counts['local']
        ratios = counts['ratios']

    # Rounding guard.
    overflow = max(0, target_explore + target_exploit + target_control + target_local - remaining)
    if overflow:
        target_exploit = max(0, target_exploit - overflow)
        overflow = max(0, target_explore + target_exploit + target_control + target_local - remaining)
        if overflow:
            target_explore = max(0, target_explore - overflow)

    made = {'elite': len(newpop), 'exploit': 0, 'local': 0, 'explore': 0, 'control': 0, 'fallback': 0}
    low_pool = [r for _, r, m in reversed(clean_results) if m.get('eval_error') is None]
    reference_pool = _balanced_reference_controls(_load_reference_control_pool())
    reference_index = 0
    made['reference_control'] = 0
    made['lower_tail_control'] = 0

    # Local neighbourhood: mutate around elites/best candidates.
    while len(newpop) < POPULATION and made['local'] < target_local:
        if elites:
            parent = random.choice(elites[:max(1, min(len(elites), ELITES))])
            if policy is not None:
                newpop.append(_adaptive_mutate_rule(parent, next_id, policy))
            else:
                newpop.append(_clone_rule_with_new_id(parent, next_id))
        else:
            newpop.append(base.make_random_rule(next_id)); made['fallback'] += 1
        next_id += 1
        made['local'] += 1

    # Exploit: recombine best-known candidates.
    while len(newpop) < POPULATION and made['exploit'] < target_exploit:
        if len(elites) >= 2:
            a, b = random.sample(elites, 2)
            child = base.crossover(a, b, next_id)
            # In exploratory phases, sometimes nudge the crossover child locally.
            try:
                if policy is not None and random.random() < min(0.35, float(getattr(policy, 'mutation_rate', 0.06))):
                    child = _adaptive_mutate_rule(child, next_id, policy)
            except Exception:
                pass
            newpop.append(child)
        elif elites:
            newpop.append(_clone_rule_with_new_id(elites[0], next_id))
        else:
            newpop.append(base.make_random_rule(next_id)); made['fallback'] += 1
        next_id += 1
        made['exploit'] += 1

    # Control: use qualified reference controls first; lower-tail is fallback only.
    while len(newpop) < POPULATION and made['control'] < target_control:
        if reference_pool:
            item = reference_pool[reference_index % len(reference_pool)]
            reference_index += 1
            newpop.append(_clone_rule_with_new_id(item["rule"], next_id))
            made['reference_control'] += 1
        elif low_pool:
            r = random.choice(low_pool[:max(2, min(len(low_pool), POPULATION // 3))])
            newpop.append(_clone_rule_with_new_id(r, next_id))
            made['lower_tail_control'] += 1
        else:
            newpop.append(base.make_random_rule(next_id))
            made['fallback'] += 1
        next_id += 1
        made['control'] += 1

    # Explore: fresh independent rules.
    while len(newpop) < POPULATION and made['explore'] < target_explore:
        newpop.append(base.make_random_rule(next_id))
        next_id += 1
        made['explore'] += 1

    # Fill any rounding gaps with local/exploit/random, depending on policy.
    while len(newpop) < POPULATION:
        if policy is not None and elites and random.random() < 0.30:
            newpop.append(_adaptive_mutate_rule(random.choice(elites), next_id, policy))
            made['local'] += 1
        elif len(elites) >= 2:
            a, b = random.sample(elites, 2)
            newpop.append(base.crossover(a, b, next_id))
            made['exploit'] += 1
        else:
            newpop.append(base.make_random_rule(next_id))
            made['fallback'] += 1
        next_id += 1

    info = {
        'mode': 'research_guided_adaptive' if policy is not None else 'research_guided_selection',
        'bridge_version': getattr(plan, 'version', 'unknown'),
        'policy_version': getattr(policy, 'version', None) if policy is not None else None,
        'stage': getattr(plan, 'stage', 'unknown'),
        'maturity': getattr(plan, 'maturity', 0.0),
        'risk': getattr(plan, 'risk', 0.0),
        'trend': getattr(plan, 'trend', 'unknown'),
        'ratios': ratios,
        'targets': {'explore': target_explore, 'exploit': target_exploit, 'control': target_control, 'local': target_local},
        'made': made,
        'population': len(newpop),
        'reference_controls': {
            'registry': str(REFERENCE_CONTROL_REGISTRY_FILE),
            'available': len(reference_pool),
            'used': made.get('reference_control', 0),
            'fallback_used': made.get('lower_tail_control', 0),
        },
    }
    if policy is not None:
        info['policy'] = policy.to_dict()
        try:
            if 'strategy' in locals() and strategy is not None:
                info['strategy'] = strategy.to_dict()
        except Exception:
            pass
    return newpop, next_id, info



def apply_observer_ecological_selection(gen, score_mode, observer_population, clean_results, guided_info=None):
    """v25.3: apply conservative species-level selection pressure to observers.

    It returns a reordered/annotated observer population. It does not rename files,
    does not delete lineage history, and falls back to the original population on any error.
    """
    if observer_ecology is None or not observer_population:
        return observer_population
    try:
        strategy_context = {}
        if isinstance(guided_info, dict):
            strategy_context = {
                'mode': guided_info.get('mode'),
                'ratios': guided_info.get('ratios'),
                'targets': guided_info.get('targets'),
                'made': guided_info.get('made'),
                'strategy': guided_info.get('strategy'),
                'search_run_id': SEARCH_RUN_ID,
            }
        if not hasattr(observer_ecology, 'apply_ecological_selection'):
            return observer_population
        new_pop, report = observer_ecology.apply_ecological_selection(
            OUT_DIR,
            generation=gen,
            score_mode=score_mode,
            observer_population=observer_population,
            clean_results=clean_results,
            strategy=strategy_context,
        )
        strong = report.get('strongest_species') or {}
        weak = report.get('highest_extinction_risk') or {}
        print(
            f"[EcologicalSelection] v25.3 applied | "
            f"dominant={report.get('dominant_species') or '-'} "
            f"strong={strong.get('species','-')}:{strong.get('ecological_fitness',0)} "
            f"weak={weak.get('species','-')}:{weak.get('extinction_risk',0)} "
            f"species={report.get('species_count',0)} observers={report.get('observer_count',0)}"
        )
        return new_pop or observer_population
    except Exception as e:
        print(f'[EcologicalSelection] failed; keeping original observer population: {e!r}')
        return observer_population


def apply_research_bridge_generation_notes(plan, gen, clean_results):
    """v24.2 reports Director ratios plus adaptive policy state."""
    if not plan or not getattr(plan, 'active', False):
        return
    try:
        ratios = getattr(plan, 'ratios', {}) or {}
        policy = _build_policy(plan, elite_count=max(2, ELITES))
        if policy is not None:
            strategy = None
            try:
                if hasattr(evolution_policy, 'build_evolution_strategy'):
                    strategy = evolution_policy.build_evolution_strategy(policy)
            except Exception:
                strategy = None
            print(
                f'[EvolutionPolicy] gen={gen} adaptive | '
                f'mut={getattr(policy,"mutation_rate",0):.3f} '
                f'int={getattr(policy,"mutation_intensity",0):.3f} '
                f'local={getattr(policy,"local_ratio",0):.2f} '
                f'targets x/e/c/l={getattr(policy,"target_explore",0)}/{getattr(policy,"target_exploit",0)}/{getattr(policy,"target_control",0)}/{getattr(policy,"target_local",0)} '
                f'valid={len(clean_results)}'
            )
            if strategy is not None:
                print(
                    f'[EvolutionStrategy] gen={gen} {strategy.name} | '
                    f'goal={strategy.goal} | expected_gain={strategy.expected_gain}'
                )
        else:
            print(
                f'[ResearchBridge] gen={gen} guided selection | '
                f'explore={ratios.get("explore", 0):.2f} '
                f'exploit={ratios.get("exploit", 0):.2f} '
                f'control={ratios.get("control", 0):.2f} '
                f'valid={len(clean_results)}'
            )
    except Exception as e:
        print(f'[ResearchBridge] generation note failed: {e!r}')

def detailed_console_line(i, rule, score, metrics):
    if metrics.get('eval_error') is not None:
        print(f'  [{i:03d}/{POPULATION}] rule={rule.rule_id:05d} CRASHED score={score:8.1f} error={metrics.get("eval_error")}')
        return

    print(
        f'  [{i:03d}/{POPULATION}] rule={rule.rule_id:05d} score={score:8.3f} '
        f'active={metrics["active"]:.3f} edge={metrics["edge"]:.3f} '
        f'b_act={metrics["boundary_activity"]:.5f} islands={metrics["islands"]} '
        f'nested={metrics.get("nested_score_raw",0):.3f} life={metrics.get("ms_local_life",0):.3f} '
        f'flow={metrics.get("ms_flow",0):.4f} rot={metrics.get("ms_rotation_flow",0):.4f} '
        f'ent={metrics.get("entity_count",0)} trk={metrics.get("persistent_tracks",0)} '
        f'objQ={metrics.get("best_entity_quality",0):.3f} reg={metrics.get("best_region_score",0):.3f} '
        f'rc={metrics.get("region_count",0)} nov={metrics.get("novelty_behavior",0):.3f} '
        f'div={metrics.get("in_generation_diversity",0):.3f} mac={metrics.get("macro_scaffold",0):.1f} '
        f'mem={metrics.get("memory_trace_score",0):.1f} cr={metrics.get("cosmic_recovery",0):.3f} '
        f'xtal={metrics.get("crystal_order",0):.2f} def={metrics.get("defect_density",0):.3f} qp={metrics.get("quasi_particle_score",0):.2f} '
        f'orgL={metrics.get("organism_lifetime",0)} orgP={metrics.get("organism_peak_largest",0)} orgB={metrics.get("organism_bonus",0):.1f} '
        f'info={metrics.get("information_survival",0):.2f} id={metrics.get("identity_persistence",0):.2f} leg={metrics.get("legacy_score",0):.2f} iB={metrics.get("information_bonus",0):.1f} '
        f'cache={int(bool(metrics.get("crystal_cache_hit", False)))} '
        f'hum={metrics.get("human_bonus",0):.0f} '
        f'pen={metrics.get("degeneracy_penalty",0):.1f}/{metrics.get("degeneracy_penalty_raw",0):.1f} '
        f'obs={metrics.get("observer_id","-")}:{metrics.get("observer_score",0):.1f}'
    )
    note = metrics.get('observer_note', '')
    if metrics.get('persistent_entity_score', 0.0) > 0.20 or metrics.get('best_entity_quality', 0.0) > 0.25 or metrics.get('best_region_score', 0.0) > 0.18 or metrics.get('best_hotspot_score', 0.0) > 0.20:
        print(f'      observer: {note}')


def run_evolution(score_mode='observer_niches', resume=False, search_config=None):
    global MAIN_PID, PAUSE_REQUESTED
    MAIN_PID = os.getpid()
    PAUSE_REQUESTED = False
    os.environ['UNIVERSE_SEARCH_MAIN_PID'] = str(MAIN_PID)
    configure_base_paths()
    # Must precede caches, Atlas directories, IDs and checkpoints. A dependency
    # failure is an infrastructure stop and must leave no scientific mutation.
    base.require_field_backend()
    load_crystal_cache()
    load_organism_cache()
    load_information_cache()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    emit_search_runtime_event(
        'process_started',
        entrypoint='Universe_Search/universe_search_v34_closed_research_cycle.py',
        population=POPULATION,
        generations=GENERATIONS,
        score_mode=score_mode,
    )

    research_plan = load_research_bridge_plan()
    if research_cycle is not None and hasattr(research_cycle, 'apply_cycle_to_research_plan'):
        try:
            research_plan = research_cycle.apply_cycle_to_research_plan(research_plan, OUT_DIR)
            cycle_state = getattr(research_plan, 'cycle_state', {}) or {}
            directives = cycle_state.get('directive_ids', []) or []
            print(
                f"[ResearchCycle] v34.1 pre-policy intent | "
                f"phase={cycle_state.get('phase','-')} directives={len(directives)}"
            )
        except Exception as e:
            print(f'[ResearchCycle] pre-policy adjustment failed: {e!r}')

    if search_job_loader is not None and search_config is not None:
        try:
            research_plan = search_job_loader.apply_config_to_research_plan(
                research_plan,
                search_config,
            )
            print(
                f'[SearchMode] mode={search_config.search_mode} '
                f'job={search_config.job_id or "-"} '
                f'target={search_config.target_regime or "-"} '
                f'seeds={len(search_config.seed_rules)} '
                f'constraints={len(search_config.constraints)}'
            )
            for warning in search_config.errors:
                print(f'[SearchMode] warning: {warning}')
        except Exception as e:
            print(f'[SearchMode] failed to apply config; continuing safely: {e!r}')

    save_research_bridge_status(research_plan)
    announce_and_save_initial_evolution_policy(research_plan)

    favorites = base.load_human_favorites()
    favorite_signatures = {base.rule_signature(r) for r in favorites}

    state = (
        load_checkpoint(score_mode, search_config)
        if resume
        else None
    )
    if resume and state is None:
        print(
            '[Search] resume refused: no compatible checkpoint for the '
            'selected score mode and Search configuration.'
        )
        return
    if state:
        print(f'Resumed from checkpoint at generation {state["start_gen"]}')
        population = state['population']
        observer_population = state['observer_population']
        next_id = state['next_id']
        next_observer_id = state['next_observer_id']
        best_ever = state['best_ever']
        novelty_archive = collections.deque((state['novelty_archive'] or [])[-NOVELTY_ARCHIVE_MAXLEN:], maxlen=NOVELTY_ARCHIVE_MAXLEN)
        diversity_skeleton = state.get('diversity_skeleton') or load_diversity_skeleton()
        start_gen = state['start_gen']
    else:
        observer_population = base.make_observer_population() if score_mode in ('observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches') else []
        next_observer_id = OBSERVER_COUNT
        reserve_count = POPULATION * (GENERATIONS + 2) + 256
        run_id_start, run_id_end = reserve_rule_id_range(reserve_count)
        population = [base.make_random_rule(run_id_start + i) for i in range(POPULATION)]
        next_id = run_id_start + POPULATION
        seed_provenance = []
        seed_payloads = []
        if (
            search_job_loader is not None
            and search_config is not None
            and search_config.seed_rules
        ):
            try:
                seed_payloads, seed_provenance = (
                    search_job_loader.load_seed_rule_payloads(
                        ATLAS_DIR,
                        search_config.seed_rules,
                    )
                )
                max_seed_slots = min(
                    len(seed_payloads),
                    max(1, POPULATION // 3),
                )
                for j, payload in enumerate(seed_payloads[:max_seed_slots]):
                    parent = base.rule_from_dict(payload)
                    # Seed rules are controls/parents, not new canonical rules.
                    # Preserve their Atlas identity until mutation/crossover
                    # actually changes the genome.
                    population[j] = parent
                print(
                    f'[SearchMode] loaded {max_seed_slots}/'
                    f'{len(search_config.seed_rules)} Atlas seed rule(s)'
                )
            except Exception as e:
                print(f'[SearchMode] seed loading failed safely: {e!r}')

        favorite_offset = min(len(seed_payloads), max(1, POPULATION // 3))
        if favorites:
            print(f'Loaded {len(favorites)} human favorite seed rules')
            room = max(0, POPULATION // 4)
            for j, fav in enumerate(favorites[:room]):
                idx = favorite_offset + j
                if idx >= POPULATION:
                    break
                # A favorite is an existing genome. Preserve its identity;
                # descendants receive fresh IDs through crossover/mutation.
                population[idx] = fav

        if search_job_loader is not None and search_config is not None:
            try:
                manifest = search_job_loader.write_search_mode_manifest(
                    RUN_HISTORY_DIR,
                    search_config,
                    score_mode=score_mode,
                    search_run_id=SEARCH_RUN_ID,
                    seed_provenance=seed_provenance,
                )
                print(f'[SearchMode] manifest saved: {manifest}')
            except Exception as e:
                print(f'[SearchMode] manifest write failed: {e!r}')

        best_ever = None
        novelty_archive = collections.deque(maxlen=NOVELTY_ARCHIVE_MAXLEN)
        diversity_skeleton = load_diversity_skeleton()
        start_gen = 1

    initialize_observer_ecology_foundation(observer_population)
    initialize_observer_ecosystem(observer_population)
    initialize_observer_civilization(observer_population)
    initialize_observer_institutions(observer_population)
    initialize_observer_network(observer_population)
    initialize_network_dynamics(observer_population)
    initialize_discovery_engine(observer_population)
    initialize_research_programs(observer_population)
    initialize_research_teams(observer_population)
    initialize_experiment_engine(observer_population)
    initialize_theory_engine(observer_population)
    initialize_paradigm_engine(observer_population)
    initialize_research_cycle(observer_population)

    target_constraints = {}
    target_scoring_active = False
    target_generation_summaries = []
    if (
        search_config is not None
        and getattr(search_config, 'search_mode', 'ordinary')
        in ('cohort_target', 'counterexample')
        and getattr(search_config, 'constraints', None)
    ):
        target_constraints = dict(search_config.constraints)
        target_scoring_active = target_scoring is not None
        print(
            f'[TargetScoring] active={target_scoring_active} '
            f'mode={search_config.search_mode} '
            f'constraints={target_constraints}'
        )

    for gen in range(start_gen, GENERATIONS + 1):
        gen_t0 = time.time()
        print(f'Generation {gen}/{GENERATIONS} mode={score_mode} [{now_s()}]')
        guided_info = None
        internal_mode = 'hierarchical_novelty' if score_mode in ('hierarchical_novelty', 'observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches') else score_mode

        try:
            raw = evaluate_population(
                population,
                internal_mode,
                workers=WORKERS,
            )
            if PAUSE_REQUESTED:
                raise SearchPauseRequested()
        except SearchPauseRequested:
            # The partial result set is deliberately discarded. Advancing a
            # population from whichever rules happened to finish first would
            # introduce runtime-dependent selection bias.
            save_crystal_cache()
            save_organism_cache()
            save_information_cache()
            save_checkpoint(
                gen - 1,
                score_mode,
                population,
                observer_population,
                next_id,
                next_observer_id,
                best_ever,
                novelty_archive,
                diversity_skeleton,
                search_config,
            )
            print(
                f'[Search] paused safely before completing generation {gen}. '
                'Partial evaluations were discarded; Resume will restart this '
                'generation from the same population.'
            )
            break

        results = []
        generation_vectors = []
        for idx, raw_score, rule_dict, metrics in raw:
            rule = base.rule_from_dict(rule_dict)
            score = raw_score

            if metrics.get('eval_error') is not None:
                metrics.update(empty_crystal_metrics('skipped because eval_error'))
                metrics.update(empty_organism_metrics('skipped because eval_error'))
                metrics.update(empty_information_metrics('skipped because eval_error'))
                metrics['observer_score'] = -1e9
                metrics['observer_id'] = -1
                metrics['observer_note'] = f'eval failed: {metrics.get("eval_error")}'
                results.append((score, rule, metrics))
                detailed_console_line(idx + 1, rule, score, metrics)
                continue

            if base.rule_signature(rule) in favorite_signatures:
                metrics['human_bonus'] = 28.0
                score += 28.0
            else:
                metrics['human_bonus'] = 0.0

            merge_crystal_into_main_cache(rule, metrics)
            merge_organism_into_main_cache(rule, metrics)
            merge_information_into_main_cache(rule, metrics)

            vec = base.metric_feature_vector(metrics)
            novelty_score = base.novelty_from_archive(vec, list(novelty_archive))
            in_gen_diversity = base.novelty_from_archive(vec, generation_vectors)
            generation_vectors.append(vec)
            metrics['novelty_behavior'] = novelty_score
            metrics['in_generation_diversity'] = in_gen_diversity

            if score_mode in ('observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches'):
                obs_scores = [(base.observer_score(o, metrics), o) for o in observer_population]
                obs_scores.sort(key=lambda x: x[0], reverse=True)
                best_obs_score, best_obs = obs_scores[0]
                metrics['observer_score'] = best_obs_score
                metrics['observer_id'] = best_obs.get('id', -1)
                metrics['observer_archetype'] = best_obs.get('archetype', 'unknown')
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.52 + best_obs_score + novelty_score * (base.NOVELTY_BONUS_BASE * 0.55) + in_gen_diversity * (base.DIVERSITY_BONUS_BASE * gen_pressure)
            elif score_mode in ('hierarchical_novelty', 'adaptive_observer', 'cosmic_curator'):
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.70 + novelty_score * base.NOVELTY_BONUS_BASE + in_gen_diversity * (base.DIVERSITY_BONUS_BASE * gen_pressure) + min(metrics.get('macro_scaffold',0), 120) * 0.12
            elif score_mode == 'novelty':
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.62 + novelty_score * 58.0 + in_gen_diversity * (34.0 * gen_pressure)

            if CRYSTAL_DEFECT_ANALYSIS:
                metrics['crystal_defect_bonus'] = metrics.get('quasi_particle_score', 0.0) * CRYSTAL_DEFECT_BONUS
                score += metrics['crystal_defect_bonus']

            if ORGANISM_ANALYSIS:
                score += metrics.get('organism_bonus', 0.0)

            if INFORMATION_ANALYSIS:
                score += metrics.get('information_bonus', 0.0)

            if target_scoring_active:
                score, target_result = target_scoring.apply_target_score(
                    score,
                    metrics,
                    target_constraints,
                )
            else:
                metrics['target_match'] = False
                metrics['target_coverage'] = 0.0
                metrics['target_distance'] = None
                metrics['target_bonus'] = 0.0

            if score > -20 or novelty_score > 0.38 or in_gen_diversity > 0.55:
                novelty_archive.append(vec)
            results.append((score, rule, metrics))
            detailed_console_line(idx + 1, rule, score, metrics)

        results.sort(key=lambda x: x[0], reverse=True)
        results = canonicalize_evaluated_results(results)
        clean_results = [r for r in results if r[2].get('eval_error') is None]
        if not clean_results:
            print('  all rules failed this generation; saving checkpoint and stopping safely.')
            save_crystal_cache()
            save_organism_cache()
            save_information_cache()
            save_checkpoint(gen, score_mode, population, observer_population, next_id, next_observer_id, best_ever, novelty_archive, diversity_skeleton, search_config)
            break

        if target_scoring_active:
            target_summary = target_scoring.summarize_generation(clean_results)
            target_summary['generation'] = gen
            target_summary['search_mode'] = search_config.search_mode
            target_summary['search_job_id'] = search_config.job_id
            target_summary['target_regime'] = search_config.target_regime
            target_summary['constraints'] = target_constraints
            atomic_write_json(
                RUN_HISTORY_DIR / f'target_scoring_generation_{gen:02d}.json',
                target_summary,
                indent=2,
            )
            target_generation_summaries.append(target_summary)
            best_target = (target_summary.get('best_target_candidates') or [{}])[0]
            print(
                f"[TargetScoring] gen={gen} "
                f"exact={target_summary.get('exact_matches',0)} "
                f"best_rule={best_target.get('rule_id','-')} "
                f"distance={best_target.get('target_distance','-')} "
                f"coverage={best_target.get('target_coverage','-')} "
                f"bonus={best_target.get('target_bonus','-')}"
            )

        if score_mode in ('coevolution', 'observer_stability', 'observer_niches'):
            observer_population, next_observer_id, truth_by_sig = base.evolve_observers_with_posttest(observer_population, clean_results, next_observer_id, gen)
            for _, r0, m0 in clean_results:
                sig = base.rule_signature(r0)
                if sig in truth_by_sig:
                    m0['post_test_truth'] = truth_by_sig[sig]
            base.save_observers(observer_population)
            lead = observer_population[0]
            print(f'  coevolution observer champion: id={lead.get("id")} arch={lead.get("archetype")} fitness={lead.get("fitness",0):.2f}')
            if score_mode == 'observer_niches':
                base.write_niche_summary(gen, score_mode, clean_results)
        elif score_mode == 'observer_evolution':
            top_metrics = [m for _, _, m in clean_results[:KEEP_TOP]]
            observer_population, next_observer_id = base.evolve_observers(observer_population, top_metrics, next_observer_id)
            base.save_observers(observer_population)

        observer_population = apply_observer_ecological_selection(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_observer_ecosystem_dynamics(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_observer_civilization_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_observer_institution_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_observer_network_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_network_dynamics_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_discovery_engine_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_research_programs_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_research_teams_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_experiment_engine_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_theory_engine_layer(gen, score_mode, observer_population, clean_results, guided_info)
        observer_population = apply_paradigm_engine_layer(gen, score_mode, observer_population, clean_results, guided_info)

        # First state pass captures Search + Discovery + Experiment outcomes.
        scientific_state = build_generation_scientific_state(
            gen,
            score_mode,
            clean_results,
            best_ever,
            guided_info=guided_info,
            cycle_state=None,
            persist=False,
        )

        observer_population, cycle_state = apply_research_cycle_layer(
            gen,
            score_mode,
            observer_population,
            clean_results,
            guided_info,
            scientific_state=scientific_state,
        )
        research_plan = refresh_research_plan_from_cycle(
            research_plan,
            cycle_state,
            gen,
        )

        if not clean_results:
            print('No valid worlds in this generation.')
            continue

        gen_best = clean_results[0]
        if best_ever is None or gen_best[0] > best_ever[0]:
            best_ever = gen_best

        # Final state pass adds best-ever and the cycle response.
        scientific_state = build_generation_scientific_state(
            gen,
            score_mode,
            clean_results,
            best_ever,
            guided_info=guided_info,
            cycle_state=cycle_state,
        )
        if scientific_state is not None:
            try:
                research_plan.scientific_state = scientific_state.to_dict()
            except Exception:
                pass

        payload = [{'score': s, 'rule': base.rule_to_dict(r), 'metrics': m} for s, r, m in clean_results[:KEEP_TOP]]
        atomic_write_json(OUT_DIR / f'generation_{gen:02d}_{score_mode}.json', payload, indent=2)
        atomic_write_json(OUT_DIR / f'best_{score_mode}.json', {'score': best_ever[0], 'rule': base.rule_to_dict(best_ever[1]), 'metrics': best_ever[2]}, indent=2)
        # Keep immutable run-scoped copies; root mirrors remain for legacy tools.
        atomic_write_json(RUN_HISTORY_DIR / f'generation_{gen:02d}_{score_mode}.json', payload, indent=2)
        atomic_write_json(RUN_HISTORY_DIR / f'best_{score_mode}.json', {'score': best_ever[0], 'rule': base.rule_to_dict(best_ever[1]), 'metrics': best_ever[2]}, indent=2)
        emit_search_runtime_event(
            'generation_committed',
            generation=gen,
            results=len(payload),
            artifact=(RUN_HISTORY_DIR / f'generation_{gen:02d}_{score_mode}.json').relative_to(PROJECT_ROOT).as_posix(),
        )

        add_to_atlas(gen, score_mode, select_atlas_items(clean_results, score_mode))
        diversity_skeleton = update_diversity_skeleton(diversity_skeleton, clean_results, gen)
        save_crystal_cache()
        save_organism_cache()
        save_information_cache()
        print(f'  valid results: {len(clean_results)}/{len(results)}')
        apply_research_bridge_generation_notes(research_plan, gen, clean_results)
        print(f'  diversity skeleton: {len(diversity_skeleton)} reps -> {DIVERSITY_SKELETON_FILE}')

        print(f'BEST gen={gen}: rule={gen_best[1].rule_id:05d} score={gen_best[0]:.3f} | best ever={best_ever[1].rule_id:05d} {best_ever[0]:.3f}')
        print(f'  best observer: {gen_best[2].get("observer_note", "no note")}')
        print(f'  generation time: {(time.time() - gen_t0)/60:.1f} min')

        if score_mode == 'observer_niches':
            elite_rules = []
            seen_sigs = set()
            for _, r, _ in clean_results[:max(4, ELITES//2)]:
                sig = base.rule_signature(r)
                if sig not in seen_sigs:
                    elite_rules.append(r); seen_sigs.add(sig)
            for _, (_, r, _) in base.niche_champions(clean_results):
                sig = base.rule_signature(r)
                if sig not in seen_sigs:
                    elite_rules.append(r); seen_sigs.add(sig)
            elites = elite_rules[:max(2, ELITES)]
        else:
            elites = [r for _, r, _ in clean_results[:ELITES]]

        guided_pop, guided_next_id, guided_info = build_research_guided_population(research_plan, clean_results, elites, next_id)
        if guided_pop is not None:
            population = guided_pop
            next_id = guided_next_id
            guided_info['generation'] = gen
            if scientific_state is not None:
                guided_info['scientific_state'] = scientific_state.to_dict()
                guided_info['generation_summary'] = {
                    'best_rule_id': scientific_state.best_rule_id,
                    'best_score': scientific_state.best_score,
                    'score_gain': scientific_state.score_gain,
                    'mean_novelty': scientific_state.mean_novelty,
                    'novelty_gain': scientific_state.novelty_gain,
                    'mean_diversity': scientific_state.mean_diversity,
                    'diversity_gain': scientific_state.diversity_gain,
                    'new_discoveries': scientific_state.new_discoveries,
                    'new_trials': scientific_state.new_trials,
                    'positive_trials': scientific_state.positive_trials,
                    'adaptive_trend': scientific_state.adaptive_trend,
                    'stagnation_generations': scientific_state.stagnation_generations,
                    'progress_score': scientific_state.progress_score,
                    'signals': scientific_state.signals,
                }
            _append_guided_selection_log(research_plan, guided_info)
            made = guided_info.get('made', {})
            ratios = guided_info.get('ratios', {})
            strat = (guided_info.get('strategy') or {}).get('name', '-') if isinstance(guided_info, dict) else '-'
            print(
                f"[EvolutionPolicy] v28.0 network strategy applied | "
                f"strategy={strat} elite={made.get('elite',0)} exploit={made.get('exploit',0)} "
                f"local={made.get('local',0)} explore={made.get('explore',0)} control={made.get('control',0)} "
                f"ref={made.get('reference_control',0)} tail={made.get('lower_tail_control',0)} fallback={made.get('fallback',0)} | "
                f"ratios e/x/c={ratios.get('explore',0):.2f}/{ratios.get('exploit',0):.2f}/{ratios.get('control',0):.2f}"
            )
        else:
            newpop = elites[:]
            while len(newpop) < POPULATION - RANDOM_IMMIGRANTS:
                if len(elites) < 2:
                    newpop.append(base.make_random_rule(next_id))
                else:
                    a, b = random.sample(elites, 2)
                    newpop.append(base.crossover(a, b, next_id))
                next_id += 1
            while len(newpop) < POPULATION:
                newpop.append(base.make_random_rule(next_id)); next_id += 1
            population = newpop

        record_observer_ecology_generation(gen, score_mode, observer_population, clean_results, guided_info if 'guided_info' in locals() else None)

        save_checkpoint(gen, score_mode, population, observer_population, next_id, next_observer_id, best_ever, novelty_archive, diversity_skeleton, search_config)

        if PAUSE_REQUESTED:
            print(
                f'[Search] paused safely after generation {gen}. '
                'Use the resume command to continue from this checkpoint.'
            )
            break

    save_crystal_cache()
    save_organism_cache()
    save_information_cache()

    if PAUSE_REQUESTED:
        print('Search paused with checkpoint preserved.')
    else:
        print('Search complete.')
        emit_search_runtime_event('search_complete')
        if target_scoring_active and target_generation_summaries:
            target_outcome = target_scoring.finalize_search_outcome(
                target_generation_summaries,
                constraints=target_constraints,
                search_mode=getattr(search_config, 'search_mode', None),
                search_job_id=getattr(search_config, 'job_id', None),
                target_regime=getattr(search_config, 'target_regime', None),
                runtime_id=os.environ.get('ARCHON_SEARCH_RUNTIME_ID'),
                dispatch_id=os.environ.get('ARCHON_SEARCH_DISPATCH_ID'),
                search_run_id=SEARCH_RUN_ID,
                expected_generations=GENERATIONS,
            )
            outcome_env = os.environ.get('ARCHON_SEARCH_OUTCOME_PATH')
            outcome_path = (
                Path(outcome_env).expanduser().resolve()
                if outcome_env
                else RUN_HISTORY_DIR / 'search_target_outcome.json'
            )
            atomic_write_json(outcome_path, target_outcome, indent=2)
            atomic_write_json(
                RUN_HISTORY_DIR / 'search_target_outcome.json',
                target_outcome,
                indent=2,
            )
            print(
                '[TargetScoring] final='
                f"{target_outcome.get('scientific_status')} "
                f"reason={target_outcome.get('reason')} "
                f"exact={target_outcome.get('exact_matches')} "
                f"full_coverage={target_outcome.get('full_coverage_candidate_slots')}/"
                f"{target_outcome.get('evaluated_candidate_slots')}"
            )
            print(f'[TargetScoring] outcome saved: {outcome_path}')
    if best_ever is not None:
        print(f'Best rule: {best_ever[1].rule_id:05d}, score={best_ever[0]:.3f}')
    else:
        print('No valid best rule was found.')
    print(f'Atlas index: {ATLAS_INDEX_FILE}')


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Universe Search v34.5 Scientific Search + Prompt Pause',
    )
    parser.add_argument(
        'command',
        nargs='?',
        default='help',
        choices=['evolve', 'search', 'resume', 'view', 'help'],
    )
    parser.add_argument(
        'score_mode',
        nargs='?',
        default='observer_niches',
    )
    parser.add_argument(
        '--search-mode',
        choices=[
            'ordinary',
            'diversity',
            'cohort_target',
            'counterexample',
            'local_around_rule',
        ],
        default='ordinary',
        help='High-level Search orchestration mode.',
    )
    parser.add_argument(
        '--experiment-plan',
        default=None,
        help='Path to Analyzer experiment_plan.json.',
    )
    parser.add_argument(
        '--search-job',
        default=None,
        help='Exact search job ID from experiment_plan.json.',
    )
    parser.add_argument(
        '--target-regime',
        default=None,
        help='Select the first job matching this target regime.',
    )
    parser.add_argument(
        '--seed-rule',
        action='append',
        default=[],
        help='Atlas rule ID to seed. May be repeated.',
    )
    args = parser.parse_args()

    mode = args.command
    score_mode = args.score_mode.lower()

    if score_mode not in base.SCORE_MODES:
        print(
            f"Unknown score mode: {score_mode!r}. "
            "Falling back to 'observer_niches'."
        )
        score_mode = 'observer_niches'

    search_config = None
    if search_job_loader is not None:
        search_config = search_job_loader.load_search_mode_config(
            project_root=PROJECT_ROOT,
            search_mode=args.search_mode,
            experiment_plan=(
                Path(args.experiment_plan)
                if args.experiment_plan
                else None
            ),
            job_id=args.search_job,
            target_regime=args.target_regime,
            seed_rules=args.seed_rule,
            requested_score_mode=score_mode,
        )
        if (
            mode in ('evolve', 'search', 'resume')
            and search_config is not None
            and getattr(search_config, 'errors', None)
        ):
            for error in search_config.errors:
                print(f'[SearchMode] configuration error: {error}')
            print('[SearchMode] launch refused: fix the configuration above.')
            return 2

    if mode in ('evolve', 'search', 'resume'):
        try:
            base.require_field_backend()
        except base.FieldBackendError as exc:
            print('[DEPENDENCY_ERROR] Universe Search evaluator is unavailable.')
            print(f'Python runtime: {sys.executable}')
            print(str(exc))
            return 2

    if mode in ('evolve', 'search'):
        try:
            run_evolution(
                score_mode,
                resume=False,
                search_config=search_config,
            )
        except base.FieldBackendError as exc:
            print('[DEPENDENCY_ERROR] Universe Search evaluator is unavailable.')
            print(f'Python runtime: {sys.executable}')
            print(str(exc))
            return 2
        finally:
            save_crystal_cache()
            save_organism_cache()
            save_information_cache()

    elif mode == 'resume':
        try:
            run_evolution(
                score_mode,
                resume=True,
                search_config=search_config,
            )
        except base.FieldBackendError as exc:
            print('[DEPENDENCY_ERROR] Universe Search evaluator is unavailable.')
            print(f'Python runtime: {sys.executable}')
            print(str(exc))
            return 2
        finally:
            save_crystal_cache()
            save_organism_cache()
            save_information_cache()

    elif mode == 'view':
        configure_base_paths()
        if base.tk is None:
            print('tkinter is not available. Viewer disabled.')
            return
        root = base.tk.Tk()
        base.Viewer(root)
        root.mainloop()

    else:
        print()
        print('Universe Search v34.2 Adaptive Scientific State')
        print('=' * 58)
        print('Usage:')
        print('  python universe_search.py evolve observer_niches')
        print(
            '  python universe_search.py evolve observer_niches '
            '--search-mode diversity'
        )
        print(
            '  python universe_search.py evolve observer_niches '
            '--search-mode cohort_target '
            '--target-regime persistent_under_scored'
        )
        print(
            '  python universe_search.py evolve observer_niches '
            '--search-mode local_around_rule --seed-rule 00251'
        )
        print()
        print('Search modes:')
        print('  ordinary          Current legacy-compatible Search.')
        print('  diversity         Exploration and novelty emphasis.')
        print('  cohort_target     Load one Analyzer search job.')
        print('  counterexample    Control-heavy Analyzer search job.')
        print('  local_around_rule Search around explicit Atlas rules.')
        print()
        print('Score modes:')
        for sm in base.SCORE_MODES:
            suffix = '  (recommended)' if sm == 'observer_niches' else ''
            print(f'  {sm}{suffix}')
        print()
        print(f'Parallel workers : {WORKERS}')
        print(f'Results folder   : {OUT_DIR}')
        print('Search modes     : v1.0 thin orchestration layer')


if __name__ == '__main__':
    raise SystemExit(main() or 0)
