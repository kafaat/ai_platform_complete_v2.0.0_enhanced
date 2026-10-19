#!/usr/bin/env python3
"""Offline, conservative draft suggestions from an experience journal.

Never edits skill files, never executes captured content, never proposes adoption.
The journal hash chain is checked for internal consistency, not authenticity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


def canon(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(value: object) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def load_observations(journal: Path) -> list[dict]:
    if journal.is_symlink() or not journal.is_file():
        raise ValueError('regular local journal required')
    if journal.stat().st_size > 2_000_000:
        raise ValueError('journal over retention budget')
    raw = journal.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('partial journal line')
    prev, seen, out = '0' * 64, set(), []
    for n, rawline in enumerate(raw.splitlines(), 1):
        entry = json.loads(rawline.decode('utf-8'))
        if not isinstance(entry, dict) or set(entry) != {'schema', 'seq', 'recorded_at', 'previous_hash', 'observation', 'verification', 'event_hash'}:
            raise ValueError(f'journal line {n}: malformed event')
        if entry['schema'] != 'uwrp.experience-event.v1' or entry['seq'] != n or entry['previous_hash'] != prev:
            raise ValueError(f'journal line {n}: invalid sequence or chain')
        if entry['verification'] != 'RECORDED_UNVERIFIED':
            raise ValueError('unsupported trust claim')
        actual = sha({k: v for k, v in entry.items() if k != 'event_hash'})
        if actual != entry['event_hash']:
            raise ValueError(f'journal line {n}: digest mismatch')
        obs = entry['observation']
        if not isinstance(obs, dict) or obs.get('schema') != 'uwrp.experience.v1':
            raise ValueError('invalid observation schema')
        if obs.get('observation_id') in seen:
            raise ValueError('duplicate observation ID')
        for key in ['skill_name', 'signal', 'evidence_digest', 'evidence_ref', 'observation_id']:
            if not isinstance(obs.get(key), str):
                raise ValueError('missing observation field: ' + key)
        seen.add(obs['observation_id'])
        out.append(obs)
        prev = actual
    return out


def make_drafts(observations: list[dict], min_independent: int = 2) -> dict:
    if not isinstance(min_independent, int) or min_independent < 2:
        raise ValueError('min independent evidence count must be >= 2')
    groups = defaultdict(list)
    for o in observations:
        groups[(o['skill_name'], o['signal'])].append(o)
    proposed, insuff = [], []
    for (name, signal), obs in sorted(groups.items()):
        independent = sorted({o['evidence_digest'] for o in obs})
        item = {'skill_name': name, 'signal': signal,
                'observations': sorted(o['observation_id'] for o in obs),
                'unique_evidence_count': len(independent)}
        if len(independent) < min_independent:
            insuff.append(item)
            continue
        item.update({'proposal_id': 'CAND-' + sha(item)[:16],
                     'status': 'DRAFT_REQUIRES_EVIDENCE_REVIEW',
                     'evidence_refs': sorted({o['evidence_ref'] for o in obs}),
                     'suggested_next_step': 'Verify root cause, specify a minimal change, and design blind A/B tests with safety gates.',
                     'authorized_to_change_skill': False,
                     'authorized_to_publish': False})
        proposed.append(item)
    return {'schema': 'uwrp.improvement-proposals.v1',
            'source_trust': 'RECORDED_UNVERIFIED',
            'journal_integrity': 'HASH_CHAIN_CHECKED_NOT_AUTHENTICITY',
            'proposal_count': len(proposed),
            'proposals': proposed, 'insufficient_evidence': insuff,
            'approval': 'NOT_REQUESTED', 'can_auto_apply': False}


def write_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.draft-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(canon(document) + b'\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--journal', type=Path, required=True)
    p.add_argument('--min-independent', type=int, default=2)
    p.add_argument('--out', type=Path, help='Optional local draft path outside source checkout')
    args = p.parse_args(argv)
    try:
        report = make_drafts(load_observations(args.journal), args.min_independent)
        if args.out:
            if args.out.is_symlink():
                raise ValueError('output symlink refused')
            write_atomic(args.out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print('REFUSED:', str(e), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
