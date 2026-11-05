#!/usr/bin/env python3
"""Generate a synthetic JMeter JTL (CSV) for demos and tests.

The data is fully fake: host is example.test, timings come from a seeded RNG,
so the output is reproducible byte for byte.

    python3 tools/make_sample.py samples/jmeter.jtl
    python3 tools/make_sample.py out.jtl --iterations 10 --seed 7
"""
import argparse
import csv
import random

HEADER = ['timeStamp', 'elapsed', 'label', 'responseCode', 'responseMessage',
          'threadName', 'dataType', 'success', 'failureMessage', 'bytes',
          'sentBytes', 'grpThreads', 'allThreads', 'URL', 'Latency',
          'IdleTime', 'Connect']

# (step label, typical elapsed ms, number of sub-requests)
STEPS = [
    ('01. Home page', 300, 3),
    ('02. Login', 1200, 4),
    ('03. Open "Work plan" section', 800, 2),
    ('04. Search by keyword', 35, 1),
    ('05. Open "Catalogs" section', 30, 1),
    ('06. Open "Details" section', 50, 1),
    ('07. Open "Summary reports" section', 30, 1),
    ('08. Open "Settings" section', 45, 1),
    ('09. Open "Profile" section', 40, 1),
    ('10. Logout', 150, 2),
]
BASE_TS = 1768471200000  # 2026-01-15 10:00:00 UTC


def generate(iterations=20, seed=42, threads=2):
    rng = random.Random(seed)
    rows = []
    for it in range(iterations):
        thread = f'Thread Group 1-{it % threads + 1}'
        ts = BASE_TS + it * 9000
        for si, (label, typical, subs) in enumerate(STEPS):
            parts = []
            cursor = ts
            for sub in range(subs):
                elapsed = max(1, int(rng.gauss(typical / subs, typical / subs / 4)))
                ok = not (si == 3 and it % 17 == 16)  # a rare error in step 04
                parts.append((cursor, elapsed, ok))
                cursor += elapsed + rng.randint(1, 8)
            total = cursor - ts
            if si == 1 and it == iterations // 2:
                total += 30000  # one outlier on login
            ok_all = all(p[2] for p in parts)
            rows.append([ts, total, label, 200 if ok_all else 500,
                         f'Number of samples in transaction : {subs}, '
                         f'number of failing samples : {0 if ok_all else 1}',
                         thread, '', str(ok_all).lower(), '',
                         rng.randint(1000, 30000), rng.randint(300, 3000),
                         threads, threads, 'null', 0, rng.randint(0, 80), 0])
            for n, (pts, elapsed, ok) in enumerate(parts):
                rows.append([pts, elapsed, f'{label.split(". ", 1)[1].lower()}-{n}',
                             200 if ok else 500, 'OK' if ok else 'Internal Server Error',
                             thread, 'text', str(ok).lower(),
                             '' if ok else 'Test failed', rng.randint(100, 20000),
                             rng.randint(300, 900), threads, threads,
                             f'https://app.example.test/api/step{si + 1}/{n}',
                             max(0, elapsed - 2), 0, rng.randint(0, 5)])
            ts = cursor + rng.randint(200, 800)
    rows.sort(key=lambda r: r[0] + r[1])  # JMeter writes in completion order
    return rows


def write_jtl(path, **kwargs):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(generate(**kwargs))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('output')
    ap.add_argument('--iterations', type=int, default=20)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--threads', type=int, default=2)
    a = ap.parse_args()
    write_jtl(a.output, iterations=a.iterations, seed=a.seed, threads=a.threads)
    print(f'written {a.output}')
