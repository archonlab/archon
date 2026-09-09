#!/usr/bin/env python3
# Universe Search v1.0.4 - observer_niches
# v1.0.3 + observer niches: worlds also survive inside different schools of observation

import json, math, random, sys, os
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import tkinter as tk
except ImportError:
    tk = None

W, H = 96, 64
POPULATION = 80
GENERATIONS = 8
TICKS = 2600
KEEP_TOP = 16
ELITES = 12
RANDOM_IMMIGRANTS = 6          # fresh blood each generation, helps escape local maxima
SAMPLE_EVERY = 200
OUT_DIR = Path('universe_search_v10_4_results')
HUMAN_FAV_FILE = OUT_DIR / 'human_favorites.json'
COSMIC_RAYS = True
COSMIC_TICKS = (0.46, 0.72)
COSMIC_RADIUS = 5
COSMIC_STRENGTH = 0.78
CELL = 7
PANEL_W = 430
DIVERSITY_BONUS_BASE = 24.0
NOVELTY_BONUS_BASE = 38.0
OBSERVER_COUNT = 18
OBSERVER_ELITES = 6
POST_TEST_CANDIDATES = 6       # expensive: top candidates get a second, harsher evaluation
POST_TEST_OBSERVER_TOP = 8      # worlds each observer can nominate for post-test fitness
POST_TEST_TICK_FRACTION = 0.55  # faster coevolution teacher pass
OBSERVER_DIVERSITY_STRENGTH = 10.0
OBSERVER_DIVERSITY_LATE = 3.0
OBSERVER_BLOCK_CROSSOVER_RATE = 0.62
OBSERVER_MEMORY_DECAY = 0.68

FUNCTIONS = ['sin', 'cos', 'tanh', 'gauss', 'poly', 'step', 'ring']
SCORE_MODES = [
    'balanced', 'novelty', 'motion', 'islands', 'boundaries',
    'scale_genesis', 'living_boundaries', 'edge_transport',
    'emergence', 'nested_complexity', 'memory', 'information_flow', 'stable_movers', 'hierarchy',
    'emergent_ecology', 'observer_log', 'entity_mode', 'local_life', 'flow', 'region_dynamics',
    'hierarchical_novelty', 'macro_scaffold', 'memory_trace', 'adaptive_observer', 'cosmic_curator', 'stress_test', 'observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches'
]
VIEW_MODES = ['value', 'activity', 'velocity', 'edge', 'age', 'delta', 'hotspot', 'ghost']

def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def rnd(a, b):
    return random.uniform(a, b)

def mutate_float(x, scale, lo, hi):
    return clamp(x + random.gauss(0, scale), lo, hi)

@dataclass
class Term:
    kind: str
    weight: float
    freq: float
    center: float
    width: float
    phase: float

@dataclass
class Rule:
    rule_id: int
    parent_a: int
    parent_b: int
    seed: int
    diffusion: float
    inertia: float
    damping: float
    decay: float
    noise: float
    bias: float
    sharpen: float
    threshold_push: float
    w_avg_r1: float
    w_avg_r4: float
    w_avg_r12: float
    w_var_r1: float
    w_var_r4: float
    w_lap_r1: float
    w_lap_r4: float
    terms: list

def random_term():
    return Term(random.choice(FUNCTIONS), rnd(-0.12, 0.12), rnd(1.0, 30.0),
                rnd(0.05, 0.95), rnd(0.004, 0.12), rnd(0, math.tau))

def term_from_dict(d):
    return Term(**d)

def rule_from_dict(d):
    d = dict(d)
    d['terms'] = [term_from_dict(t) if isinstance(t, dict) else t for t in d.get('terms', [])]
    # Backward compatibility if an older JSON lacks new fields.
    base = make_random_rule(d.get('rule_id', 0))
    bd = asdict(base)
    bd.update(d)
    bd['terms'] = d['terms']
    return Rule(**bd)

def rule_to_dict(r):
    return asdict(r)

def make_random_rule(rule_id):
    return Rule(rule_id, -1, -1, random.randrange(1_000_000_000),
                rnd(0.02, 0.65), rnd(0, 0.88), rnd(0.955, 0.999), rnd(0, 0.035),
                10 ** rnd(-5.2, -2.3), rnd(-0.018, 0.018), rnd(-0.22, 0.22), rnd(-0.080, 0.080),
                rnd(-0.8, 0.8), rnd(-0.6, 0.6), rnd(-0.4, 0.4),
                rnd(-0.5, 0.5), rnd(-0.4, 0.4),
                rnd(-0.7, 0.7), rnd(-0.5, 0.5),
                [random_term() for _ in range(random.randint(2, 6))])

def mutate_term(t):
    nt = Term(t.kind, t.weight, t.freq, t.center, t.width, t.phase)
    if random.random() < 0.08:
        nt.kind = random.choice(FUNCTIONS)
    nt.weight = mutate_float(nt.weight, 0.035, -0.22, 0.22)
    nt.freq = mutate_float(nt.freq, 2.3, 0.2, 45.0)
    nt.center = mutate_float(nt.center, 0.055, 0.0, 1.0)
    nt.width = mutate_float(nt.width, 0.018, 0.002, 0.18)
    nt.phase = (nt.phase + random.gauss(0, 0.45)) % math.tau
    return nt

def crossover(a, b, rule_id):
    def pick(name):
        return getattr(a if random.random() < 0.5 else b, name)
    child_terms = []
    pool = a.terms + b.terms
    random.shuffle(pool)
    for t in pool[:random.randint(2, 7)]:
        child_terms.append(mutate_term(t))
    if random.random() < 0.12 and len(child_terms) < 9:
        child_terms.append(random_term())
    if random.random() < 0.08 and len(child_terms) > 2:
        child_terms.pop(random.randrange(len(child_terms)))

    r = Rule(rule_id, a.rule_id, b.rule_id, random.randrange(1_000_000_000),
             pick('diffusion'), pick('inertia'), pick('damping'), pick('decay'), pick('noise'),
             pick('bias'), pick('sharpen'), pick('threshold_push'),
             pick('w_avg_r1'), pick('w_avg_r4'), pick('w_avg_r12'), pick('w_var_r1'), pick('w_var_r4'),
             pick('w_lap_r1'), pick('w_lap_r4'), child_terms)
    r.diffusion = mutate_float(r.diffusion, 0.055, 0.0, 0.9)
    r.inertia = mutate_float(r.inertia, 0.055, 0.0, 0.96)
    r.damping = mutate_float(r.damping, 0.006, 0.92, 0.9995)
    r.decay = mutate_float(r.decay, 0.006, 0.0, 0.06)
    r.noise = 10 ** mutate_float(math.log10(max(r.noise, 1e-7)), 0.22, -6.0, -1.8)
    r.bias = mutate_float(r.bias, 0.006, -0.04, 0.04)
    r.sharpen = mutate_float(r.sharpen, 0.035, -0.35, 0.35)
    r.threshold_push = mutate_float(r.threshold_push, 0.018, -0.12, 0.12)
    for name, sc, lo, hi in [
        ('w_avg_r1', .08, -.9, .9), ('w_avg_r4', .07, -.8, .8), ('w_avg_r12', .055, -.65, .65),
        ('w_var_r1', .055, -.65, .65), ('w_var_r4', .05, -.55, .55),
        ('w_lap_r1', .075, -.9, .9), ('w_lap_r4', .06, -.7, .7)]:
        setattr(r, name, mutate_float(getattr(r, name), sc, lo, hi))
    return r

# ---------- Fast toroidal field operations ----------

