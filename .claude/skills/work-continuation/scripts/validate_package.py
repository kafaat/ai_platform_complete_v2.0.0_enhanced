#!/usr/bin/env python3
"""Offline, read-only UWRP portable bundle lint. Not an agent/runtime certification."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

VALID_CAPABILITIES = {'available', 'unavailable', 'unknown', 'not_applicable'}
MODES = {'LIGHT', 'CHECKPOINTED', 'COORDINATED'}
KINDS = {'creative', 'research', 'document', 'code', 'operations', 'mixed'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_validity_digest(fields: dict) -> str:
    """Identity of the *declared relevant* inputs, not proof that selection is complete."""
    return 'sha256:' + sha(json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def validate_state(state: dict) -> list[str]:
    errors = []
    if state.get('schema_version') != 'uwrp/state/v3.1':
        errors.append('state version')
    if state.get('task_kind') not in KINDS or state.get('mode') not in MODES:
        errors.append('invalid task mode or kind')
    if state.get('optional_git_context') is not None and state.get('task_kind') != 'code':
        # Git is allowed in mixed/docs/research tasks, so don't impose type requirements.
        pass
    if state.get('checkpoint', {}).get('status') == 'DONE_VERIFIED':
        if state.get('verification_status') != 'VERIFIED_CURRENT' or not state.get('checkpoint', {}).get('last_verified_evidence'):
            errors.append('completion lacks current primary evidence')
    if state.get('verification_status') == 'VERIFIED_CURRENT' and not any(
        (s.get('content_sha256') or s.get('version_id')) and s.get('observed_at') for s in state.get('sources', [])
    ):
        errors.append('verified state lacks pinned inspected source')
    backup = state.get('backup', {})
    if backup.get('status') == 'BACKUP_VERIFIED' and not all(backup.get(k) for k in ('storage_kind','destination', 'remote_digest', 'verified_at')):
        errors.append('backup verified without remote readback evidence')
    for unit in state.get('units', []):
        if unit.get('status') == 'VERIFIED_CURRENT' and not unit.get('evidence_ref'):
            errors.append('verified unit lacks evidence: '+str(unit.get('unit_id')))
    return errors


def validate_profile(profile: dict) -> list[str]:
    errors=[]
    if profile.get('schema_version') != 'uwrp/profile/v3.1' or profile.get('selected_mode') not in MODES:
        errors.append('profile version/mode')
    if any(value not in VALID_CAPABILITIES for value in profile.get('capabilities', {}).values()):
        errors.append('unknown capability status')
    if not profile.get('capabilities'):
        errors.append('no capability map')
    return errors


def validate_receipt(receipt: dict) -> list[str]:
    errors=[]
    if receipt.get('schema_version') != 'uwrp/unit-receipt/v3.1':
        errors.append('receipt version')
    if receipt.get('status') == 'NOT_RUN' and (receipt.get('exit_code') is not None or receipt.get('result_digest') is not None):
        errors.append('not-run receipt contains results')
    if receipt.get('status') == 'PASSED' and not all(receipt.get(k) for k in ('evidence_ref','validity_key','finished_at')):
        errors.append('pass without evidence and validity')
    if receipt.get('result_scope') == 'SHARDED_VERIFICATION' and receipt.get('consecutive_full_run_proven') is True:
        errors.append('sharded results falsely claim contiguous proof')
    return errors


def validate_external(action: dict) -> list[str]:
    errors=[]
    if action.get('schema_version') != 'uwrp/external-action/v3.1':
        errors.append('action version')
    if action.get('status') == 'NOT_ATTEMPTED' and action.get('attempts') != 0:
        errors.append('unattempted action has attempts')
    if action.get('status') == 'EFFECT_VERIFIED' and not (action.get('target_readback') and action.get('authorization',{}).get('status') == 'VERIFIED'):
        errors.append('external effect not proven or authorized')
    return errors


def package_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.is_file() and not ({'__pycache__','.pytest_cache','.git'} & set(p.relative_to(root).parts)))


def validate_package(root: Path) -> list[str]:
    errors = []
    root = root.resolve()
    skill = root/'SKILL.md'
    if not skill.is_file():
        return ['missing SKILL.md']
    content = skill.read_text('utf-8')
    if not content.startswith('---\n') or not re.search(r'\n---\n', content):
        errors.append('skill frontmatter invalid')
    if not re.search(r'^name: work-continuation$', content, re.M) or not re.search(r'^description:', content, re.M):
        errors.append('required skill metadata invalid')
    if len(content.splitlines()) > 500:
        errors.append('skill too long')
    for r in re.findall(r'`((?:references|prompts|templates)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)`', content):
        if not (root/r).is_file():
            errors.append('missing referenced file '+r)
    expected = ['templates/state.example.json','templates/capability-profile.example.json',
                'templates/unit-receipt.example.json','templates/external-action.example.json',
                'templates/storage-policy.example.json']
    for rel in expected:
        try:
            x=json.loads((root/rel).read_text('utf-8'))
            if x.get('example_only') is not True:
                errors.append(rel+' claims real work')
            if rel.endswith('state.example.json'):
                errors += validate_state(x)
                if x['verification_status']!='RECORDED_UNVERIFIED':
                    errors.append('sample state claims verified')
            if rel.endswith('capability-profile.example.json'):
                errors += validate_profile(x)
            if rel.endswith('unit-receipt.example.json'):
                errors += validate_receipt(x)
            if rel.endswith('external-action.example.json'):
                errors += validate_external(x)
        except Exception as exc:
            errors.append(rel+' invalid JSON: '+str(exc))
    manifest_path=root/'SHA256SUMS'
    if not manifest_path.is_file():
        errors.append('no digest manifest')
    else:
        entries={}
        for line in manifest_path.read_text('utf-8').splitlines():
            m=re.fullmatch(r'([a-f0-9]{64})  ([^\n\\]+)', line)
            if not m: errors.append('bad manifest entry'); continue
            d,rel=m.groups()
            if rel in entries: errors.append('duplicate manifest path '+rel)
            entries[rel]=d
        found={p.relative_to(root).as_posix() for p in package_files(root) if p.name!='SHA256SUMS'}
        if set(entries)!=found:
            errors.append('manifest coverage differs: missing='+str(sorted(found-set(entries)))+' extra='+str(sorted(set(entries)-found)))
        for rel,d in entries.items():
            p=root/rel
            if rel.startswith('/') or '..' in Path(rel).parts or not p.is_file():
                errors.append('unsafe manifest path '+rel)
            elif sha(p.read_bytes())!=d:
                errors.append('digest mismatch: '+rel)
    secrets=[re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
             re.compile(r'\bghp_[a-zA-Z0-9]{25,}\b'),
             re.compile(r'\bgithub_pat_[a-zA-Z0-9_]{25,}\b'),
             re.compile(r'\bAKIA[0-9A-Z]{16}\b')]
    for p in package_files(root):
        if p.is_symlink() or p.suffix in {'.log','.pyc'}:
            errors.append('unsafe bundled file: '+p.relative_to(root).as_posix())
        if p.suffix in {'.md','.json','.py','.txt'}:
            t=p.read_text('utf-8')
            if any(regex.search(t) for regex in secrets):
                errors.append('possible credential: '+p.relative_to(root).as_posix())
    return errors


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ns=ap.parse_args()
    errors=validate_package(ns.root)
    if errors:
        print('\n'.join('FAIL: '+e for e in errors))
        return 1
    print('PASS: offline portable bundle integrity and example contracts')
    print('LIMIT: no agent runtime, remote backup, CI, or provider integration tested')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
