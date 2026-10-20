"""Validate one or more case JSON files without loading the whole catalogue.
Usage: .venv/bin/python scripts/check_cases.py cases/pediatric/more.json [...]
Exit code 1 on the first invalid case; prints a per-difficulty summary."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import importlib

store = importlib.import_module("case_store.__init__" if False else "case_store")


def main(paths):
    topic_ids = {t["id"] for t in store.load_topics()}
    seen, counts = set(), Counter()
    for p in paths:
        docs = json.loads(Path(p).read_text(encoding="utf-8"))
        for doc in docs if isinstance(docs, list) else [docs]:
            try:
                c = doc if "hidden_facts" in doc else store.expand(doc)
                store.validate(c, topic_ids)
            except Exception as e:  # noqa: BLE001 - report any authoring error
                print(f"INVALID {p} :: {doc.get('id') or doc.get('case_id')} :: {e!r}")
                return 1
            cid = c["case_id"]
            if cid in seen:
                print(f"DUPLICATE id in batch: {cid}")
                return 1
            seen.add(cid)
            counts[c["difficulty"]] += 1
    print(f"OK {len(seen)} cases", dict(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