def box_avg_grid(grid, radius, boundary_mode="wrap"):
    """Square average using wrap or zero-valued fixed-dead boundaries."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    if height == 0 or width == 0:
        return []
    if any(len(row) != width for row in grid):
        raise ValueError("grid must be rectangular")
    if radius <= 0:
        return [row[:] for row in grid]

    if boundary_mode not in ("wrap", "fixed_dead"):
        raise ValueError(
            "boundary_mode must be 'wrap' or 'fixed_dead'"
        )

    win = 2 * radius + 1
    area = win * win

    if boundary_mode == "fixed_dead":
        # Integral image over a zero-padded field. The denominator remains the
        # full window area, because cells outside the world are explicitly dead.
        padded_width = width + 2 * radius
        padded_height = height + 2 * radius
        padded = [
            [0.0] * padded_width
            for _ in range(padded_height)
        ]
        for y, row in enumerate(grid):
            padded[y + radius][radius:radius + width] = row[:]

        integral = [
            [0.0] * (padded_width + 1)
            for _ in range(padded_height + 1)
        ]
        for y in range(padded_height):
            running = 0.0
            target = integral[y + 1]
            previous = integral[y]
            for x in range(padded_width):
                running += padded[y][x]
                target[x + 1] = previous[x + 1] + running

        out = [[0.0] * width for _ in range(height)]
        for y in range(height):
            y0 = y
            y1 = y + win
            for x in range(width):
                x0 = x
                x1 = x + win
                total = (
                    integral[y1][x1]
                    - integral[y0][x1]
                    - integral[y1][x0]
                    + integral[y0][x0]
                )
                out[y][x] = total / area
        return out

    hs = [[0.0] * width for _ in range(height)]
    for y in range(height):
        row = grid[y]
        s = sum(row[x % width] for x in range(-radius, radius + 1))
        hs[y][0] = s
        for x in range(1, width):
            s += (
                row[(x + radius) % width]
                - row[(x - radius - 1) % width]
            )
            hs[y][x] = s

    out = [[0.0] * width for _ in range(height)]
    for x in range(width):
        s = sum(
            hs[y % height][x]
            for y in range(-radius, radius + 1)
        )
        out[0][x] = s / area
        for y in range(1, height):
            s += (
                hs[(y + radius) % height][x]
                - hs[(y - radius - 1) % height][x]
            )
            out[y][x] = s / area
    return out


def variance_grid(grid, avg, radius, boundary_mode="wrap"):
    height = len(grid)
    width = len(grid[0]) if height else 0
    sq = [[value * value for value in row] for row in grid]
    avg_sq = box_avg_grid(sq, radius, boundary_mode)
    return [
        [
            max(0.0, avg_sq[y][x] - avg[y][x] * avg[y][x])
            for x in range(width)
        ]
        for y in range(height)
    ]

# ---------- Optional array backend for feature maps (Stage 1) ----------
# Default is "numpy".
# Set ART_EVO_FIELD_BACKEND=numpy or ART_EVO_FIELD_BACKEND=cupy before launch.
# The selector is intentionally read at runtime, not only at import time, so
# validation scripts or notebooks can switch os.environ after importing this file.
FIELD_MAP_BACKEND = os.environ.get("ART_EVO_FIELD_BACKEND", "numpy").strip().lower()


class FieldBackendError(RuntimeError):
    """Base class for evaluator infrastructure failures, never candidate evidence."""


class FieldBackendDependencyError(FieldBackendError):
    """The selected numerical backend is unavailable in this Python runtime."""


class FieldBackendConfigurationError(FieldBackendError):
    """The numerical backend selection itself is invalid."""

try:
    import numpy as _np
except Exception:
    _np = None

try:
    import cupy as _cp
    try:
        from cupyx.scipy.ndimage import uniform_filter as _cupy_uniform_filter
    except Exception:
        _cupy_uniform_filter = None
except Exception:
    _cp = None
    _cupy_uniform_filter = None


def _selected_field_map_backend():
    raw = os.environ.get("ART_EVO_FIELD_BACKEND")
    backend = (raw if raw else "numpy").strip().lower()

    aliases = {
        "np": "numpy",
        "cpu": "numpy",
        "cp": "cupy",
        "cuda": "cupy",
        "gpu": "cupy",
        "legacy": "numpy",
    }

    backend = aliases.get(backend, backend)

    if backend not in ("numpy", "cupy"):
        raise FieldBackendConfigurationError(
            f"Unknown ART_EVO_FIELD_BACKEND={backend!r}. Use 'numpy' or 'cupy'."
        )

    return backend


def field_backend_status():
    """Small diagnostic helper for logs / manual checks."""
    return {
        "selected": _selected_field_map_backend(),
        "env": os.environ.get("ART_EVO_FIELD_BACKEND"),
        "numpy": _np is not None,
        "cupy": _cp is not None,
    }


def _array_module_for_feature_maps():
    backend = _selected_field_map_backend()
    if backend == "cupy":
        if _cp is None:
            raise FieldBackendDependencyError("ART_EVO_FIELD_BACKEND=cupy requested, but CuPy is not installed/importable.")
        return _cp
    if backend == "numpy":
        if _np is None:
            raise FieldBackendDependencyError("ART_EVO_FIELD_BACKEND=numpy requested, but NumPy is not installed/importable.")
        return _np
    return None


def require_field_backend():
    """Fail before candidate evaluation when evaluator infrastructure is absent."""
    return _array_module_for_feature_maps()


def _to_cpu_list(xp, arr):
    if xp is _cp:
        return _cp.asnumpy(arr).tolist()
    return arr.tolist()


def _maps_to_cpu_lists(xp, maps):
    """Convert feature maps back to Python lists.

    Stage 7: for CuPy, batch the six maps into one GPU->CPU transfer.
    This avoids six separate asnumpy() calls and six implicit sync points.
    """
    if xp is _cp:
        stacked = _cp.stack(maps, axis=0)
        host = _cp.asnumpy(stacked)
        return tuple(host[i].tolist() for i in range(host.shape[0]))
    return tuple(m.tolist() for m in maps)


def _box_avg_array(arr, radius, xp, boundary_mode="wrap"):
    """Toroidal square average using the fastest backend implementation."""
    if radius <= 0:
        return arr.copy()
    if boundary_mode not in ("wrap", "fixed_dead"):
        raise ValueError(
            "boundary_mode must be 'wrap' or 'fixed_dead'"
        )
    size = 2 * radius + 1
    if xp is _cp and _cupy_uniform_filter is not None:
        mode = "wrap" if boundary_mode == "wrap" else "constant"
        return _cupy_uniform_filter(
            arr,
            size=size,
            mode=mode,
            cval=0.0,
        )
    if boundary_mode == "fixed_dead":
        padded = xp.pad(
            arr,
            ((radius, radius), (radius, radius)),
            mode="constant",
            constant_values=0.0,
        )
        out = xp.zeros_like(arr, dtype=xp.float32)
        height, width = arr.shape
        for dy in range(size):
            for dx in range(size):
                out += padded[dy:dy + height, dx:dx + width]
        return out / float(size * size)

    hs = xp.zeros_like(arr, dtype=xp.float32)
    for dx in range(-radius, radius + 1):
        hs += xp.roll(arr, shift=dx, axis=1)
    out = xp.zeros_like(arr, dtype=xp.float32)
    for dy in range(-radius, radius + 1):
        out += xp.roll(hs, shift=dy, axis=0)
    return out / float(size * size)


def _variance_array(arr, avg, radius, xp, arr_sq=None, boundary_mode="wrap"):
    """Local variance. Stage 7 can pass precomputed arr_sq to avoid duplicate arr*arr."""
    if arr_sq is None:
        arr_sq = arr * arr
    avg_sq = _box_avg_array(arr_sq, radius, xp, boundary_mode)
    return xp.maximum(0.0, avg_sq - avg * avg)


def _feature_maps_from_array(arr, xp, boundary_mode="wrap"):
    """Return feature maps as native NumPy/CuPy arrays.

    This is the GPU-stays-GPU core: no asnumpy(), no tolist().
    Higher layers can keep working on the returned arrays without crossing
    the CPU/GPU boundary until they really need Python data.
    """
    avg_r1_box = _box_avg_array(arr, 1, xp, boundary_mode)
    avg_r4 = _box_avg_array(arr, 4, xp, boundary_mode)
    avg_r12 = _box_avg_array(arr, 12, xp, boundary_mode)

    # Stage 7: reuse arr*arr for both variance radii.
    arr_sq = arr * arr
    var_r1 = _variance_array(
        arr, avg_r1_box, 1, xp,
        arr_sq=arr_sq,
        boundary_mode=boundary_mode,
    )
    var_r4 = _variance_array(
        arr, avg_r4, 4, xp,
        arr_sq=arr_sq,
        boundary_mode=boundary_mode,
    )

    if boundary_mode == "wrap":
        lap_r4 = (
            xp.roll(avg_r4, shift=4, axis=1) +
            xp.roll(avg_r4, shift=-4, axis=1) +
            xp.roll(avg_r4, shift=4, axis=0) +
            xp.roll(avg_r4, shift=-4, axis=0) -
            4.0 * arr
        ) / 4.0
    else:
        pad = 4
        padded = xp.pad(
            avg_r4,
            ((pad, pad), (pad, pad)),
            mode="constant",
            constant_values=0.0,
        )
        height, width = arr.shape
        left = padded[pad:pad + height, 0:width]
        right = padded[pad:pad + height, 2 * pad:2 * pad + width]
        up = padded[0:height, pad:pad + width]
        down = padded[2 * pad:2 * pad + height, pad:pad + width]
        lap_r4 = (left + right + up + down - 4.0 * arr) / 4.0

    return avg_r1_box, avg_r4, avg_r12, var_r1, var_r4, lap_r4


def _as_backend_array(grid, xp):
    """Convert grid to the selected backend with the least copying possible.

    Stage 4: if the caller already keeps the field as a NumPy/CuPy array,
    do not copy it back and forth every feature-map call. Lists are still
    supported for the old CPU observer path.
    """
    if xp is _cp and _cp is not None and isinstance(grid, _cp.ndarray):
        return grid.astype(_cp.float32, copy=False)
    if xp is _np and _np is not None and isinstance(grid, _np.ndarray):
        return grid.astype(_np.float32, copy=False)
    return xp.asarray(grid, dtype=xp.float32)


def feature_maps_array_backend_raw(grid, boundary_mode="wrap"):
    """Optional NumPy/CuPy implementation returning native arrays.

    Returns:
        (xp, maps) where xp is numpy/cupy and maps is a tuple of arrays.

    This raw path keeps arrays native to the selected backend. If `grid` is
    already a CuPy array, it stays on GPU; if it is already a NumPy array, it
    stays on CPU. The legacy list-returning API is preserved below.
    """
    xp = _array_module_for_feature_maps()
    if xp is None:
        return None, None
    arr = _as_backend_array(grid, xp)
    maps = _feature_maps_from_array(arr, xp, boundary_mode)
    # Do not synchronize here. Returning GPU arrays is safe; CPU conversion
    # or external profilers can synchronize when needed.
    return xp, maps


def feature_maps_array_backend(grid, boundary_mode="wrap"):
    """Legacy wrapper returning Python lists."""
    xp, maps = feature_maps_array_backend_raw(grid, boundary_mode)
    if maps is None:
        return None
    return _maps_to_cpu_lists(xp, maps)


def gpu_basic_metrics_from_arrays(a, v, delta, age=None, trace=None):
    """Stage 8: compute basic Observer metrics directly on NumPy/CuPy arrays.

    This is a side-path for profiling and future GPU-native observer work.
    It does not change the old FieldSim.metrics() API.
    """
    xp = _cp if (_cp is not None and isinstance(a, _cp.ndarray)) else _np
    if xp is None:
        return None

    a = a.astype(xp.float32, copy=False)
    v = v.astype(xp.float32, copy=False)
    delta = delta.astype(xp.float32, copy=False)

    mean = xp.mean(a)
    active = xp.mean(a > 0.08)
    hi = xp.mean(a > 0.55)
    motion = xp.mean(xp.abs(v))

    edge_map_arr = 0.5 * (
        xp.abs(a - xp.roll(a, shift=-1, axis=1)) +
        xp.abs(a - xp.roll(a, shift=-1, axis=0))
    )
    edge = xp.mean(edge_map_arr)

    activity = xp.mean(delta)
    edge_mask = edge_map_arr > 0.12
    edge_cells = xp.sum(edge_mask)
    boundary_activity = xp.where(
        edge_cells > 0,
        xp.sum(delta * edge_mask) / xp.maximum(edge_cells, 1),
        xp.asarray(0.0, dtype=xp.float32),
    )
    boundary_fraction = xp.mean(edge_mask)

    hot_mask = delta > 0.006
    hot_fraction = xp.mean(hot_mask)
    delta_total = xp.sum(delta)

    yy, xx = xp.indices(a.shape, dtype=xp.float32)
    h, w = a.shape
    act_cx = xp.where(delta_total > 1e-12, xp.sum(xx * delta) / delta_total / float(w), 0.5)
    act_cy = xp.where(delta_total > 1e-12, xp.sum(yy * delta) / delta_total / float(h), 0.5)
    delta_mass = delta_total / float(w * h)

    out = {
        "mean": mean,
        "active": active,
        "hi": hi,
        "motion": motion,
        "edge": edge,
        "activity": activity,
        "boundary_activity": boundary_activity,
        "boundary_fraction": boundary_fraction,
        "act_cx": act_cx,
        "act_cy": act_cy,
        "delta_mass": delta_mass,
        "hot_fraction": hot_fraction,
    }

    if age is not None:
        age_arr = xp.asarray(age)
        out["old_fraction"] = xp.mean(age_arr > 120)

    if trace is not None:
        tr = xp.asarray(trace, dtype=xp.float32)
        out["trace_mass"] = xp.mean(tr)
        out["trace_hot"] = xp.mean(tr > 0.08)
        out["trace_edge"] = xp.mean(
            0.5 * (
                xp.abs(tr - xp.roll(tr, shift=-1, axis=1)) +
                xp.abs(tr - xp.roll(tr, shift=-1, axis=0))
            )
        )

    return out


def gpu_metrics_to_cpu(metrics):
    """Convert GPU/array scalar metrics to plain Python floats."""
    if metrics is None:
        return None
    out = {}
    for k, v in metrics.items():
        if _cp is not None and isinstance(v, _cp.ndarray):
            out[k] = float(_cp.asnumpy(v))
        elif _np is not None and isinstance(v, _np.ndarray):
            out[k] = float(v)
        else:
            out[k] = float(v)
    return out


def profile_gpu_basic_metrics_once(grid=None):
    """Small manual helper for Stage 8 profiling.

    It creates deterministic arrays if grid is None and returns CPU floats.
    """
    xp = _array_module_for_feature_maps()
    if xp is None:
        return None
    if grid is None:
        rng = random.Random(12345)
        grid = [[rng.random() for _ in range(W)] for _ in range(H)]
    a = _as_backend_array(grid, xp)
    v = xp.zeros_like(a, dtype=xp.float32)
    delta = xp.abs(a - xp.roll(a, shift=1, axis=0)) * 0.01
    metrics = gpu_basic_metrics_from_arrays(a, v, delta)
    if xp is _cp:
        _cp.cuda.Stream.null.synchronize()
    return gpu_metrics_to_cpu(metrics)


class FieldSim:
    """One cellular-automaton world with explicit runtime geometry.

    The legacy module-level self.width/self.height values remain defaults for Universe Search.
    Observer and experimental runs can now provide their own dimensions.
    Runtime Environment v1 supports torus + wrap; bounded boundaries follow
    in the next stage.
    """

    def __init__(
        self,
        rule,
        width=W,
        height=H,
        topology="torus",
        boundary_mode="wrap",
    ):
        self.width = int(width)
        self.height = int(height)
        if self.width < 1 or self.height < 1:
            raise ValueError("Field width and height must be >= 1")

        self.topology = str(topology)
        self.boundary_mode = str(boundary_mode)
        valid_environment = (
            (self.topology == "torus" and self.boundary_mode == "wrap")
            or (
                self.topology == "bounded"
                and self.boundary_mode == "fixed_dead"
            )
        )
        if not valid_environment:
            raise ValueError(
                "Supported environments are torus+wrap and "
                "bounded+fixed_dead"
            )

        self.rule = rule
        self.tick = 0
        self.rng = random.Random(rule.seed)
        self.a = [[0.0] * self.width for _ in range(self.height)]
        self.prev_a = [[0.0] * self.width for _ in range(self.height)]
        self.v = [[0.0] * self.width for _ in range(self.height)]
        self.delta = [[0.0] * self.width for _ in range(self.height)]
        self.age = [[0] * self.width for _ in range(self.height)]
        self.activity_heat = [[0.0] * self.width for _ in range(self.height)]
        # Short-term memory trace: fading echo of recent changes.
        # Useful for detecting worlds where events leave temporary scars/trails.
        self.trace = [[0.0] * self.width for _ in range(self.height)]
        self.seed_field()
        self.prev_a = [row[:] for row in self.a]

    def seed_field(self):
        for y in range(self.height):
            for x in range(self.width):
                cx, cy = self.width / 2, self.height / 2
                d = math.hypot((x - cx) / self.width, (y - cy) / self.height)
                blob = max(0.0, 1.0 - d * 3.2)
                self.a[y][x] = clamp(blob * self.rng.random() + self.rng.random() * 0.05)

    def get(self, x, y):
        if self.boundary_mode == "wrap":
            return self.a[y % self.height][x % self.width]
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.a[y][x]
        return 0.0

    def _grid_get(self, grid, x, y):
        if self.boundary_mode == "wrap":
            return grid[y % self.height][x % self.width]
        if 0 <= x < self.width and 0 <= y < self.height:
            return grid[y][x]
        return 0.0

    def avg8(self, x, y, avg_r1=None):
        if avg_r1 is None:
            # true 8-neighbor average, excluding center
            s = 0.0
            for yy in range(y-1, y+2):
                for xx in range(x-1, x+2):
                    if xx != x or yy != y:
                        s += self.get(xx, yy)
            return s / 8.0
        # box avg includes center, convert to excluding center
        return (avg_r1[y][x] * 9.0 - self.a[y][x]) / 8.0

    def laplacian(self, x, y):
        c = self.a[y][x]
        return (self.get(x+1,y) + self.get(x-1,y) + self.get(x,y+1) + self.get(x,y-1) - 4*c) / 4.0

    def eval_term(self, t, c, n, lap, edge):
        z = c * 0.8 + n * 0.7 + lap * 0.9 + edge * 0.55 + t.phase
        if t.kind == 'sin':
            val = math.sin(z * t.freq + t.phase)
        elif t.kind == 'cos':
            val = math.cos(z * t.freq + t.phase)
        elif t.kind == 'tanh':
            val = math.tanh((z - t.center) * t.freq)
        elif t.kind == 'gauss':
            val = math.exp(-((z - t.center) ** 2) / max(1e-6, t.width))
        elif t.kind == 'poly':
            val = (z - t.center) ** 2 - t.width
        elif t.kind == 'step':
            val = 1.0 if z > t.center else -1.0
        elif t.kind == 'ring':
            val = math.sin(abs(z - t.center) * t.freq) * math.exp(-abs(z - t.center) / max(1e-6, t.width))
        else:
            val = 0.0
        return t.weight * val

    def feature_maps(self):
        accelerated = feature_maps_array_backend(self.a, self.boundary_mode)
        if accelerated is not None:
            return accelerated

        avg_r1_box = box_avg_grid(self.a, 1, self.boundary_mode)
        avg_r4 = box_avg_grid(self.a, 4, self.boundary_mode)
        avg_r12 = box_avg_grid(self.a, 12, self.boundary_mode)
        var_r1 = variance_grid(
            self.a, avg_r1_box, 1, self.boundary_mode
        )
        var_r4 = variance_grid(
            self.a, avg_r4, 4, self.boundary_mode
        )
        # Larger curvature: compare local cell to four medium-neighborhood samples.
        lap_r4 = [[0.0] * self.width for _ in range(self.height)]
        for y in range(self.height):
            for x in range(self.width):
                c = self.a[y][x]
                lap_r4[y][x] = (
                    self._grid_get(avg_r4, x + 4, y)
                    + self._grid_get(avg_r4, x - 4, y)
                    + self._grid_get(avg_r4, x, y + 4)
                    + self._grid_get(avg_r4, x, y - 4)
                    - 4 * c
                ) / 4.0
        return avg_r1_box, avg_r4, avg_r12, var_r1, var_r4, lap_r4

    def step(self):
        old_a = self.a
        r = self.rule
        avg_r1_box, avg_r4, avg_r12, var_r1, var_r4, lap_r4 = self.feature_maps()
        na = [[0.0] * self.width for _ in range(self.height)]
        nv = [[0.0] * self.width for _ in range(self.height)]
        ndelta = [[0.0] * self.width for _ in range(self.height)]
        nage = [[0] * self.width for _ in range(self.height)]
        for y in range(self.height):
            for x in range(self.width):
                c = self.a[y][x]
                n = self.avg8(x, y, avg_r1_box)
                lap = self.laplacian(x, y)
                edge = abs(c - n)
                vel = self.v[y][x]

                local_threshold = r.threshold_push * (avg_r12[y][x] - 0.5)
                adaptive_diffusion = r.diffusion * (1.0 + 0.55 * var_r4[y][x])

                force = adaptive_diffusion * lap + r.bias - r.decay * c
                force += r.sharpen * edge * (0.5 - c)
                force += local_threshold
                force += r.w_avg_r1 * (n - 0.5) * 0.055
                force += r.w_avg_r4 * (avg_r4[y][x] - 0.5) * 0.045
                force += r.w_avg_r12 * (avg_r12[y][x] - 0.5) * 0.035
                force += r.w_var_r1 * var_r1[y][x] * 0.12
                force += r.w_var_r4 * var_r4[y][x] * 0.10
                force += r.w_lap_r1 * lap * 0.075
                force += r.w_lap_r4 * lap_r4[y][x] * 0.06
                for t in r.terms:
                    force += self.eval_term(t, c, n, lap, edge)
                force += self.rng.uniform(-r.noise, r.noise)

                vel = (vel * r.inertia + force) * r.damping
                c2 = clamp(c + vel)
                if c2 > 0.995:
                    vel -= (c2 - 0.995) * 0.85; c2 = 0.995
                if c2 < 0.004:
                    c2 = 0.0; vel *= 0.35
                d = abs(c2 - c)
                na[y][x] = c2
                nv[y][x] = vel
                ndelta[y][x] = d
                nage[y][x] = self.age[y][x] + 1 if d < 0.006 else 0
                self.activity_heat[y][x] = min(1.0, self.activity_heat[y][x] * 0.92 + d * 18.0)
                self.trace[y][x] = min(1.0, self.trace[y][x] * 0.965 + d * 22.0)
        self.prev_a = old_a
        self.a, self.v, self.delta, self.age = na, nv, ndelta, nage
        self.tick += 1

    def metrics(self):
        vals = [v for row in self.a for v in row]
        mean = sum(vals) / len(vals)
        active = sum(1 for v in vals if v > 0.08) / len(vals)
        hi = sum(1 for v in vals if v > 0.55) / len(vals)
        motion = sum(abs(self.v[y][x]) for y in range(self.height) for x in range(self.width)) / (self.width * self.height)
        edge = 0.0
        boundary_activity = 0.0
        activity = 0.0
        edge_cells = 0
        for y in range(self.height):
            for x in range(self.width):
                e = (
                    abs(self.a[y][x] - self.get(x + 1, y))
                    + abs(self.a[y][x] - self.get(x, y + 1))
                )
                e *= 0.5
                edge += e
                d = self.delta[y][x]
                activity += d
                if e > 0.12:
                    boundary_activity += d
                    edge_cells += 1
        edge /= (self.width * self.height)
        activity /= (self.width * self.height)
        boundary_activity = boundary_activity / max(1, edge_cells)
        boundary_fraction = edge_cells / (self.width * self.height)
        act_cx, act_cy, delta_mass, hot_fraction = activity_centroid_from_delta(self.delta)
        old_fraction = sum(1 for y in range(self.height) for x in range(self.width) if self.age[y][x] > 120) / (self.width * self.height)
        trace_mass = sum(self.trace[y][x] for y in range(self.height) for x in range(self.width)) / (self.width * self.height)
        trace_hot = sum(1 for y in range(self.height) for x in range(self.width) if self.trace[y][x] > 0.08) / (self.width * self.height)
        trace_edge = 0.0
        for y in range(self.height):
            for x in range(self.width):
                trace_edge += 0.5 * (
                    abs(
                        self.trace[y][x]
                        - self._grid_get(self.trace, x + 1, y)
                    )
                    + abs(
                        self.trace[y][x]
                        - self._grid_get(self.trace, x, y + 1)
                    )
                )
        trace_edge /= (self.width * self.height)
        return {
            'mean': mean, 'active': active, 'hi': hi, 'motion': motion, 'edge': edge,
            'activity': activity, 'boundary_activity': boundary_activity,
            'boundary_fraction': boundary_fraction,
            'act_cx': act_cx, 'act_cy': act_cy, 'delta_mass': delta_mass,
            'hot_fraction': hot_fraction, 'old_fraction': old_fraction,
            'trace_mass': trace_mass, 'trace_hot': trace_hot, 'trace_edge': trace_edge,
        }

    def scale_metrics(self):
        avg_r1_box, avg_r4, avg_r12, var_r1, var_r4, _ = self.feature_maps()
        small = []; medium = []; large = []
        for y in range(0, self.height, 4):
            for x in range(0, self.width, 4):
                small.append(var_r1[y][x])
                medium.append(var_r4[y][x])
                large.append(avg_r12[y][x])
        def var(xs):
            m = sum(xs) / max(1, len(xs))
            return sum((x - m) ** 2 for x in xs) / max(1, len(xs))
        small_texture = sum(small) / max(1, len(small))
        mid_texture = sum(medium) / max(1, len(medium))
        large_order = var(large)
        scale_gap = abs(small_texture - large_order) + abs(mid_texture - large_order) * 0.5
        return {'small_texture': small_texture, 'mid_texture': mid_texture, 'large_order': large_order, 'scale_gap': scale_gap}

    def islands(self):
        seen = [[False]*self.width for _ in range(self.height)]
        sizes = []
        for y in range(self.height):
            for x in range(self.width):
                if seen[y][x] or self.a[y][x] <= 0.12:
                    continue
                stack = [(x,y)]; seen[y][x] = True; size = 0
                while stack:
                    px, py = stack.pop(); size += 1
                    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        nx = px + dx
                        ny = py + dy
                        if self.boundary_mode == "wrap":
                            nx %= self.width
                            ny %= self.height
                        elif not (
                            0 <= nx < self.width
                            and 0 <= ny < self.height
                        ):
                            continue
                        if not seen[ny][nx] and self.a[ny][nx] > 0.12:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                sizes.append(size)
        return len(sizes), (max(sizes) if sizes else 0), sizes


def edge_map(frame):
    out = [[0.0] * W for _ in range(H)]
    for y in range(H):
        row = frame[y]
        row2 = frame[(y + 1) % H]
        for x in range(W):
            out[y][x] = 0.5 * (abs(row[x] - row[(x + 1) % W]) + abs(row[x] - row2[x]))
    return out

def frame_similarity(a, b):
    # 1.0 = same large-scale structure, 0.0 = totally different.
    ea, eb = edge_map(a), edge_map(b)
    diff = 0.0
    mass = 0.0
    for y in range(H):
        for x in range(W):
            diff += abs(ea[y][x] - eb[y][x])
            mass += max(ea[y][x], eb[y][x], 0.02)
    return clamp(1.0 - diff / max(1e-6, mass))

def activity_centroid_from_delta(delta):
    total = 0.0
    sx = 0.0
    sy = 0.0
    hot = 0
    for y in range(H):
        for x in range(W):
            d = delta[y][x]
            total += d
            sx += x * d
            sy += y * d
            if d > 0.006:
                hot += 1
    if total <= 1e-12:
        return 0.5, 0.5, 0.0, 0.0
    return sx / total / W, sy / total / H, total / (W * H), hot / (W * H)

def centroid_path_score(samples):
    pts = [(s.get('act_cx', 0.5), s.get('act_cy', 0.5)) for s in samples if s.get('activity', 0) > 1e-6]
    if len(pts) < 3:
        return 0.0
    dist = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx = min(abs(x2 - x1), 1.0 - abs(x2 - x1))
        dy = min(abs(y2 - y1), 1.0 - abs(y2 - y1))
        dist += math.hypot(dx, dy)
    return clamp(dist * 2.5)

def temporal_variance(samples, key):
    vals = [s.get(key, 0.0) for s in samples]
    if not vals:
        return 0.0
    m = sum(vals) / len(vals)
    return sum((v - m) ** 2 for v in vals) / len(vals)


def nested_window_metrics(frames, window=12, stride=6):
    """Measure small living structures inside a larger scaffold.

    Good worlds have:
    - macro scaffold: edge map remains similar over time;
    - local complexity: some windows have texture/edges;
    - local activity: only some windows are alive, not the whole field;
    - local diversity: windows are not all identical.
    """
    if len(frames) < 3:
        return {
            'nested_score_raw': 0.0, 'local_complexity': 0.0, 'local_activity': 0.0,
            'local_diversity': 0.0, 'macro_stability': 0.0, 'active_windows': 0.0,
        }
    first = frames[1]
    last = frames[-1]
    prev = frames[-2]
    macro_stability = frame_similarity(first, last)
    complexities = []
    activities = []
    means = []
    active_windows = 0
    total_windows = 0
    for y0 in range(0, H - window + 1, stride):
        for x0 in range(0, W - window + 1, stride):
            total_windows += 1
            vals = []
            delta_sum = 0.0
            edge_sum = 0.0
            for yy in range(y0, y0 + window):
                for xx in range(x0, x0 + window):
                    v = last[yy][xx]
                    vals.append(v)
                    delta_sum += abs(last[yy][xx] - prev[yy][xx])
                    if xx + 1 < x0 + window:
                        edge_sum += abs(last[yy][xx] - last[yy][xx + 1])
                    if yy + 1 < y0 + window:
                        edge_sum += abs(last[yy][xx] - last[yy + 1][xx])
            n = window * window
            mean = sum(vals) / n
            var = sum((v - mean) ** 2 for v in vals) / n
            local_edge = edge_sum / max(1, 2 * window * (window - 1))
            local_delta = delta_sum / n
            # complexity prefers texture with boundaries, but not pure saturation.
            complexity = clamp(var * 9.0 + local_edge * 2.2)
            activity = clamp(local_delta * 55.0)
            complexities.append(complexity)
            activities.append(activity)
            means.append(mean)
            if complexity > 0.10 and activity > 0.015:
                active_windows += 1
    if not complexities:
        return {
            'nested_score_raw': 0.0, 'local_complexity': 0.0, 'local_activity': 0.0,
            'local_diversity': 0.0, 'macro_stability': 0.0, 'active_windows': 0.0,
        }
    local_complexity = sum(complexities) / len(complexities)
    local_activity = sum(activities) / len(activities)
    mc = sum(complexities) / len(complexities)
    mm = sum(means) / len(means)
    diversity_c = sum((c - mc) ** 2 for c in complexities) / len(complexities)
    diversity_m = sum((m - mm) ** 2 for m in means) / len(means)
    local_diversity = clamp(diversity_c * 8.0 + diversity_m * 4.0)
    active_window_fraction = active_windows / max(1, total_windows)
    # Sweet spot: not zero local life, but not everything alive either.
    localization = clamp(1.0 - abs(active_window_fraction - 0.12) * 5.0)
    nested_score_raw = (
        0.28 * macro_stability +
        0.24 * clamp(local_complexity * 2.5) +
        0.22 * clamp(local_activity * 8.0) +
        0.16 * local_diversity +
        0.10 * localization
    )
    return {
        'nested_score_raw': nested_score_raw,
        'local_complexity': local_complexity,
        'local_activity': local_activity,
        'local_diversity': local_diversity,
        'macro_stability': macro_stability,
        'active_windows': active_window_fraction,
    }


def shifted_window_similarity(prev, last, x0, y0, window, dx, dy):
    """Similarity between prev window and shifted last window.
    1 means same local pattern moved by (dx, dy). Toroidal outside global field,
    but window itself is kept rectangular.
    """
    diff = 0.0
    mass = 0.0
    for yy in range(window):
        y_prev = y0 + yy
        y_last = (y0 + yy + dy) % H
        for xx in range(window):
            x_prev = x0 + xx
            x_last = (x0 + xx + dx) % W
            a = prev[y_prev][x_prev]
            b = last[y_last][x_last]
            diff += abs(a - b)
            mass += max(abs(a), abs(b), 0.03)
    return clamp(1.0 - diff / max(1e-6, mass))



def rotated_window_similarity(prev, last, x0, y0, window, rotation):
    """Similarity when a local pattern rotates in place.
    rotation can be 90, 180, 270 degrees. This catches little rotors/mechanisms
    that do not translate but still preserve structure while changing orientation.
    """
    diff = 0.0
    mass = 0.0
    for yy in range(window):
        for xx in range(window):
            if rotation == 90:
                rx, ry = window - 1 - yy, xx
            elif rotation == 180:
                rx, ry = window - 1 - xx, window - 1 - yy
            elif rotation == 270:
                rx, ry = yy, window - 1 - xx
            else:
                rx, ry = xx, yy
            a = prev[y0 + yy][x0 + xx]
            b = last[y0 + ry][x0 + rx]
            diff += abs(a - b)
            mass += max(abs(a), abs(b), 0.03)
    return clamp(1.0 - diff / max(1e-6, mass))

def multi_scale_local_life(frames, windows=(8, 16, 32), strides=(4, 8, 16)):
    """Find local life inside macro order.

    It asks smaller questions than whole-world scoring:
    - Is there local structure in a window?
    - Is it active but not noisy everywhere?
    - Does it move like a pattern (flow) rather than just flicker?
    - Is the macro scaffold still recognizable?
    """
    if len(frames) < 3:
        return {
            'ms_local_life': 0.0, 'ms_flow': 0.0, 'ms_rotation_flow': 0.0, 'ms_complexity': 0.0,
            'ms_activity': 0.0, 'ms_diversity': 0.0, 'best_hotspot_x': 0,
            'best_hotspot_y': 0, 'best_hotspot_size': 0, 'best_hotspot_score': 0.0,
        }
    first, prev, last = frames[1], frames[-2], frames[-1]
    macro = frame_similarity(first, last)
    all_complexities = []
    all_activities = []
    all_flows = []
    all_rot_flows = []
    best = (0.0, 0, 0, 0)
    for window, stride in zip(windows, strides):
        for y0 in range(0, H - window + 1, stride):
            for x0 in range(0, W - window + 1, stride):
                vals = []
                delta_sum = 0.0
                edge_sum = 0.0
                for yy in range(y0, y0 + window):
                    for xx in range(x0, x0 + window):
                        v = last[yy][xx]
                        vals.append(v)
                        delta_sum += abs(last[yy][xx] - prev[yy][xx])
                        if xx + 1 < x0 + window:
                            edge_sum += abs(last[yy][xx] - last[yy][xx + 1])
                        if yy + 1 < y0 + window:
                            edge_sum += abs(last[yy][xx] - last[yy + 1][xx])
                n = window * window
                mean = sum(vals) / n
                var = sum((v - mean) ** 2 for v in vals) / n
                local_edge = edge_sum / max(1, 2 * window * (window - 1))
                activity = clamp((delta_sum / n) * 65.0)
                complexity = clamp(var * 10.0 + local_edge * 2.6)

                same = shifted_window_similarity(prev, last, x0, y0, window, 0, 0)
                shifted_best = 0.0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        shifted_best = max(shifted_best, shifted_window_similarity(prev, last, x0, y0, window, dx, dy))
                # Flow prefers shifted similarity that beats still similarity, but also allows slow drift.
                flow = clamp((shifted_best - same + 0.08) * 3.0) * activity * complexity
                rotated_best = 0.0
                if window <= 16:  # cheap enough, and rotors are usually local
                    rotated_best = max(
                        rotated_window_similarity(prev, last, x0, y0, window, 90),
                        rotated_window_similarity(prev, last, x0, y0, window, 180),
                        rotated_window_similarity(prev, last, x0, y0, window, 270),
                    )
                rotation_flow = clamp((rotated_best - same + 0.06) * 3.2) * activity * complexity

                all_complexities.append(complexity)
                all_activities.append(activity)
                all_flows.append(flow)
                all_rot_flows.append(rotation_flow)
                hotspot_score = complexity * (0.35 + activity) * (0.55 + flow)
                if 0.03 < activity < 0.85 and hotspot_score > best[0]:
                    best = (hotspot_score, x0, y0, window)

    if not all_complexities:
        return {
            'ms_local_life': 0.0, 'ms_flow': 0.0, 'ms_rotation_flow': 0.0, 'ms_complexity': 0.0,
            'ms_activity': 0.0, 'ms_diversity': 0.0, 'best_hotspot_x': 0,
            'best_hotspot_y': 0, 'best_hotspot_size': 0, 'best_hotspot_score': 0.0,
        }
    c_avg = sum(all_complexities) / len(all_complexities)
    a_avg = sum(all_activities) / len(all_activities)
    f_avg = sum(all_flows) / len(all_flows)
    r_avg = sum(all_rot_flows) / len(all_rot_flows) if all_rot_flows else 0.0
    c_mean = c_avg
    diversity = clamp(sum((c - c_mean) ** 2 for c in all_complexities) / len(all_complexities) * 10.0)
    # Sweet spot: a few active windows, not a global storm.
    active_win_frac = sum(1 for a in all_activities if 0.04 < a < 0.85) / len(all_activities)
    localization = clamp(1.0 - abs(active_win_frac - 0.16) * 4.0)
    local_life = (
        0.24 * macro +
        0.22 * clamp(c_avg * 2.6) +
        0.20 * clamp(a_avg * 6.0) +
        0.14 * clamp(f_avg * 8.0) +
        0.04 * clamp(r_avg * 10.0) +
        0.10 * diversity +
        0.06 * localization
    )
    return {
        'ms_local_life': local_life,
        'ms_flow': f_avg,
        'ms_rotation_flow': r_avg,
        'ms_complexity': c_avg,
        'ms_activity': a_avg,
        'ms_diversity': diversity,
        'best_hotspot_x': best[1],
        'best_hotspot_y': best[2],
        'best_hotspot_size': best[3],
        'best_hotspot_score': best[0],
    }

def simple_entity_detector(prev, last, min_delta=0.008):
    """Detect connected moving blobs in the delta map.
    These are not 'creatures' yet, just candidate moving entities: walkers,
    pulsing defects, boundary packets, tiny reactors.
    """
    delta = [[abs(last[y][x] - prev[y][x]) for x in range(W)] for y in range(H)]
    seen = [[False] * W for _ in range(H)]
    comps = []
    for y in range(H):
        for x in range(W):
            if seen[y][x] or delta[y][x] <= min_delta:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            cells = []
            mass = 0.0
            sx = 0.0
            sy = 0.0
            edge_mass = 0.0
            while stack:
                px, py = stack.pop()
                d = delta[py][px]
                cells.append((px, py))
                mass += d
                sx += px * d
                sy += py * d
                e = 0.5 * (abs(last[py][px] - last[py][(px + 1) % W]) + abs(last[py][px] - last[(py + 1) % H][px]))
                edge_mass += e * d
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = (px + dx) % W, (py + dy) % H
                    if not seen[ny][nx] and delta[ny][nx] > min_delta:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(cells) >= 2:
                comps.append({
                    'size': len(cells),
                    'mass': mass,
                    'cx': sx / max(1e-9, mass) / W,
                    'cy': sy / max(1e-9, mass) / H,
                    'edge_affinity': edge_mass / max(1e-9, mass),
                })
    empty = {
        'entity_count': 0, 'entity_mass': 0.0, 'entity_score': 0.0, 'edge_entities': 0,
        'largest_entity': 0, 'best_entity_size': 0, 'best_entity_mass': 0.0,
        'best_entity_edge': 0.0, 'best_entity_x': 0.0, 'best_entity_y': 0.0,
        'best_entity_quality': 0.0,
    }
    if not comps:
        return empty
    good = [c for c in comps if 2 <= c['size'] <= 90]
    if not good:
        return empty
    edge_entities = sum(1 for c in good if c['edge_affinity'] > 0.06)
    total_mass = sum(c['mass'] for c in good) / (W * H)
    count_score = clamp(len(good) / 18.0)
    edge_score = clamp(edge_entities / 12.0)
    mass_score = clamp(total_mass * 190.0)
    size_balance = clamp(1.0 - abs((sum(c['size'] for c in good) / max(1, len(good))) - 14.0) / 32.0)
    entity_score = 0.32 * count_score + 0.28 * edge_score + 0.24 * mass_score + 0.16 * size_balance

    # Pick a single object worth watching. This prefers compact, non-trivial,
    # edge-affine moving blobs: walkers, pulsing defects, boundary packets.
    def quality(c):
        size_pref = clamp(1.0 - abs(c['size'] - 14.0) / 36.0)
        mass_pref = clamp(c['mass'] * 7.5)
        edge_pref = clamp(c['edge_affinity'] * 8.0)
        return 0.36 * size_pref + 0.34 * mass_pref + 0.30 * edge_pref

    best = max(good, key=quality)
    best_quality = quality(best)
    return {
        'entity_count': len(good),
        'entity_mass': total_mass,
        'entity_score': entity_score,
        'edge_entities': edge_entities,
        'largest_entity': max((c['size'] for c in good), default=0),
        'best_entity_size': best['size'],
        'best_entity_mass': best['mass'],
        'best_entity_edge': best['edge_affinity'],
        'best_entity_x': best['cx'],
        'best_entity_y': best['cy'],
        'best_entity_quality': best_quality,
    }



def _entity_components(prev, last, min_delta=0.008):
    """Return raw moving components from a delta map for tracking."""
    delta = [[abs(last[y][x] - prev[y][x]) for x in range(W)] for y in range(H)]
    seen = [[False] * W for _ in range(H)]
    comps = []
    for y in range(H):
        for x in range(W):
            if seen[y][x] or delta[y][x] <= min_delta:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            cells = []
            mass = 0.0
            sx = sy = 0.0
            edge_mass = 0.0
            while stack:
                px, py = stack.pop()
                d = delta[py][px]
                cells.append((px, py))
                mass += d
                sx += px * d
                sy += py * d
                e = 0.5 * (abs(last[py][px] - last[py][(px + 1) % W]) + abs(last[py][px] - last[(py + 1) % H][px]))
                edge_mass += e * d
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = (px + dx) % W, (py + dy) % H
                    if not seen[ny][nx] and delta[ny][nx] > min_delta:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if 2 <= len(cells) <= 120 and mass > 0:
                comps.append({
                    'size': len(cells),
                    'mass': mass,
                    'cx': sx / mass / W,
                    'cy': sy / mass / H,
                    'edge_affinity': edge_mass / max(1e-9, mass),
                })
    return comps


def persistent_entity_tracker(frames, min_delta=0.008):
    """Very light 2-3 sample tracker.
    It does not try to identify life perfectly. It asks whether moving delta blobs
    persist across several sampled frames with plausible velocity inheritance.
    """
    empty = {
        'persistent_entity_score': 0.0, 'persistent_tracks': 0,
        'best_track_age': 0, 'best_track_speed': 0.0, 'best_track_edge': 0.0,
        'best_track_size': 0, 'best_track_quality': 0.0,
    }
    if len(frames) < 4:
        return empty
    comp_series = [_entity_components(frames[i-1], frames[i], min_delta) for i in range(1, len(frames))]
    tracks = []
    # Seed tracks from the first few samples.
    for c in comp_series[0]:
        tracks.append({'last': c, 'age': 1, 'speed_sum': 0.0, 'edge_sum': c['edge_affinity'], 'size_sum': c['size'], 'miss': 0})
    for comps in comp_series[1:]:
        used = set()
        for tr in tracks:
            lx, ly = tr['last']['cx'], tr['last']['cy']
            best_i = None
            best_d = 999.0
            for i, c in enumerate(comps):
                if i in used:
                    continue
                dx = abs(c['cx'] - lx); dx = min(dx, 1.0 - dx)
                dy = abs(c['cy'] - ly); dy = min(dy, 1.0 - dy)
                d = (dx*dx + dy*dy) ** 0.5
                size_ratio = c['size'] / max(1, tr['last']['size'])
                if d < 0.18 and 0.25 < size_ratio < 4.0 and d < best_d:
                    best_i = i; best_d = d
            if best_i is not None:
                c = comps[best_i]
                used.add(best_i)
                tr['age'] += 1
                tr['speed_sum'] += best_d
                tr['edge_sum'] += c['edge_affinity']
                tr['size_sum'] += c['size']
                tr['last'] = c
                tr['miss'] = 0
            else:
                tr['miss'] += 1
        for i, c in enumerate(comps):
            if i not in used:
                tracks.append({'last': c, 'age': 1, 'speed_sum': 0.0, 'edge_sum': c['edge_affinity'], 'size_sum': c['size'], 'miss': 0})
        tracks = [t for t in tracks if t['miss'] <= 1]
    good = [t for t in tracks if t['age'] >= 2]
    if not good:
        return empty
    def q(t):
        age = clamp(t['age'] / 4.0)
        avg_speed = t['speed_sum'] / max(1, t['age'] - 1)
        speed_pref = clamp(1.0 - abs(avg_speed - 0.035) / 0.09)
        edge_pref = clamp((t['edge_sum'] / max(1, t['age'])) * 8.0)
        size_avg = t['size_sum'] / max(1, t['age'])
        size_pref = clamp(1.0 - abs(size_avg - 16.0) / 42.0)
        return 0.35 * age + 0.25 * speed_pref + 0.22 * edge_pref + 0.18 * size_pref
    best = max(good, key=q)
    best_q = q(best)
    persistent_score = clamp((sum(q(t) for t in good) / max(1, len(good))) * 0.65 + clamp(len(good) / 8.0) * 0.35)
    return {
        'persistent_entity_score': persistent_score,
        'persistent_tracks': len(good),
        'best_track_age': best['age'],
        'best_track_speed': best['speed_sum'] / max(1, best['age'] - 1),
        'best_track_edge': best['edge_sum'] / max(1, best['age']),
        'best_track_size': int(best['size_sum'] / max(1, best['age'])),
        'best_track_quality': best_q,
    }

def window_stats(frame, x0, y0, window):
    vals = []
    edge_sum = 0.0
    for yy in range(y0, y0 + window):
        for xx in range(x0, x0 + window):
            v = frame[yy][xx]
            vals.append(v)
            if xx + 1 < x0 + window:
                edge_sum += abs(frame[yy][xx] - frame[yy][xx + 1])
            if yy + 1 < y0 + window:
                edge_sum += abs(frame[yy][xx] - frame[yy + 1][xx])
    n = window * window
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    edge = edge_sum / max(1, 2 * window * (window - 1))
    return mean, var, edge

def window_delta(a, b, x0, y0, window):
    total = 0.0
    for yy in range(y0, y0 + window):
        for xx in range(x0, x0 + window):
            total += abs(b[yy][xx] - a[yy][xx])
    return total / (window * window)

def regional_dynamics_detector(frames, windows=(8, 16, 24, 32), strides=(4, 8, 12, 16)):
    """Detect locally unusual dynamics, not only connected delta blobs.

    This is closer to what a human observer noticed: moving boundaries,
    pulsing seams, absorbers, little walkers inside a larger scaffold.
    A region scores high when it has:
      - structure now,
      - persistent but localized change across several snapshots,
      - motion/flow rather than pure flicker,
      - contrast against the global background.
    """
    zero = {
        'region_score': 0.0, 'region_count': 0, 'region_flow': 0.0,
        'region_activity': 0.0, 'region_structure': 0.0,
        'best_region_score': 0.0, 'best_region_x': 0, 'best_region_y': 0,
        'best_region_size': 0, 'best_region_flow': 0.0,
        'best_region_activity': 0.0, 'best_region_structure': 0.0,
    }
    if len(frames) < 4:
        return zero
    # Use the last few snapshots, because the latest attractor/dynamics matters most.
    fs = frames[-min(6, len(frames)):]
    last = fs[-1]
    prev = fs[-2]

    # Global activity baseline between recent frames.
    global_delta = 0.0
    pairs = 0
    for i in range(1, len(fs)):
        pairs += 1
        for y in range(H):
            for x in range(W):
                global_delta += abs(fs[i][y][x] - fs[i - 1][y][x])
    global_activity = global_delta / max(1, pairs * W * H)

    region_scores = []
    flows = []
    acts = []
    structs = []
    best = zero.copy()

    for window, stride in zip(windows, strides):
        if window > W or window > H:
            continue
        for y0 in range(0, H - window + 1, stride):
            for x0 in range(0, W - window + 1, stride):
                # Recent activity history in the same local window.
                deltas = [window_delta(fs[i - 1], fs[i], x0, y0, window) for i in range(1, len(fs))]
                if not deltas:
                    continue
                act_avg = sum(deltas) / len(deltas)
                act_max = max(deltas)
                act_min = min(deltas)
                # Persistent local activity: not just one-frame spark.
                persistence = clamp(act_min / max(1e-8, act_avg)) if act_avg > 0 else 0.0

                _, var, edge = window_stats(last, x0, y0, window)
                structure = clamp(var * 11.0 + edge * 3.0)

                same = shifted_window_similarity(prev, last, x0, y0, window, 0, 0)
                shifted_best = 0.0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        shifted_best = max(shifted_best, shifted_window_similarity(prev, last, x0, y0, window, dx, dy))
                flow = clamp((shifted_best - same + 0.06) * 3.6)

                # We want local activity above the world baseline, but not full-window noise.
                contrast = clamp((act_avg - global_activity * 0.85) * 95.0)
                sweet_activity = clamp(1.0 - abs(act_avg - 0.012) / 0.035)
                not_noise = clamp(1.0 - max(0.0, act_max - 0.08) * 9.0)

                # Boundaries and agents are often small but persistent: reward the best region,
                # not the global average.
                score = (
                    0.28 * structure +
                    0.22 * contrast +
                    0.18 * persistence +
                    0.18 * flow +
                    0.14 * sweet_activity
                ) * not_noise

                # Ignore completely static/dead windows and global storms.
                if act_avg < 0.00035 or structure < 0.015:
                    score = 0.0

                region_scores.append(score)
                flows.append(flow * score)
                acts.append(act_avg * score)
                structs.append(structure * score)
                if score > best['best_region_score']:
                    best.update({
                        'best_region_score': score,
                        'best_region_x': x0,
                        'best_region_y': y0,
                        'best_region_size': window,
                        'best_region_flow': flow,
                        'best_region_activity': act_avg,
                        'best_region_structure': structure,
                    })

    if not region_scores:
        return zero
    top = sorted(region_scores, reverse=True)[:12]
    region_score = sum(top) / max(1, len(top))
    count = sum(1 for s in region_scores if s > 0.25)
    weight_sum = max(1e-9, sum(region_scores))
    return {
        'region_score': region_score,
        'region_count': count,
        'region_flow': sum(flows) / weight_sum,
        'region_activity': sum(acts) / weight_sum,
        'region_structure': sum(structs) / weight_sum,
        **{k: best[k] for k in best if k.startswith('best_region_')},
    }


def load_human_favorites():
    """Rules manually liked in the viewer.  These are reintroduced as seed organisms."""
    try:
        if HUMAN_FAV_FILE.exists():
            data = json.loads(HUMAN_FAV_FILE.read_text(encoding='utf-8'))
            return [rule_from_dict(item['rule']) for item in data if 'rule' in item]
    except Exception as e:
        print('Warning: could not load human favorites:', e)
    return []

def save_human_favorite(rule, note='liked in viewer'):
    OUT_DIR.mkdir(exist_ok=True)
    items = []
    try:
        if HUMAN_FAV_FILE.exists():
            items = json.loads(HUMAN_FAV_FILE.read_text(encoding='utf-8'))
    except Exception:
        items = []
    fp = json.dumps(rule_to_dict(rule), sort_keys=True)
    if any(json.dumps(x.get('rule', {}), sort_keys=True) == fp for x in items):
        return False
    items.append({'note': note, 'rule': rule_to_dict(rule)})
    HUMAN_FAV_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')
    return True

def rule_signature(rule):
    """Compact signature for exact human-favorite bonus."""
    d = rule_to_dict(rule)
    d.pop('rule_id', None); d.pop('parent_a', None); d.pop('parent_b', None)
    return json.dumps(d, sort_keys=True)

def apply_cosmic_ray(sim, radius=COSMIC_RADIUS, strength=COSMIC_STRENGTH, rng=None):
    """Local disturbance: a small energy burst to test recovery/regeneration."""
    rng = rng or random
    width = sim.width
    height = sim.height
    cx = rng.randrange(width)
    cy = rng.randrange(height)
    r2 = radius * radius
    changed = 0
    for yy in range(cy - radius, cy + radius + 1):
        for xx in range(cx - radius, cx + radius + 1):
            dx = xx - cx; dy = yy - cy
            if dx*dx + dy*dy <= r2:
                x = xx % width; y = yy % height
                falloff = 1.0 - math.sqrt(dx*dx + dy*dy) / max(1, radius)
                kick = (rng.random() - 0.5) * strength * (0.35 + 0.65 * falloff)
                sim.a[y][x] = clamp(sim.a[y][x] + kick)
                sim.v[y][x] += kick * 0.06
                sim.trace[y][x] = max(sim.trace[y][x], abs(kick))
                changed += 1
    return {'cosmic_x': cx, 'cosmic_y': cy, 'cosmic_changed': changed}

def cosmic_recovery_score(before, after, later):
    """Rewards worlds that absorb disturbance without becoming dead, soup, or pure chaos."""
    if before is None or after is None or later is None:
        return 0.0, {'cosmic_recovery': 0.0, 'cosmic_damage': 0.0, 'cosmic_resilience': 0.0}
    damage = 1.0 - frame_similarity(before, after)
    recovered = frame_similarity(before, later)
    still_changed = 1.0 - frame_similarity(after, later)
    # good: disturbance matters, then structure partially returns, but not perfectly erased
    damage_sweet = clamp(1.0 - abs(damage - 0.055) / 0.11)
    recovery = clamp((recovered - 0.72) * 3.2)
    residual_life = clamp(still_changed * 7.5)
    score = 0.45 * damage_sweet + 0.35 * recovery + 0.20 * residual_life
    return score, {'cosmic_recovery': score, 'cosmic_damage': damage, 'cosmic_resilience': recovered}


def score_rule(
    rule,
    mode='balanced',
    collect_frames=False,
    max_ticks=None,
    *,
    width=W,
    height=H,
    topology="torus",
    boundary_mode="wrap",
):
    local_ticks = int(max_ticks or TICKS)
    sim = FieldSim(
        rule,
        width=width,
        height=height,
        topology=topology,
        boundary_mode=boundary_mode,
    )
    samples = []
    frames = []
    snapshots = []
    cosmic_before = cosmic_after = cosmic_later = None
    cosmic_info = {}
    cosmic_steps = {int(local_ticks * f) for f in COSMIC_TICKS} if (COSMIC_RAYS and mode in ('cosmic_curator', 'stress_test', 'adaptive_observer', 'hierarchical_novelty', 'emergent_ecology', 'coevolution')) else set()
    first_cosmic = min(cosmic_steps) if cosmic_steps else None
    later_step = (first_cosmic + max(120, SAMPLE_EVERY)) if first_cosmic is not None else None
    for i in range(local_ticks):
        if i in cosmic_steps:
            if cosmic_before is None:
                cosmic_before = [row[:] for row in sim.a]
            cosmic_info.update(apply_cosmic_ray(sim))
            if cosmic_after is None:
                cosmic_after = [row[:] for row in sim.a]
        sim.step()
        if later_step is not None and i == later_step:
            cosmic_later = [row[:] for row in sim.a]
        if i % SAMPLE_EVERY == 0 or i == local_ticks - 1:
            m = sim.metrics(); sm = sim.scale_metrics(); islands, biggest, _ = sim.islands()
            m.update(sm); m['islands'] = islands; m['biggest'] = biggest
            samples.append(m)
            snap = [row[:] for row in sim.a]
            snapshots.append(snap)
            if collect_frames:
                frames.append(snap)
    last = samples[-1]
    tail = samples[-6:]
    avg_motion = sum(s['motion'] for s in tail) / min(6, len(samples))
    avg_activity = sum(s['activity'] for s in tail) / min(6, len(samples))
    avg_boundary_activity = sum(s['boundary_activity'] for s in tail) / min(6, len(samples))
    active = last['active']
    edge = last['edge']
    islands = last['islands']
    biggest = last['biggest'] / (W * H)
    small = last['small_texture']; mid = last['mid_texture']; large = last['large_order']; gap = last['scale_gap']
    boundary_fraction = last['boundary_fraction']
    memory_similarity = frame_similarity(snapshots[1], snapshots[-1]) if len(snapshots) > 2 else 0.0
    centroid_flow = centroid_path_score(tail)
    motion_stability = 1.0 - clamp(temporal_variance(tail, 'activity') * 7000)
    hot_fraction = sum(s.get('hot_fraction', 0.0) for s in tail) / min(6, len(samples))
    old_fraction = last.get('old_fraction', 0.0)
    nested = nested_window_metrics(snapshots, window=12, stride=6)
    nested_raw = nested['nested_score_raw']
    ms_life = multi_scale_local_life(snapshots)
    entities = simple_entity_detector(snapshots[-2], snapshots[-1]) if len(snapshots) >= 2 else simple_entity_detector(snapshots[-1], snapshots[-1])
    persistent = persistent_entity_tracker(snapshots)
    regions = regional_dynamics_detector(snapshots)
    cosmic_score, cosmic_metrics = cosmic_recovery_score(cosmic_before, cosmic_after, cosmic_later or (snapshots[-1] if snapshots else None))
    localized_activity = clamp(1.0 - abs(hot_fraction - 0.025) * 18.0)

    survival = 1.0 - abs(active - 0.28) * 2.2
    not_dead = 1.0 if 0.03 < active < 0.75 else 0.12
    balance = max(0.0, survival) * 42 + min(edge * 260, 34) + min(avg_motion * 550, 24)
    novelty = min(abs(last['mean'] - 0.5) * 55 + edge * 230 + islands * 0.9, 115)
    motion_score = min(avg_motion * 1700 + edge * 140 + active * 18, 120)
    islands_score = min(islands * 1.8 + biggest * 100 + edge * 110, 130)
    boundaries_score = min(edge * 360 + small * 600 + min(islands, 35), 135)

    scale_score = 100 * not_dead
    scale_score += min(small * 900, 35)
    scale_score += min(mid * 540, 30)
    scale_score += min(large * 780, 34)
    scale_score += min(gap * 520, 28)
    scale_score += min(edge * 160, 22)
    scale_score += min(avg_motion * 700, 18)
    scale_score -= max(0, biggest - 0.55) * 80

    # Looks for what you observed: stable domains + living edges + small walkers/defects.
    # It prefers localized motion, not global noise.
    localization = avg_boundary_activity / max(1e-6, avg_activity)
    living_boundaries = 40 * not_dead
    living_boundaries += min(edge * 220, 35)
    living_boundaries += min(boundary_fraction * 90, 22)
    living_boundaries += min(avg_boundary_activity * 9000, 28)
    living_boundaries += min(localization * 6, 18)
    living_boundaries += min(gap * 330, 18)
    living_boundaries -= max(0, avg_activity - 0.015) * 900    # too much whole-field flicker is noise
    living_boundaries -= max(0, biggest - 0.72) * 55

    # More aggressive mode: specifically hunts transport on boundaries.
    edge_transport = 30 * not_dead
    edge_transport += min(edge * 180, 28)
    edge_transport += min(avg_boundary_activity * 13000, 40)
    edge_transport += min(localization * 9, 28)
    edge_transport += min(boundary_fraction * 65, 18)
    edge_transport -= max(0, avg_activity - 0.012) * 1100

    # Broad emergence: many ways to be interesting, not only living boundaries.
    memory_score = 35 * not_dead
    memory_score += min(memory_similarity * 38, 38)
    memory_score += min(edge * 150, 24)
    memory_score += min(old_fraction * 35, 24)
    memory_score += min(avg_activity * 2500, 18)
    memory_score -= max(0, avg_activity - 0.02) * 700

    information_flow = 28 * not_dead
    information_flow += min(centroid_flow * 42, 42)
    information_flow += min(localization * 7, 22)
    information_flow += min(avg_boundary_activity * 10000, 30)
    information_flow += min(edge * 100, 16)
    information_flow -= max(0, hot_fraction - 0.12) * 180

    stable_movers = 25 * not_dead
    stable_movers += min(memory_similarity * 24, 24)        # stable scaffold
    stable_movers += min(centroid_flow * 35, 35)            # something travels
    stable_movers += min(localized_activity * 26, 26)       # not whole-field flicker
    stable_movers += min(avg_activity * 3200, 22)
    stable_movers += min(edge * 80, 12)

    hierarchy = 30 * not_dead
    hierarchy += min(small * 850, 28)
    hierarchy += min(mid * 520, 24)
    hierarchy += min(large * 720, 26)
    hierarchy += min(gap * 420, 22)
    hierarchy += min(edge * 135, 18)
    hierarchy += min(memory_similarity * 18, 18)
    hierarchy += min(avg_boundary_activity * 5000, 15)
    hierarchy -= max(0, biggest - 0.68) * 45

    # Nested complexity: macro-order with small local life inside it.
    nested_complexity = 20 * not_dead
    nested_complexity += min(nested_raw * 85, 85)
    nested_complexity += min(memory_similarity * 18, 18)
    nested_complexity += min(edge * 85, 16)
    nested_complexity -= max(0, active - 0.88) * 180
    nested_complexity -= max(0, avg_activity - 0.035) * 520

    # Emergent ecology: do not judge the whole universe as one picture.
    # It rewards active local places inside a persistent larger world.
    local_life = 22 * not_dead
    local_life += min(ms_life['ms_local_life'] * 95, 95)
    local_life += min(ms_life['best_hotspot_score'] * 40, 24)
    local_life += min(memory_similarity * 14, 14)
    local_life -= max(0, active - 0.88) * 160
    local_life -= max(0, avg_activity - 0.045) * 430

    flow_score = 18 * not_dead
    flow_score += min(ms_life['ms_flow'] * 850, 42)
    flow_score += min(ms_life.get('ms_rotation_flow', 0.0) * 850, 24)
    flow_score += min(centroid_flow * 28, 28)
    flow_score += min(avg_boundary_activity * 7000, 22)
    flow_score += min(localized_activity * 18, 18)
    flow_score -= max(0, hot_fraction - 0.16) * 170

    entity_mode = 18 * not_dead
    entity_mode += min(entities['entity_score'] * 64, 64)
    entity_mode += min(persistent['persistent_entity_score'] * 62, 42)
    entity_mode += min(entities['edge_entities'] * 2.2, 20)
    entity_mode += min(persistent['persistent_tracks'] * 2.8, 24)
    entity_mode += min(ms_life['ms_local_life'] * 35, 35)
    entity_mode -= max(0, entities['entity_count'] - 70) * 1.2
    entity_mode -= max(0, active - 0.90) * 150

    # Region dynamics: looks for locally unusual processes inside a macro world.
    # This is not a blob detector; it rewards windows where the behavior differs
    # from the surrounding scaffold: crawling seams, pulsing defects, absorbers, channels.
    region_dynamics = 16 * not_dead
    region_dynamics += min(regions['region_score'] * 115, 115)
    region_dynamics += min(regions['best_region_score'] * 60, 38)
    region_dynamics += min(regions['region_flow'] * 45, 28)
    region_dynamics += min(regions['region_count'] * 1.2, 24)
    region_dynamics += min(memory_similarity * 10, 10)
    region_dynamics -= max(0, active - 0.91) * 170
    region_dynamics -= max(0, avg_activity - 0.065) * 380

    # Macro scaffold: stable large-scale stage where local processes can live.
    macro_scaffold = 18 * not_dead
    macro_scaffold += min(memory_similarity * 34, 34)
    macro_scaffold += min(edge * 165, 28)
    macro_scaffold += min(boundary_fraction * 70, 18)
    macro_scaffold += min(gap * 310, 18)
    macro_scaffold -= max(0, active - 0.88) * 170
    macro_scaffold -= max(0, avg_activity - 0.055) * 260

    # Memory trace: rewards worlds where recent events leave localized fading traces,
    # not a global storm and not total stillness.
    trace_mass = last.get('trace_mass', 0.0)
    trace_hot = last.get('trace_hot', 0.0)
    trace_edge = last.get('trace_edge', 0.0)
    trace_localized = clamp(1.0 - abs(trace_hot - 0.08) * 7.0)
    memory_trace_score = 18 * not_dead
    memory_trace_score += min(trace_mass * 120, 36)
    memory_trace_score += min(trace_edge * 390, 48)
    memory_trace_score += min(trace_localized * 36, 36)
    memory_trace_score += min(memory_similarity * 20, 20)
    memory_trace_score -= max(0, trace_hot - 0.34) * 120

    # Hierarchical local ecology: macro stage + local regions + entities/flow.
    hierarchical_local = (
        0.23 * macro_scaffold +
        0.22 * region_dynamics +
        0.17 * local_life +
        0.12 * flow_score +
        0.12 * entity_mode +
        0.18 * memory_trace_score
    )

    emergent_ecology = (
        0.18 * hierarchical_local +
        0.18 * region_dynamics +
        0.18 * local_life +
        0.15 * flow_score +
        0.12 * entity_mode +
        0.09 * nested_complexity +
        0.06 * hierarchy +
        0.04 * memory_trace_score
    )

    cosmic_curator = (
        0.24 * hierarchical_local +
        0.18 * region_dynamics +
        0.16 * local_life +
        0.14 * flow_score +
        0.12 * entity_mode +
        0.12 * memory_trace_score +
        42.0 * cosmic_score
    )

    stress_test = (
        0.34 * macro_scaffold +
        0.24 * memory_trace_score +
        0.20 * region_dynamics +
        0.22 * local_life +
        58.0 * cosmic_score
    )

    emergence = (
        0.16 * scale_score +
        0.15 * memory_score +
        0.14 * information_flow +
        0.14 * stable_movers +
        0.15 * hierarchy +
        0.12 * living_boundaries +
        0.14 * nested_complexity
    )

    # Degenerate-world guardrails.
    # Prevents the search from rewarding boring attractors such as:
    #   - fully saturated soup: active ~= 1, edge ~= 0
    #   - dead empty field: active ~= 0
    #   - one smooth island with no boundaries or boundary activity
    degeneracy_penalty = 0.0
    degeneracy_penalty += max(0.0, active - 0.86) * 260.0
    degeneracy_penalty += max(0.0, 0.035 - edge) * 1400.0
    degeneracy_penalty += max(0.0, 0.00012 - avg_boundary_activity) * 120000.0
    degeneracy_penalty += max(0.0, biggest - 0.82) * 95.0
    if active > 0.92 and edge < 0.05:
        degeneracy_penalty += 95.0
    # v0.9.1 stable-soup hammer: motion inside a smooth saturated field is not life.
    if active > 0.95 and edge < 0.03:
        degeneracy_penalty += 180.0 + max(0.0, active - 0.95) * 700.0 + max(0.0, 0.03 - edge) * 2600.0
    if active > 0.985 and edge < 0.012:
        degeneracy_penalty += 220.0
    if active < 0.02:
        degeneracy_penalty += 90.0

    # Adaptive guardrails: boring soup gets the full hammer, but strange worlds with
    # local life, flow, memory traces, persistent entities or unusual regions get a softer hit.
    interestingness = clamp(
        0.22 * nested_raw +
        0.18 * ms_life['ms_local_life'] +
        0.13 * ms_life['ms_flow'] +
        0.09 * ms_life.get('ms_rotation_flow', 0.0) +
        0.13 * memory_trace_score / 120.0 +
        0.13 * regions['region_score'] +
        0.12 * persistent['persistent_entity_score']
    )
    adaptive_penalty_scale = 1.0 - 0.68 * interestingness
    degeneracy_penalty_raw = degeneracy_penalty
    degeneracy_penalty *= adaptive_penalty_scale

    # Apply mostly to the broad/new modes. Old modes stay comparable with previous runs.
    scale_score -= degeneracy_penalty * 0.55
    living_boundaries -= degeneracy_penalty * 0.75
    edge_transport -= degeneracy_penalty * 0.75
    memory_score -= degeneracy_penalty * 0.55
    information_flow -= degeneracy_penalty * 0.70
    stable_movers -= degeneracy_penalty * 0.70
    hierarchy -= degeneracy_penalty * 0.55
    nested_complexity -= degeneracy_penalty * 0.60
    local_life -= degeneracy_penalty * 0.65
    flow_score -= degeneracy_penalty * 0.65
    entity_mode -= degeneracy_penalty * 0.70
    region_dynamics -= degeneracy_penalty * 0.65
    macro_scaffold -= degeneracy_penalty * 0.45
    memory_trace_score -= degeneracy_penalty * 0.55
    hierarchical_local -= degeneracy_penalty * 0.65
    emergent_ecology -= degeneracy_penalty * 0.85
    cosmic_curator -= degeneracy_penalty * 0.72
    stress_test -= degeneracy_penalty * 0.66
    emergence -= degeneracy_penalty

    # Add derived diagnostics to the visible metrics saved in JSON.
    last['memory_similarity'] = memory_similarity
    last['centroid_flow'] = centroid_flow
    last['motion_stability'] = motion_stability
    last['hot_fraction'] = hot_fraction
    last['old_fraction'] = old_fraction
    last['localized_activity'] = localized_activity
    last.update(nested)
    last.update(ms_life)
    last.update(entities)
    last.update(persistent)
    last.update(regions)
    last.update(cosmic_metrics)
    last.update(cosmic_info)
    # Human-readable observation hints for the console and JSON logs.
    if persistent.get('persistent_tracks', 0) > 0:
        last['observer_note'] = (
            f"track age={persistent.get('best_track_age',0)} "
            f"size={persistent.get('best_track_size',0)} "
            f"speed={persistent.get('best_track_speed',0.0):.3f} "
            f"edge={persistent.get('best_track_edge',0.0):.3f}"
        )
    elif entities.get('entity_count', 0) > 0:
        last['observer_note'] = (
            f"object size={entities.get('best_entity_size',0)} "
            f"mass={entities.get('best_entity_mass',0.0):.3f} "
            f"edge={entities.get('best_entity_edge',0.0):.3f} "
            f"at=({entities.get('best_entity_x',0.0):.2f},{entities.get('best_entity_y',0.0):.2f})"
        )
    elif ms_life.get('best_hotspot_score', 0.0) > 0.05:
        last['observer_note'] = (
            f"hotspot x={ms_life.get('best_hotspot_x',0)} "
            f"y={ms_life.get('best_hotspot_y',0)} "
            f"size={ms_life.get('best_hotspot_size',0)} "
            f"score={ms_life.get('best_hotspot_score',0.0):.3f}"
        )
    else:
        last['observer_note'] = 'no clear local object'
    last['degeneracy_penalty_raw'] = degeneracy_penalty_raw
    last['degeneracy_penalty_scale'] = adaptive_penalty_scale
    last['interestingness'] = interestingness
    last['degeneracy_penalty'] = degeneracy_penalty
    last['macro_scaffold'] = macro_scaffold
    last['memory_trace_score'] = memory_trace_score
    last['hierarchical_local'] = hierarchical_local

    scores = {
        'balanced': balance,
        'novelty': novelty,
        'motion': motion_score,
        'islands': islands_score,
        'boundaries': boundaries_score,
        'scale_genesis': scale_score,
        'living_boundaries': living_boundaries,
        'edge_transport': edge_transport,
        'emergence': emergence,
        'nested_complexity': nested_complexity,
        'memory': memory_score,
        'information_flow': information_flow,
        'stable_movers': stable_movers,
        'hierarchy': hierarchy,
        'emergent_ecology': emergent_ecology,
        'observer_log': emergent_ecology,
        'entity_mode': entity_mode,
        'local_life': local_life,
        'flow': flow_score,
        'region_dynamics': region_dynamics,
        'macro_scaffold': macro_scaffold,
        'memory_trace': memory_trace_score,
        'hierarchical_novelty': hierarchical_local,
        'adaptive_observer': hierarchical_local,
        'cosmic_curator': cosmic_curator,
        'stress_test': stress_test,
    }
    return scores.get(mode, balance), last, frames



def metric_feature_vector(metrics):
    """Small fingerprint of a world's behavior for novelty preservation."""
    keys = [
        'active', 'edge', 'boundary_activity', 'boundary_fraction', 'islands',
        'nested_score_raw', 'ms_local_life', 'ms_flow', 'entity_score',
        'best_entity_quality', 'region_score', 'best_region_score',
        'region_flow', 'trace_mass', 'trace_edge', 'macro_scaffold',
        'ms_rotation_flow', 'persistent_entity_score', 'persistent_tracks',
    ]
    vals = []
    for k in keys:
        v = metrics.get(k, 0.0)
        if k == 'islands':
            v = math.log1p(v) / 8.0
        elif k == 'boundary_activity':
            v = min(1.0, v * 40.0)
        elif k in ('trace_mass', 'trace_edge'):
            v = min(1.0, v * 8.0)
        elif k in ('macro_scaffold',):
            v = min(1.0, max(0.0, v / 120.0))
        vals.append(float(v))
    return vals

