"""
diag_mfrr.py - why does the mFRR sha256 change between identical requests?
Fetches the same URL twice and narrows down the difference, layer by layer.
Temporary debugging tool: not part of the pipeline.

Run:  python diag_mfrr.py
"""
import hashlib
import json
from datetime import date

import requests

from ingest_svk import build_mfrr_url   # the exact URL the pipeline uses

url = build_mfrr_url(date(2026, 9, 26))
a = requests.get(url, timeout=60)
b = requests.get(url, timeout=60)

# Layer 1: the raw bytes (what sha256 sees)
print("bytes identical:  ", a.content == b.content)
print("sha256 a:", hashlib.sha256(a.content).hexdigest()[:16])
print("sha256 b:", hashlib.sha256(b.content).hexdigest()[:16])

ja, jb = a.json(), b.json()

# Layer 2: top-level parts of the answer (help, success, result, ...)
for key in sorted(set(ja) | set(jb)):
    if ja.get(key) != jb.get(key):
        print("DIFFERENT top-level key:", key)

ra, rb = ja["result"], jb["result"]

# Layer 3: parts inside "result" other than the rows themselves
for key in sorted(set(ra) | set(rb)):
    if key != "records" and ra.get(key) != rb.get(key):
        print("DIFFERENT result key:", key)
        print("   a:", str(ra.get(key))[:200])
        print("   b:", str(rb.get(key))[:200])

# Layer 4: the rows. Same rows in a different order, or different values?
recs_a, recs_b = ra["records"], rb["records"]
print("rows a / b:", len(recs_a), "/", len(recs_b))
print("same order:       ", recs_a == recs_b)

def as_set(recs):
    # sort_keys makes each row's text independent of key order
    return {json.dumps(r, sort_keys=True) for r in recs}

print("same rows (any order):", as_set(recs_a) == as_set(recs_b))

# If the order differs, show the first position where it does
for i, (x, y) in enumerate(zip(recs_a, recs_b)):
    if x != y:
        print(f"first difference at row {i}:")
        print("   a:", x)
        print("   b:", y)
        break
