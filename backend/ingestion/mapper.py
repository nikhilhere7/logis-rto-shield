"""Guess which column in the merchant's file matches each canonical field."""
import difflib
import re


def norm(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def suggest_mapping(columns, spec):
    """Returns {canonical_field: source_column or None}. Each source column is used at most once."""
    by_norm = {}
    for c in columns:
        by_norm.setdefault(norm(c), c)
    mapping, used = {}, set()

    # pass 1: exact match on the canonical name or a known alias
    for f in spec.fields:
        for cand in (norm(f.name),) + tuple(norm(a) for a in f.aliases):
            src = by_norm.get(cand)
            if src and src not in used:
                mapping[f.name] = src
                used.add(src)
                break

    # pass 2: fuzzy match for whatever is left
    for f in spec.fields:
        if f.name in mapping:
            continue
        left = [n for n, c in by_norm.items() if c not in used]
        best, score = None, 0.0
        for cand in (norm(f.name),) + tuple(norm(a) for a in f.aliases):
            for hit in difflib.get_close_matches(cand, left, n=1, cutoff=0.86):
                s = difflib.SequenceMatcher(None, cand, hit).ratio()
                if s > score:
                    best, score = hit, s
        if best:
            mapping[f.name] = by_norm[best]
            used.add(by_norm[best])
        else:
            mapping[f.name] = None
    return mapping