def novelty_from_archive(vec, archive):
    """Distance to nearest previous behavior fingerprint. 0=already seen, 1=very new."""
    if not archive:
        return 1.0
    best = 999.0
    for other in archive[-400:]:
        d = math.sqrt(sum((a-b)*(a-b) for a,b in zip(vec, other)) / max(1, len(vec)))
        if d < best:
            best = d
    return clamp(best * 2.8)


OBSERVER_FEATURES = [
    'macro_scaffold', 'best_region_score', 'region_score', 'ms_local_life',
    'ms_flow', 'ms_rotation_flow', 'memory_trace_score', 'persistent_entity_score',
    'best_entity_quality', 'nested_score_raw', 'cosmic_recovery', 'edge',
    'boundary_activity', 'novelty_behavior', 'in_generation_diversity'
]

OBSERVER_ARCHIVE_FILE = OUT_DIR / 'observer_profiles.json'

def make_observer_profile(observer_id=0, archetype=None):
    """A tiny evolvable taste-function. It does not change physics, only how worlds are judged."""
    if archetype == 'scaffold':
        weights = {'macro_scaffold':1.2, 'nested_score_raw':0.7, 'edge':0.5, 'memory_trace_score':0.5}
    elif archetype == 'life':
        weights = {'ms_local_life':1.2, 'best_region_score':1.0, 'persistent_entity_score':0.7, 'best_entity_quality':0.5}
    elif archetype == 'flow':
        weights = {'ms_flow':1.2, 'ms_rotation_flow':1.0, 'boundary_activity':0.7, 'region_score':0.5}
    elif archetype == 'memory':
        weights = {'memory_trace_score':1.2, 'cosmic_recovery':0.8, 'macro_scaffold':0.7, 'persistent_entity_score':0.5}
    elif archetype == 'novelty':
        weights = {'novelty_behavior':1.2, 'in_generation_diversity':0.9, 'region_score':0.5, 'ms_local_life':0.5}
    else:
        weights = {k: random.random() for k in OBSERVER_FEATURES}
    for k in OBSERVER_FEATURES:
        weights.setdefault(k, random.uniform(0.0, 0.35))
    ssum = sum(abs(v) for v in weights.values()) or 1.0
    weights = {k: clamp(v / ssum * 5.0, 0.0, 1.4) for k, v in weights.items()}
    return {'id': observer_id, 'weights': weights, 'fitness': 0.0, 'age': 0, 'archetype': archetype or 'random'}

