#!/usr/bin/env python3
"""Minimal async load test for the PUBLIC read endpoints (no login, no LLM calls, no spend).

    python scripts/loadtest.py --base-url http://localhost:8021 --concurrency 50 --duration 20

Hits /api/topics, /api/cases and /api/cases/{id} (ids discovered from /api/cases) in a weighted mix and prints
RPS, error rate and p50/p95/p99 latency overall and per endpoint. Dependencies: httpx only (requirements.txt).

NOTE: the app has a per-IP ceiling (GLOBAL_IP_LIMIT_PER_MIN, default 300/min) that answers 429. Against a local server
raise it (e.g. GLOBAL_IP_LIMIT_PER_MIN=1000000) or the test measures the limiter. 429s are reported as their own
column and are NOT counted as latency samples. Do not point this at production without telling yourself first.
"""
import argparse
import asyncio
import itertools
import random
import statistics
import sys
import time
from collections import defaultdict
from typing import Dict, List, Tuple

import httpx


def pct(sorted_ms: List[float], p: float) -> float:
    if not sorted_ms:
        return float("nan")
    k = min(len(sorted_ms) - 1, max(0, int(round(p / 100 * len(sorted_ms) + 0.5)) - 1))
    return sorted_ms[k]


async def discover(client: httpx.AsyncClient, lang: str) -> List[str]:
    r = await client.get("/api/cases", params={"lang": lang, "limit": 100})
    r.raise_for_status()
    return [c["case_id"] for c in r.json()]


async def worker(client: httpx.AsyncClient, deadline: float, ids: List[str], lang: str,
                 samples: Dict[str, List[float]], status: Dict[str, Dict[int, int]]) -> None:
    rnd = random.Random()
    while time.perf_counter() < deadline:
        roll = rnd.random()
        if roll < 0.2:
            name, url, params = "GET /api/topics", "/api/topics", {"lang": lang}
        elif roll < 0.5:
            name, url, params = "GET /api/cases", "/api/cases", {"lang": lang, "limit": 20, "offset": rnd.choice((0, 20, 40))}
        else:
            cid = rnd.choice(ids)
            name, url, params = "GET /api/cases/{id}", f"/api/cases/{cid}", {"lang": lang}
        t0 = time.perf_counter()
        try:
            r = await client.get(url, params=params)
            code = r.status_code
        except httpx.HTTPError:
            code = 0
        dt = (time.perf_counter() - t0) * 1000
        status[name][code] += 1
        if code == 200:
            samples[name].append(dt)


def report(samples, status, elapsed: float) -> Tuple[int, int]:
    rows = []
    total = ok = limited = 0
    for name in sorted(status):
        codes = status[name]
        n = sum(codes.values())
        total += n
        ok += codes.get(200, 0)
        limited += codes.get(429, 0)
        lat = sorted(samples[name])
        rows.append((name, n, codes.get(200, 0), codes.get(429, 0), n - codes.get(200, 0) - codes.get(429, 0),
                     pct(lat, 50), pct(lat, 95), pct(lat, 99), max(lat) if lat else float("nan")))
    allv = sorted(itertools.chain.from_iterable(samples.values()))
    rows.append(("ALL", total, ok, limited, total - ok - limited, pct(allv, 50), pct(allv, 95), pct(allv, 99),
                 max(allv) if allv else float("nan")))
    print(f"{'endpoint':<22}{'reqs':>8}{'200':>8}{'429':>7}{'err':>6}{'p50ms':>9}{'p95ms':>9}{'p99ms':>9}{'maxms':>9}")
    for r in rows:
        print(f"{r[0]:<22}{r[1]:>8}{r[2]:>8}{r[3]:>7}{r[4]:>6}{r[5]:>9.1f}{r[6]:>9.1f}{r[7]:>9.1f}{r[8]:>9.1f}")
    errors = total - ok - limited
    print(f"\nduration={elapsed:.1f}s  throughput={total / elapsed:.0f} req/s  ok-rate={100 * ok / max(total, 1):.2f}%  "
          f"error-rate={100 * errors / max(total, 1):.2f}%  rate-limited={100 * limited / max(total, 1):.2f}%")
    if allv:
        print(f"mean={statistics.fmean(allv):.1f}ms")
    return errors, limited


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8001")
    ap.add_argument("--concurrency", "-c", type=int, default=50)
    ap.add_argument("--duration", "-d", type=float, default=20.0, help="seconds")
    ap.add_argument("--lang", default="en", choices=("tr", "en"))
    ap.add_argument("--max-error-rate", type=float, default=1.0, help="exit 1 if error rate (%%) is above this")
    a = ap.parse_args()

    limits = httpx.Limits(max_connections=a.concurrency, max_keepalive_connections=a.concurrency)
    async with httpx.AsyncClient(base_url=a.base_url, timeout=30, limits=limits) as client:
        ids = await discover(client, a.lang)
        print(f"target={a.base_url} concurrency={a.concurrency} duration={a.duration}s cases={len(ids)}")
        samples: Dict[str, List[float]] = defaultdict(list)
        status: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        start = time.perf_counter()
        deadline = start + a.duration
        await asyncio.gather(*(worker(client, deadline, ids, a.lang, samples, status) for _ in range(a.concurrency)))
        elapsed = time.perf_counter() - start
    errors, _ = report(samples, status, elapsed)
    total = sum(sum(c.values()) for c in status.values())
    return 1 if total and 100 * errors / total > a.max_error_rate else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
