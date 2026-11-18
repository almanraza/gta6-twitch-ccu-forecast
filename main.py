"""GTA VI launch-day Twitch concurrent-viewer forecaster.

Reads one case (makefun/twitch-ccu-case/v1) and writes, for each of hours 2..24
of the release day, five quantiles of that hour's concurrent viewers in Twitch's
"Grand Theft Auto VI" category.

The idea
--------
A launch day is not one curve. It is two, and which one you get is decided by
how much of the day's audience hour 1 already holds:

  * a midnight unlock in the game's main market puts the peak in hour 1, and the
    day decays from there;
  * an unlock that lands while most of the world is asleep leaves hour 1 holding
    a fraction of the audience, and the day ramps up as each region's midnight
    arrives, peaking late.

GTA VI is the second kind: New Zealand unlocks at 11:00Z the day before, central
Europe at 23:00Z, the UK at 00:00Z, the US east coast at 05:00Z and the west
coast at 08:00Z. Hour 1 (00:00-01:00Z) therefore holds Europe and the UK but
almost none of the Americas, so the day should rise for many hours after it.

The regime is read from the case itself, not assumed: hour 1's print against the
category's own pre-release baseline, the median of the history the case carries.
A launch whose hour 1 is already far above its ordinary audience is the first
kind; one whose hour 1 is only a few times its ordinary audience is the second.

Within a regime the shape is a smooth curve fitted to the comparables' log ratio
to their own hour 1, and the spread is the empirical spread of the residuals
around that curve, so the quantiles are measured rather than assumed. The
pinball loss is proper, so an honest spread is what scores best.

Standard library only, no network, deterministic: two runs on one case write the
same bytes.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Launches below this hour-1 print are too small to say anything about a launch
# of GTA VI's size: their curves are dominated by one or two big streamers.
MIN_V1 = 20000
# How much to widen or narrow the measured spread. 1.0 is the honest value.
SPREAD_SCALE = 1.05


# --------------------------------------------------------------------- stats

def quantile(vals, tau):
    """Linear-interpolated quantile of a sorted list."""
    n = len(vals)
    if n == 0:
        return 0.0
    if n == 1:
        return vals[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return vals[lo] * (1 - (pos - lo)) + vals[hi] * (pos - lo)


def solve(A, b):
    """Least squares by normal equations, Gaussian elimination with a tiny ridge."""
    n = len(A[0])
    N = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(n)] for i in range(n)]
    y = [sum(A[k][i] * b[k] for k in range(len(A))) for i in range(n)]
    for i in range(n):
        N[i][i] += 1e-9
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(N[r][i]))
        N[i], N[p] = N[p], N[i]
        y[i], y[p] = y[p], y[i]
        if abs(N[i][i]) < 1e-12:
            continue
        for r in range(i + 1, n):
            f = N[r][i] / N[i][i]
            for c in range(i, n):
                N[r][c] -= f * N[i][c]
            y[r] -= f * y[i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        if abs(N[i][i]) < 1e-12:
            continue
        x[i] = (y[i] - sum(N[i][j] * x[j] for j in range(i + 1, n))) / N[i][i]
    return x


# --------------------------------------------------------------------- shape

def basis(h):
    """Smooth basis over hours 2..24: level, trend, and three bumps.

    The bumps sit where launch days actually bend: the early drop after a
    midnight peak, the midday plateau, and the evening peak.
    """
    x = (h - 2) / 22.0
    return [
        1.0,
        x,
        math.exp(-((h - 4.0) ** 2) / (2 * 3.0 ** 2)),
        math.exp(-((h - 10.0) ** 2) / (2 * 4.0 ** 2)),
        math.exp(-((h - 20.0) ** 2) / (2 * 4.5 ** 2)),
    ]


def curve_at(coef, h):
    return sum(c * v for c, v in zip(coef, basis(h)))


def fit_curve(points):
    return solve([basis(h) for h, _ in points], [v for _, v in points])


# ---------------------------------------------------------------------- case

def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def day_hours(comp):
    """A comparable's release-day hours 1..24 -> viewers."""
    t0 = parse(comp["day_start"])
    out = {}
    for pt in comp["hourly"]:
        h = int(round((parse(pt["from"]) - t0).total_seconds() / 3600)) + 1
        if 1 <= h <= 24 and pt.get("viewers") is not None:
            out[h] = pt["viewers"]
    return out