def normalize_observer_feature(k, metrics):
    v = metrics.get(k, 0.0)
    if k in ('macro_scaffold', 'memory_trace_score'):
        return clamp(max(0.0, v) / 120.0)
    if k in ('ms_flow', 'ms_rotation_flow', 'boundary_activity'):
        return clamp(v * (950.0 if k != 'boundary_activity' else 50.0))
    if k in ('persistent_entity_score', 'best_entity_quality', 'best_region_score', 'region_score', 'nested_score_raw', 'cosmic_recovery', 'edge', 'novelty_behavior', 'in_generation_diversity', 'ms_local_life'):
        return clamp(v)
    return clamp(v)

def observer_score(profile, metrics):
    weights = profile.get('weights', {})
    val = 0.0
    for k, w in weights.items():
        val += w * normalize_observer_feature(k, metrics)
    # Observers are allowed to prefer strange worlds, but they should dislike pure soup.
    active = metrics.get('active', 0.0); edge = metrics.get('edge', 0.0)
    if active > 0.96 and edge < 0.035:
        val *= 0.42
    if active < 0.02:
        val *= 0.35
    return val * 34.0

def mutate_observer_profile(parent, new_id):
    child = {'id': new_id, 'weights': dict(parent.get('weights', {})), 'fitness': 0.0, 'age': parent.get('age',0)+1, 'archetype': parent.get('archetype','mutant')}
    for k in OBSERVER_FEATURES:
        x = child['weights'].get(k, 0.0)
        if random.random() < 0.85:
            x += random.gauss(0, 0.16)
        if random.random() < 0.05:
            x = random.random() * 1.2
        child['weights'][k] = clamp(x, 0.0, 1.6)
    ssum = sum(abs(v) for v in child['weights'].values()) or 1.0
    child['weights'] = {k: clamp(v / ssum * 5.0, 0.0, 1.6) for k, v in child['weights'].items()}
    return child

