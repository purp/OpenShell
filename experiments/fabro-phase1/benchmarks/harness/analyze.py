# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fit the three-term proxy cost model from run-ladder.sh output.

Usage: python3 analyze.py <results-dir>

CSV columns: rung,cell,rep,namelookup,connect,appconnect,ttfb,total (seconds)
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def load(results_dir):
    rows = defaultdict(list)  # (rung, cell) -> list of dict
    for path in sorted(Path(results_dir).glob("rung*.csv")):
        with open(path, newline="") as f:
            for rec in csv.reader(f):
                if len(rec) != 8:
                    continue
                rung, cell, rep = rec[0], rec[1], int(rec[2])
                # keep-alive cells: curl -o only redirects the first URL, so
                # later 16-byte "xxx..." bodies prefix the timing line
                rec[3] = rec[3].lstrip("x")
                nl, conn, app, ttfb, total = (float(x) for x in rec[3:])
                rows[(rung, cell)].append(
                    dict(rep=rep, namelookup=nl, connect=conn,
                         appconnect=app, ttfb=ttfb, total=total)
                )
    return rows


def med_iqr(values):
    med = statistics.median(values)
    q = statistics.quantiles(values, n=4)
    return med, q[2] - q[0]


def ms(x):
    return f"{x * 1000:8.2f}"


def fit_slope(points):
    """Least-squares slope/intercept over (x, y) medians."""
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def main():
    rows = load(sys.argv[1])

    print(f"{'rung,cell':<24} {'n':>4} {'med_total':>9} {'IQR':>9} "
          f"{'med_conn':>9} {'med_appconn':>11} {'med_ttfb':>9}  (ms)")
    for (rung, cell), recs in sorted(rows.items()):
        tot = [r["total"] for r in recs]
        med, iqr = med_iqr(tot)
        mc, _ = med_iqr([r["connect"] for r in recs])
        ma, _ = med_iqr([r["appconnect"] for r in recs])
        mt, _ = med_iqr([r["ttfb"] for r in recs])
        print(f"{rung + ',' + cell:<24} {len(recs):>4} {ms(med)} {ms(iqr)} "
              f"{ms(mc)} {ms(ma):>11} {ms(mt)}")

    # per-byte slopes: fit median total vs bytes for size sweeps, per rung/direction
    print("\nper-byte slopes (fit over size-sweep medians):")
    for rung in sorted({r for (r, _) in rows}):
        for direction in ("resp", "req"):
            pts = []
            for (rg, cell), recs in rows.items():
                if rg != rung or not cell.startswith(f"{direction}_"):
                    continue
                kb = int(cell.split("_")[1].rstrip("k"))
                med, _ = med_iqr([r["total"] for r in recs])
                pts.append((kb * 1024, med))
            if len(pts) >= 3:
                slope, intercept = fit_slope(sorted(pts))
                print(f"  {rung} {direction}: {slope * 1e9:8.2f} ns/byte "
                      f"({slope * 1e6 * 1024:6.2f} us/KB), "
                      f"intercept {intercept * 1000:7.2f} ms")

    # per-request constant from keep-alive: (total_kaN - total_ka1) / (N-1)
    print("\nper-request constant (keep-alive deltas, using final-request totals):")
    for rung in sorted({r for (r, _) in rows}):
        base = None
        for n in (1, 10, 100):
            key = (rung, f"ka{n}_req{n}")
            # total across the whole curl run is the LAST request's cumulative? No:
            # each -w line is per transfer; sum the per-request medians instead.
            cells = [(c, recs) for (rg, c), recs in rows.items()
                     if rg == rung and c.startswith(f"ka{n}_req")]
            if not cells:
                continue
            per_req = []
            for c, recs in cells:
                med, _ = med_iqr([r["total"] for r in recs])
                per_req.append(med)
            total = sum(per_req)
            if n == 1:
                base = total
                print(f"  {rung} ka1 total {ms(total)} ms (connection setup + 1 request)")
            elif base is not None:
                print(f"  {rung} ka{n}: marginal per-request "
                      f"{ms((total - base) / (n - 1))} ms")


if __name__ == "__main__":
    main()