def prebase(comp):
    """Median viewers in the 7 days before the release day."""
    t0 = parse(comp["day_start"])
    vals = [p["viewers"] for p in comp["hourly"]
            if p.get("viewers") is not None
            and 0 <= (t0 - parse(p["from"])).total_seconds() / 86400 <= 7]
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


def case_prebase(case):
    """The same yardstick for the case being forecast, from its own history."""
    vals = [p["viewers"] for p in case.get("history") or []
            if p.get("viewers") is not None and p["viewers"] >= 1]
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


def regime(v1, pb):
    """How far hour 1 already stands above the category's ordinary audience."""
    if not pb or pb < 1:
        return 0.0
    return math.log(max(v1, 1) / pb)


# --------------------------------------------------------------------- model

def build(comps):
    """Fit one curve per regime, with each hour's residual spread."""
    pool = []
    for c in comps:
        dh = day_hours(c)
        v1 = dh.get(1)
        pb = prebase(c)
        if not v1 or v1 < MIN_V1 or not pb or pb < 1:
            continue
        r = {}
        for h in range(2, 25):
            v = dh.get(h)
            if v is not None and v >= 1:
                r[h] = math.log(v / v1)
        if len(r) >= 15:
            pool.append((regime(v1, pb), r))

    if not pool:
        return None

    regs = sorted(x[0] for x in pool)
    cut = regs[len(regs) // 2]

    models = []
    for lo, hi in ((-1e9, cut), (cut, 1e9)):
        pts, members = [], []
        for rg, r in pool:
            if lo <= rg < hi:
                members.append(r)
                pts.extend((h, v) for h, v in r.items())
        if len(members) < 4:
            continue
        coef = fit_curve(pts)
        res = {h: [] for h in range(2, 25)}
        for r in members:
            for h, v in r.items():
                res[h].append(v - curve_at(coef, h))
        models.append({"lo": lo, "hi": hi, "coef": coef, "res": res})

    if not models:
        return None
    return {"cut": cut, "models": models}


def forecast(case, model):
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    p1 = max(1, first["viewers"]) if first else 1
    rg = regime(p1, case_prebase(case))

    pick = None
    for m in model["models"]:
        if m["lo"] <= rg < m["hi"]:
            pick = m
            break
    if pick is None:
        pick = model["models"][0]

    rows = []
    for h in range(2, 25):
        m = curve_at(pick["coef"], h)
        rs = sorted(pick["res"][h])
        if len(rs) < 4:
            # Too few comparables for this hour: fall back to a random walk.
            rows.append([p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z])
            continue
        qs = [p1 * math.exp(m + quantile(rs, tau) * SPREAD_SCALE) for tau in LEVELS]
        rows.append(qs)
    return rows


def clamp_rows(rows):
    """Keep every quantile finite, above 0, at most 1e9, and non-decreasing."""
    out = []
    for h, qs in zip(range(2, 25), rows):
        fixed = []
        prev = 0.0
        for q in qs:
            if not isinstance(q, (int, float)) or not math.isfinite(q):
                q = 1.0
            q = min(max(float(q), 1e-6), 1e9)
            q = max(q, prev)
            prev = q
            fixed.append(round(q, 4))
        out.append({"hour": h, "q": fixed})
    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        model = build(case.get("comparables") or [])
        if model is None:
            first = next((k for k in case["known"] if k["hour"] == 1), None)
            p1 = max(1, first["viewers"]) if first else 1
            rows = [[p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z]
                    for h in range(2, 25)]
        else:
            rows = forecast(case, model)
        payload = {"hours": clamp_rows(rows)}
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