def make_observer_population():
    archetypes = ['scaffold', 'life', 'flow', 'memory', 'novelty']
    obs=[]
    for i, a in enumerate(archetypes):
        obs.append(make_observer_profile(i, a))
    while len(obs) < OBSERVER_COUNT:
        obs.append(make_observer_profile(len(obs)))
    return obs

def evolve_observers(observers, top_metrics, next_obs_id):
    # Fitness: observers survive if their taste assigns high scores to the best worlds that generation.
    for o in observers:
        if top_metrics:
            o['fitness'] = sum(observer_score(o, m) for m in top_metrics[:min(KEEP_TOP, len(top_metrics))]) / min(KEEP_TOP, len(top_metrics))
        else:
            o['fitness'] = 0.0
    observers.sort(key=lambda z: z.get('fitness',0.0), reverse=True)
    elites = [dict(o, weights=dict(o['weights'])) for o in observers[:OBSERVER_ELITES]]
    new_obs = elites[:]
    while len(new_obs) < OBSERVER_COUNT:
        parent = random.choice(elites)
        new_obs.append(mutate_observer_profile(parent, next_obs_id)); next_obs_id += 1
    return new_obs, next_obs_id


def post_test_truth_score(metrics):
    """A harsher 'does this world remain interesting after stress?' score.
    This is the teacher signal for observers.  It rewards worlds that keep structure,
    local life, memory, objects, and recovery after cosmic rays, while avoiding soup.
    """
    active = metrics.get('active', 0.0)
    edge = metrics.get('edge', 0.0)
    soup = 1.0 if (active > 0.96 and edge < 0.04) else 0.0
    dead = 1.0 if active < 0.02 else 0.0
    viable = clamp(1.0 - soup - dead)
    val = 0.0
    val += 0.20 * clamp(metrics.get('macro_scaffold', 0.0) / 120.0)
    val += 0.18 * clamp(metrics.get('ms_local_life', 0.0))
    val += 0.16 * clamp(metrics.get('best_region_score', 0.0))
    val += 0.14 * clamp(metrics.get('persistent_entity_score', 0.0))
    val += 0.12 * clamp(metrics.get('memory_trace_score', 0.0) / 120.0)
    val += 0.12 * clamp(metrics.get('cosmic_recovery', 0.0))
    val += 0.08 * clamp(metrics.get('ms_flow', 0.0) * 900.0 + metrics.get('ms_rotation_flow', 0.0) * 500.0)
    return 100.0 * val * viable


def observer_weight_vector(obs):
    w = obs.get('weights', {})
    return [float(w.get(k, 0.0)) for k in OBSERVER_FEATURES]

def observer_distance(a, b):
    av = observer_weight_vector(a); bv = observer_weight_vector(b)
    return math.sqrt(sum((x-y)*(x-y) for x, y in zip(av, bv)) / max(1, len(av)))

def observer_diversity_strength_for_gen(gen=None):
    """Strong diversity early, softer late, so observers explore first and specialize later."""
    if gen is None:
        return OBSERVER_DIVERSITY_STRENGTH
    denom = max(1, GENERATIONS - 1)
    t = clamp((gen - 1) / denom)
    return OBSERVER_DIVERSITY_STRENGTH * (1.0 - t) + OBSERVER_DIVERSITY_LATE * t

def observer_diversity_bonus(obs, population, gen=None):
    """Reward observers whose taste is not just a clone of the current herd."""
    if len(population) <= 1:
        return 0.0
    dists = [observer_distance(obs, other) for other in population if other is not obs]
    nearest = min(dists) if dists else 0.0
    # nearest around 0.18+ is already meaningfully different after weight normalization
    return observer_diversity_strength_for_gen(gen) * clamp(nearest / 0.22)

def pearson_corr(xs, ys):
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    xs = xs[:n]; ys = ys[:n]
    mx = sum(xs)/n; my = sum(ys)/n
    vx = sum((x-mx)*(x-mx) for x in xs)
    vy = sum((y-my)*(y-my) for y in ys)
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0
    return sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / math.sqrt(vx*vy)



def rank_values(vals):
    """Simple average-rank helper for Spearman fallback."""
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) * 0.5 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks

def spearman_corr(xs, ys):
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    return pearson_corr(rank_values(xs[:n]), rank_values(ys[:n]))

def mse_agreement(xs, ys):
    """0..1 agreement fallback when correlations are noisy or too few picks exist."""
    n = min(len(xs), len(ys))
    if n <= 0:
        return 0.0
    mse = sum((clamp(xs[i]) - clamp(ys[i])) ** 2 for i in range(n)) / n
    return clamp(1.0 - mse * 3.0)

def robust_observer_agreement(preds, truths):
    """Use Pearson when there are enough post-tested picks, otherwise rank/MSE fallback."""
    n = min(len(preds), len(truths))
    if n >= 5:
        p = pearson_corr(preds, truths)
        s = spearman_corr(preds, truths)
        if abs(p) < 1e-9:
            return s
        return 0.65 * p + 0.35 * s
    if n >= 3:
        s = spearman_corr(preds, truths)
        m = mse_agreement(preds, truths)
        return 0.5 * s + 0.5 * (m * 2.0 - 1.0)
    return mse_agreement(preds, truths) * 2.0 - 1.0

OBSERVER_BLOCKS = [
    ('structure', ['macro_scaffold', 'nested_score_raw', 'edge', 'boundary_activity']),
    ('local_life', ['best_region_score', 'region_score', 'ms_local_life', 'persistent_entity_score', 'best_entity_quality']),
    ('motion_memory', ['ms_flow', 'ms_rotation_flow', 'memory_trace_score', 'cosmic_recovery']),
    ('curiosity', ['novelty_behavior', 'in_generation_diversity']),
]

def crossover_observer_profiles(a, b, new_id):
    """Block-level observer crossover: whole 'tastes' move together, not just averaged soup."""
    child_weights = {}
    for _, keys in OBSERVER_BLOCKS:
        donor = a if random.random() < 0.5 else b
        for k in keys:
            child_weights[k] = donor.get('weights', {}).get(k, 0.0)
    # tiny chance for one feature-level swap to prevent rigid blocks
    for k in OBSERVER_FEATURES:
        child_weights.setdefault(k, (a.get('weights', {}).get(k,0.0)+b.get('weights', {}).get(k,0.0))*0.5)
        if random.random() < 0.10:
            child_weights[k] = (a.get('weights', {}).get(k,0.0)+b.get('weights', {}).get(k,0.0))*0.5
    child = {'id': new_id, 'weights': child_weights, 'fitness': 0.0,
             'age': max(a.get('age',0), b.get('age',0)) + 1,
             'archetype': f'blockmix:{a.get("id")}/{b.get("id")}' }
    return mutate_observer_profile(child, new_id)

def short_weights(obs, topn=5):
    items = sorted(obs.get('weights', {}).items(), key=lambda kv: kv[1], reverse=True)[:topn]
    return ', '.join(f'{k}={v:.2f}' for k, v in items)

def evolve_observers_with_posttest(observers, all_results, next_obs_id, gen=None):
    """True coevolution-lite.
    Observers first nominate worlds using their own taste.  A small union of nominated
    and globally strong worlds is then post-tested with stress_test.  Observer fitness
    is how well their nominations predict post-test truth, not merely how much they
    agree with the current score.
    """
    candidates = []
    seen = set()
    # Include global best worlds.
    for score, rule, metrics in all_results[:POST_TEST_CANDIDATES]:
        sig = rule_signature(rule)
        if sig not in seen:
            candidates.append((rule, metrics, 'global'))
            seen.add(sig)
    # Include observer-nominated worlds.
    for obs in observers:
        ranked = sorted(all_results, key=lambda x: observer_score(obs, x[2]), reverse=True)
        for _, rule, metrics in ranked[:2]:
            sig = rule_signature(rule)
            if sig not in seen and len(candidates) < POST_TEST_CANDIDATES + POST_TEST_OBSERVER_TOP:
                candidates.append((rule, metrics, f'obs{obs.get("id")}'))
                seen.add(sig)
    truth_by_sig = {}
    print(f'  post-test: {len(candidates)} candidate worlds')
    for idx, (rule, metrics, source) in enumerate(candidates, 1):
        # A second evaluation with cosmic rays.  Uses the same global TICKS, so keep candidate count small.
        _, stress_metrics, _ = score_rule(rule, 'stress_test', max_ticks=max(420, int(TICKS * POST_TEST_TICK_FRACTION)))
        truth = post_test_truth_score(stress_metrics)
        truth_by_sig[rule_signature(rule)] = truth
        print(f'    post[{idx:02d}] rule={rule.rule_id:05d} src={source} truth={truth:6.2f} active={stress_metrics.get("active",0):.3f} edge={stress_metrics.get("edge",0):.3f} life={stress_metrics.get("ms_local_life",0):.3f} reg={stress_metrics.get("best_region_score",0):.3f} trk={stress_metrics.get("persistent_tracks",0)} cr={stress_metrics.get("cosmic_recovery",0):.3f}')
    # Fitness: nominate high-truth worlds and avoid high-scoring worlds that fail the post-test.
    for obs in observers:
        ranked = sorted(all_results, key=lambda x: observer_score(obs, x[2]), reverse=True)
        picks = ranked[:min(POST_TEST_OBSERVER_TOP, len(ranked))]
        fit = 0.0
        weight_sum = 0.0
        preds, truths = [], []
        for rank, (_, rule, metrics) in enumerate(picks):
            pred = observer_score(obs, metrics) / 34.0
            truth = truth_by_sig.get(rule_signature(rule))
            if truth is None:
                continue
            truth_n = truth / 100.0
            preds.append(pred); truths.append(truth_n)
            rank_w = 1.0 / (1.0 + rank * 0.35)
            # reward high prediction of true worlds, punish confidence in bad post-test worlds
            fit += rank_w * (truth_n * (0.6 + pred) - 0.35 * abs(pred - truth_n))
            weight_sum += rank_w
        raw_fit = 100.0 * fit / max(1e-6, weight_sum)
        div_bonus = observer_diversity_bonus(obs, observers, gen)
        old_ema = obs.get('fitness_ema', raw_fit)
        ema = OBSERVER_MEMORY_DECAY * old_ema + (1.0 - OBSERVER_MEMORY_DECAY) * raw_fit
        obs['fitness_raw'] = raw_fit
        obs['fitness_corr'] = robust_observer_agreement(preds, truths)
        obs['fitness_pearson'] = pearson_corr(preds, truths)
        obs['fitness_spearman'] = spearman_corr(preds, truths)
        obs['fitness_mse_agree'] = mse_agreement(preds, truths)
        obs['diversity_bonus'] = div_bonus
        obs['fitness_ema'] = ema
        obs['fitness'] = ema + div_bonus
    observers.sort(key=lambda z: z.get('fitness', 0.0), reverse=True)
    print('  top observers:')
    for oo in observers[:min(5, len(observers))]:
        print(f'    obs#{oo.get("id")} fit={oo.get("fitness",0):6.2f} raw={oo.get("fitness_raw",0):6.2f} ema={oo.get("fitness_ema",0):6.2f} div={oo.get("diversity_bonus",0):5.2f} agr={oo.get("fitness_corr",0):+.2f} p={oo.get("fitness_pearson",0):+.2f} s={oo.get("fitness_spearman",0):+.2f} mse={oo.get("fitness_mse_agree",0):.2f} | {short_weights(oo)}')
    elites = [dict(o, weights=dict(o['weights'])) for o in observers[:OBSERVER_ELITES]]
    new_obs = elites[:]
    while len(new_obs) < OBSERVER_COUNT:
        # Block crossover is now the default reproductive trick: observer 'schools of thought'
        # exchange whole preference modules, instead of averaging into grey mush.
        if random.random() < OBSERVER_BLOCK_CROSSOVER_RATE and len(elites) >= 2:
            a, b = random.sample(elites, 2)
            new_obs.append(crossover_observer_profiles(a, b, next_obs_id)); next_obs_id += 1
        else:
            parent = random.choice(elites)
            new_obs.append(mutate_observer_profile(parent, next_obs_id)); next_obs_id += 1
    return new_obs, next_obs_id, truth_by_sig

def save_observers(observers):
    try:
        OUT_DIR.mkdir(exist_ok=True)
        OBSERVER_ARCHIVE_FILE.write_text(json.dumps(observers, indent=2), encoding='utf-8')
    except Exception:
        pass

def observer_niche_key(metrics):
    """A world's ecological niche is the observer/archetype that liked it most.
    This lets worlds survive as representatives of different ways of seeing,
    not only as global score monarchs.
    """
    oid = metrics.get('observer_id', -1)
    arch = metrics.get('observer_archetype', 'unknown')
    return f'{arch}#{oid}'

def niche_champions(results, limit_per_niche=1):
    """Return unique rules that are best inside each observer niche."""
    by = {}
    for score, rule, metrics in results:
        k = observer_niche_key(metrics)
        if k not in by or score > by[k][0]:
            by[k] = (score, rule, metrics)
    champs = sorted(by.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(k, v) for k, v in champs[:max(1, OBSERVER_ELITES)]]

def write_niche_summary(gen, score_mode, results):
    rows = []
    for k, (score, rule, metrics) in niche_champions(results):
        rows.append({
            'niche': k,
            'rule_id': rule.rule_id,
            'score': score,
            'observer_score': metrics.get('observer_score', 0.0),
            'active': metrics.get('active', 0.0),
            'edge': metrics.get('edge', 0.0),
            'life': metrics.get('ms_local_life', 0.0),
            'flow': metrics.get('ms_flow', 0.0),
            'memory': metrics.get('memory_trace_score', 0.0),
            'region': metrics.get('best_region_score', 0.0),
            'entity_quality': metrics.get('best_entity_quality', 0.0),
            'truth': metrics.get('post_test_truth', None),
        })
    try:
        (OUT_DIR / f'niches_{gen:02d}_{score_mode}.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    except Exception:
        pass
    if rows:
        print('  niche champions:')
        for r in rows[:min(6, len(rows))]:
            print(f'    {r["niche"]}: rule={r["rule_id"]:05d} score={r["score"]:7.2f} obs={r["observer_score"]:5.1f} life={r["life"]:.3f} reg={r["region"]:.3f} mem={r["memory"]:.1f}')

def run_evolution(score_mode='balanced'):
    OUT_DIR.mkdir(exist_ok=True)
    favorites = load_human_favorites()
    observer_population = make_observer_population() if score_mode in ('observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches') else []
    next_observer_id = OBSERVER_COUNT
    population = [make_random_rule(i) for i in range(POPULATION)]
    if favorites:
        print(f'Loaded {len(favorites)} human favorite seed rules')
        for j, fav in enumerate(favorites[:min(len(favorites), POPULATION // 4)]):
            fav.rule_id = j
            population[j] = fav
    favorite_signatures = {rule_signature(r) for r in favorites}
    next_id = POPULATION
    best_ever = None
    novelty_archive = []
    for gen in range(1, GENERATIONS + 1):
        results = []
        generation_vectors = []
        print(f'Generation {gen}/{GENERATIONS} mode={score_mode}')
        for i, rule in enumerate(population, 1):
            internal_mode = 'hierarchical_novelty' if score_mode in ('hierarchical_novelty', 'observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches') else score_mode
            score, metrics, _ = score_rule(rule, internal_mode)
            if rule_signature(rule) in favorite_signatures:
                metrics['human_bonus'] = 28.0
                score += 28.0
            else:
                metrics['human_bonus'] = 0.0
            vec = metric_feature_vector(metrics)
            novelty_score = novelty_from_archive(vec, novelty_archive)
            in_gen_diversity = novelty_from_archive(vec, generation_vectors)
            generation_vectors.append(vec)
            metrics['novelty_behavior'] = novelty_score
            metrics['in_generation_diversity'] = in_gen_diversity
            if score_mode in ('observer_evolution', 'coevolution', 'observer_stability', 'observer_genetics', 'observer_niches'):
                obs_scores = [(observer_score(o, metrics), o) for o in observer_population]
                obs_scores.sort(key=lambda x: x[0], reverse=True)
                best_obs_score, best_obs = obs_scores[0]
                metrics['observer_score'] = best_obs_score
                metrics['observer_id'] = best_obs.get('id', -1)
                metrics['observer_archetype'] = best_obs.get('archetype', 'unknown')
                # Let observers compete, but keep the old lab signals as a stabilizing floor.
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.52 + best_obs_score + novelty_score * (NOVELTY_BONUS_BASE * 0.55) + in_gen_diversity * (DIVERSITY_BONUS_BASE * gen_pressure)
            elif score_mode in ('hierarchical_novelty', 'adaptive_observer', 'cosmic_curator'):
                # Two-stage taste: good macro stage, local process, unlike archive, and unlike siblings this generation.
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.70 + novelty_score * NOVELTY_BONUS_BASE + in_gen_diversity * (DIVERSITY_BONUS_BASE * gen_pressure) + min(metrics.get('macro_scaffold',0), 120) * 0.12
            elif score_mode == 'novelty':
                gen_pressure = 1.0 - 0.35 * ((gen - 1) / max(1, GENERATIONS - 1))
                score = score * 0.62 + novelty_score * 58.0 + in_gen_diversity * (34.0 * gen_pressure)
            results.append((score, rule, metrics))
            if score > -20 or novelty_score > 0.38 or in_gen_diversity > 0.55:
                novelty_archive.append(vec)
            print(f'  [{i:03d}/{POPULATION}] rule={rule.rule_id:05d} score={score:8.3f} active={metrics["active"]:.3f} edge={metrics["edge"]:.3f} b_act={metrics["boundary_activity"]:.5f} islands={metrics["islands"]} nested={metrics.get("nested_score_raw",0):.3f} life={metrics.get("ms_local_life",0):.3f} flow={metrics.get("ms_flow",0):.4f} rot={metrics.get("ms_rotation_flow",0):.4f} ent={metrics.get("entity_count",0)} trk={metrics.get("persistent_tracks",0)} objQ={metrics.get("best_entity_quality",0):.3f} reg={metrics.get("best_region_score",0):.3f} rc={metrics.get("region_count",0)} nov={metrics.get("novelty_behavior",0):.3f} div={metrics.get("in_generation_diversity",0):.3f} mac={metrics.get("macro_scaffold",0):.1f} mem={metrics.get("memory_trace_score",0):.1f} cr={metrics.get("cosmic_recovery",0):.3f} hum={metrics.get("human_bonus",0):.0f} pen={metrics.get("degeneracy_penalty",0):.1f}/{metrics.get("degeneracy_penalty_raw",0):.1f} obs={metrics.get("observer_id","-")}:{metrics.get("observer_score",0):.1f}')
            note = metrics.get('observer_note', '')
            if metrics.get('persistent_entity_score', 0.0) > 0.20 or metrics.get('best_entity_quality', 0.0) > 0.25 or metrics.get('best_region_score', 0.0) > 0.18 or metrics.get('best_hotspot_score', 0.0) > 0.20:
                print(f'      observer: {note}')
        results.sort(key=lambda x: x[0], reverse=True)
        if score_mode in ('coevolution', 'observer_stability', 'observer_niches'):
            observer_population, next_observer_id, truth_by_sig = evolve_observers_with_posttest(observer_population, results, next_observer_id, gen)
            # Add truth score into saved metrics for top rules if available.
            for idx, (s0, r0, m0) in enumerate(results):
                if rule_signature(r0) in truth_by_sig:
                    m0['post_test_truth'] = truth_by_sig[rule_signature(r0)]
            save_observers(observer_population)
            lead = observer_population[0]
            print(f'  coevolution observer champion: id={lead.get("id")} arch={lead.get("archetype")} fitness={lead.get("fitness",0):.2f}')
            if score_mode == 'observer_niches':
                write_niche_summary(gen, score_mode, results)
        elif score_mode == 'observer_evolution':
            top_metrics = [m for _, _, m in results[:KEEP_TOP]]
            observer_population, next_observer_id = evolve_observers(observer_population, top_metrics, next_observer_id)
            save_observers(observer_population)
            lead = observer_population[0]
            print(f'  observer champion: id={lead.get("id")} arch={lead.get("archetype")} fitness={lead.get("fitness",0):.2f}')
        if best_ever is None or results[0][0] > best_ever[0]:
            best_ever = results[0]
        payload = [{'score': s, 'rule': rule_to_dict(r), 'metrics': m} for s, r, m in results[:KEEP_TOP]]
        (OUT_DIR / f'generation_{gen:02d}_{score_mode}.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
        (OUT_DIR / f'best_{score_mode}.json').write_text(json.dumps({'score': best_ever[0], 'rule': rule_to_dict(best_ever[1]), 'metrics': best_ever[2]}, indent=2), encoding='utf-8')
        print(f'BEST gen={gen}: rule={results[0][1].rule_id:05d} score={results[0][0]:.3f} | best ever={best_ever[1].rule_id:05d} {best_ever[0]:.3f}')
        print(f'  best observer: {results[0][2].get("observer_note", "no note")}')
        if score_mode == 'observer_niches':
            # Preserve global champions AND niche champions. This is the key difference:
            # a world can survive because it is the best specimen for a particular observer-school.
            elite_rules = []
            seen_sigs = set()
            for _, r, _ in results[:max(4, ELITES//2)]:
                sig = rule_signature(r)
                if sig not in seen_sigs:
                    elite_rules.append(r); seen_sigs.add(sig)
            for _, (_, r, _) in niche_champions(results):
                sig = rule_signature(r)
                if sig not in seen_sigs:
                    elite_rules.append(r); seen_sigs.add(sig)
            elites = elite_rules[:max(2, ELITES)]
        else:
            elites = [r for _, r, _ in results[:ELITES]]
        newpop = elites[:]
        # Random immigrants: keep a few strange tourists in the gene pool.
        while len(newpop) < POPULATION - RANDOM_IMMIGRANTS:
            a, b = random.sample(elites, 2)
            newpop.append(crossover(a, b, next_id))
            next_id += 1
        while len(newpop) < POPULATION:
            newpop.append(make_random_rule(next_id)); next_id += 1
        population = newpop
    print('Search complete.')
    print(f'Best rule: {best_ever[1].rule_id:05d}, score={best_ever[0]:.3f}')

class Viewer:
    def __init__(self, root):
        self.root = root
        self.root.title('Universe Search v1.0.4 Observer Niches Viewer')
        self.canvas = tk.Canvas(root, width=W*CELL + PANEL_W, height=H*CELL, bg='black')
        self.canvas.pack()
        self.rule = self.load_best()
        self.sim = FieldSim(self.rule)
        self.running = True
        self.steps_per_frame = 4
        self.view_mode_i = 0
        self.last_recovery = None
        self.recovery_before = None
        self.recovery_after = None
        self.last_ray_tick = None
        self.ghost_alpha = 0.55
        root.bind('<space>', self.toggle)
        root.bind('r', self.reset)
        root.bind('v', self.cycle_view)
        root.bind('s', self.step_once)
        root.bind('l', self.like_rule)
        root.bind('c', self.cosmic_ray)
        root.bind('p', self.save_png)
        root.bind('e', self.export_rule)
        root.bind('+', self.faster)
        root.bind('=', self.faster)
        root.bind('-', self.slower)
        root.bind('[', self.ghost_down)
        root.bind(']', self.ghost_up)
        self.draw()

    def load_best(self):
        files = sorted(OUT_DIR.glob('best_*.json'))
        if files:
            data = json.loads(files[-1].read_text(encoding='utf-8'))
            print('Loaded', files[-1])
            return rule_from_dict(data['rule'])
        print('No best file found, using random rule.')
        return make_random_rule(0)

    def toggle(self, _=None):
        self.running = not self.running

    def reset(self, _=None):
        self.sim = FieldSim(self.rule)

    def cycle_view(self, _=None):
        self.view_mode_i = (self.view_mode_i + 1) % len(VIEW_MODES)

    def step_once(self, _=None):
        self.running = False
        self.sim.step()

    def like_rule(self, _=None):
        saved = save_human_favorite(self.rule, note=f'liked at tick {self.sim.tick}')
        print('Human favorite saved.' if saved else 'Already in human favorites.')

    def cosmic_ray(self, _=None):
        self.recovery_before = [row[:] for row in self.sim.a]
        info = apply_cosmic_ray(self.sim)
        self.recovery_after = [row[:] for row in self.sim.a]
        self.last_ray_tick = self.sim.tick
        self.last_recovery = {'cosmic_recovery': 0.0, **info}
        print('Cosmic ray injected:', info)


    def save_png(self, _=None):
        try:
            from PIL import Image
            mode = VIEW_MODES[self.view_mode_i]
            img = Image.new('RGB', (W, H))
            pix = img.load()
            for y in range(H):
                for x in range(W):
                    h = self.cell_color(x, y, mode).lstrip('#')
                    pix[x, y] = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            OUT_DIR.mkdir(exist_ok=True)
            path = OUT_DIR / f'snapshot_rule_{self.rule.rule_id:05d}_tick_{self.sim.tick:06d}_{mode}.png'
            img = img.resize((W*CELL, H*CELL), Image.Resampling.NEAREST)
            img.save(path)
            print('Saved PNG:', path)
        except Exception as e:
            print('PNG save failed:', e)

    def export_rule(self, _=None):
        try:
            OUT_DIR.mkdir(exist_ok=True)
            base = OUT_DIR / f'export_rule_{self.rule.rule_id:05d}'
            (base.with_suffix('.json')).write_text(json.dumps(rule_to_dict(self.rule), indent=2), encoding='utf-8')
            code = 'from dataclasses import dataclass\n# Paste this dict into another Universe Search compatible engine.\nRULE = ' + repr(rule_to_dict(self.rule)) + '\n'
            (base.with_suffix('.py')).write_text(code, encoding='utf-8')
            print('Exported rule:', base.with_suffix('.json'), 'and', base.with_suffix('.py'))
        except Exception as e:
            print('Export failed:', e)

    def faster(self, _=None):
        self.steps_per_frame = min(64, self.steps_per_frame * 2)

    def slower(self, _=None):
        self.steps_per_frame = max(1, self.steps_per_frame // 2)

    def ghost_down(self, _=None):
        self.ghost_alpha = max(0.05, self.ghost_alpha - 0.08)

    def ghost_up(self, _=None):
        self.ghost_alpha = min(0.95, self.ghost_alpha + 0.08)

    def cell_color(self, x, y, mode):
        a = self.sim.a[y][x]
        if mode == 'value':
            # blue/yellow, closer to the older viewer
            blue = int((1.0 - a) * 230)
            yellow = int(a * 255)
            green = int(120 + 90 * (1.0 - abs(a - 0.5) * 2))
            return f'#{yellow:02x}{green:02x}{blue:02x}'
        if mode == 'activity':
            h = clamp(self.sim.activity_heat[y][x])
            r = int(h * 255); g = int(min(255, h * 420)); b = int(40 + (1-h) * 70)
            return f'#{r:02x}{g:02x}{b:02x}'
        if mode == 'velocity':
            v = self.sim.v[y][x]
            if v >= 0:
                r = int(clamp(v * 9000) * 255); b = 30
            else:
                b = int(clamp(-v * 9000) * 255); r = 30
            g = int(50 + clamp(abs(v) * 5000) * 120)
            return f'#{r:02x}{g:02x}{b:02x}'
        if mode == 'edge':
            e = abs(a - self.sim.a[y][(x+1) % W]) + abs(a - self.sim.a[(y+1) % H][x])
            e = clamp(e * 2.2)
            v = int(e * 255)
            return f'#{v:02x}{v:02x}{v:02x}'
        if mode == 'age':
            age = clamp(self.sim.age[y][x] / 200.0)
            v = int(age * 255)
            return f'#{v:02x}{v:02x}{v:02x}'
        if mode == 'delta':
            d = clamp(self.sim.delta[y][x] * 120.0)
            r = int(d * 255)
            g = int((1.0 - abs(a - 0.5) * 2.0) * 120)
            b = int((1.0 - d) * 90)
            return f'#{r:02x}{g:02x}{b:02x}'
        if mode == 'hotspot':
            # value + activity heat, useful for finding local life zones
            h = clamp(self.sim.activity_heat[y][x])
            r = int(clamp(a * 0.55 + h * 0.75) * 255)
            g = int(clamp((1.0 - abs(a - 0.5) * 2.0) * 0.35 + h * 0.9) * 255)
            b = int(clamp((1.0 - a) * 0.65 + h * 0.35) * 255)
            return f'#{r:02x}{g:02x}{b:02x}'
        if mode == 'ghost':
            # Current state blended with previous tick: cyan = older, yellow/red = new motion.
            old = self.sim.prev_a[y][x]
            d = clamp(abs(a - old) * 80.0)
            alpha = self.ghost_alpha
            mix = alpha * old + (1.0 - alpha) * a
            r = int(clamp(a * 0.45 + d * 0.80 + (1-alpha)*0.15) * 255)
            g = int(clamp((a + old) * 0.22 + d * 0.65) * 255)
            b = int(clamp((1.0 - mix) * 0.60 + (1.0 - d) * 0.14) * 255)
            return f'#{r:02x}{g:02x}{b:02x}'
        v = int(a * 255)
        return f'#{v:02x}{v:02x}{v:02x}'

    def draw(self):
        if self.running:
            for _ in range(self.steps_per_frame):
                self.sim.step()
        self.canvas.delete('all')
        mode = VIEW_MODES[self.view_mode_i]
        for y in range(H):
            for x in range(W):
                col = self.cell_color(x, y, mode)
                self.canvas.create_rectangle(x*CELL, y*CELL, (x+1)*CELL, (y+1)*CELL, fill=col, outline='')
        if self.last_ray_tick is not None and self.recovery_before is not None and self.recovery_after is not None and self.sim.tick >= self.last_ray_tick + 80:
            rec, rec_m = cosmic_recovery_score(self.recovery_before, self.recovery_after, self.sim.a)
            self.last_recovery = rec_m
        m = self.sim.metrics(); sm = self.sim.scale_metrics(); islands, biggest, _ = self.sim.islands()
        px = W*CELL + 16
        lines = [
            'Universe Search v1.0', '',
            f'Rule: {self.rule.rule_id}', f'Tick: {self.sim.tick}',
            f'View: {mode}', f'Ghost: {self.ghost_alpha:.2f}', f'Speed: x{self.steps_per_frame}', f'Paused: {not self.running}', '',
            f'active: {m["active"]:.3f}', f'mean:   {m["mean"]:.3f}', f'edge:   {m["edge"]:.3f}',
            f'motion: {m["motion"]:.5f}', f'activity: {m["activity"]:.5f}',
            f'boundary_act: {m["boundary_activity"]:.5f}', f'boundary_frac: {m["boundary_fraction"]:.3f}',
            f'hot_fraction: {m["hot_fraction"]:.4f}', f'old_fraction: {m["old_fraction"]:.3f}',
            f'trace_mass: {m.get("trace_mass",0):.4f}', f'trace_edge: {m.get("trace_edge",0):.4f}',
            f'recovery: {(self.last_recovery or {}).get("cosmic_recovery",0):.3f}',
            f'islands: {islands}', f'biggest: {biggest}', '',
            f'small_texture: {sm["small_texture"]:.5f}', f'mid_texture:   {sm["mid_texture"]:.5f}',
            f'large_order:   {sm["large_order"]:.5f}', f'scale_gap:     {sm["scale_gap"]:.5f}', '',
            'Space: pause/run', 'S: one tick', 'V: view mode', '+/-: speed', 'R: reset',
            'C: cosmic ray', 'P: save PNG', 'E: export rule', 'L: like rule', '[/]: ghost alpha'
        ]
        for i, line in enumerate(lines):
            self.canvas.create_text(px, 18+i*18, text=line, fill='white', anchor='nw', font=('Consolas', 11))
        self.root.after(30, self.draw)

def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'menu'
    score_mode = sys.argv[2].lower() if len(sys.argv) > 2 else 'observer_evolution'
    if score_mode not in SCORE_MODES:
        score_mode = 'emergence'
    if mode in ('evolve', 'search'):
        run_evolution(score_mode)
    elif mode == 'view':
        if tk is None:
            print('tkinter is not available. Viewer disabled.')
            return
        root = tk.Tk()
        Viewer(root)
        root.mainloop()
    else:
        print('Доступные режимы:', ', '.join(SCORE_MODES))
        print('Рекомендовано:')
        print('  python universe_search_v09_1_quality_viewer.py evolve emergent_ecology')
        print('  python universe_search_v09_1_quality_viewer.py evolve local_life')
        print('  python universe_search_v09_1_quality_viewer.py evolve entity_mode')
        print('  python universe_search_v09_1_quality_viewer.py evolve flow')
        print('  python universe_search_v09_1_quality_viewer.py view')

if __name__ == '__main__':
    main()
