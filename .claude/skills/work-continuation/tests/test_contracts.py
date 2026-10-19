"""Offline tests: syntax and claim safety, not external-provider acceptance."""
from __future__ import annotations
import copy
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('portable_validator', ROOT/'scripts/validate_package.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def sample(name):
    return json.loads((ROOT/'templates'/name).read_text('utf-8'))

class ContractTests(unittest.TestCase):
    def test_bundle_integrity(self): self.assertEqual(mod.validate_package(ROOT), [])
    def test_non_git_state_accepted(self): self.assertEqual(mod.validate_state(sample('state.example.json')),[])
    def test_capabilities_are_dynamic(self): self.assertEqual(mod.validate_profile(sample('capability-profile.example.json')),[])
    def test_unknown_capability_rejected(self):
        p=sample('capability-profile.example.json'); p['capabilities']['git']='assumed'
        self.assertTrue(mod.validate_profile(p))
    def test_done_requires_primary_evidence(self):
        s=sample('state.example.json');s['checkpoint']['status']='DONE_VERIFIED'
        self.assertTrue(mod.validate_state(s))
    def test_verified_source_requires_version_and_observed_at(self):
        s=sample('state.example.json');s['verification_status']='VERIFIED_CURRENT'
        self.assertTrue(mod.validate_state(s))
    def test_verified_unit_requires_evidence(self):
        s=sample('state.example.json');s['units'][0]['status']='VERIFIED_CURRENT'
        self.assertTrue(mod.validate_state(s))
    def test_backup_verified_requires_readback(self):
        s=sample('state.example.json');s['backup']['status']='BACKUP_VERIFIED'
        self.assertTrue(mod.validate_state(s))
    def test_unrun_receipt_has_no_exit_code(self):
        r=sample('unit-receipt.example.json');r['exit_code']=0
        self.assertTrue(mod.validate_receipt(r))
    def test_shards_cannot_claim_contiguous(self):
        r=sample('unit-receipt.example.json');r['result_scope']='SHARDED_VERIFICATION';r['consecutive_full_run_proven']=True
        self.assertTrue(mod.validate_receipt(r))
    def test_external_action_must_not_claim_effect(self):
        a=sample('external-action.example.json');a['status']='EFFECT_VERIFIED'
        self.assertTrue(mod.validate_external(a))
    def test_no_git_required_for_document(self):
        s=sample('state.example.json');self.assertIsNone(s['optional_git_context']);self.assertEqual(s['task_kind'],'document')
    def test_validity_canonical_order(self):
        self.assertEqual(mod.canonical_validity_digest({'a':1,'b':2}),mod.canonical_validity_digest({'b':2,'a':1}))
    def test_changed_base_invalidates_key(self):
        a={'tree':'t1','base_head':'h1'};b={'tree':'t1','base_head':'h2'}
        self.assertNotEqual(mod.canonical_validity_digest(a),mod.canonical_validity_digest(b))
    def test_sample_backup_is_unverified(self):
        self.assertEqual(sample('state.example.json')['backup']['status'],'BACKUP_PENDING')
    def test_core_provider_neutral(self):
        s=(ROOT/'SKILL.md').read_text('utf-8')
        self.assertIn('agent-neutral',s)
        self.assertIn('project-neutral',s)
        self.assertNotIn('services/sahool-platform',s)
    def test_en_and_ar_self_contained_prompt(self):
        for name in ('UNIVERSAL_RESUME_AR.md','UNIVERSAL_RESUME_EN.md'):
            text=(ROOT/'prompts'/name).read_text('utf-8')
            self.assertGreater(len(text),400)
            self.assertIn('BACKUP_PENDING',text)
    def test_manifest_detects_modified_skill(self):
        with tempfile.TemporaryDirectory() as td:
            fake=Path(td)
            (fake/'SKILL.md').write_text((ROOT/'SKILL.md').read_text('utf-8')+'tamper',encoding='utf-8')
            (fake/'SHA256SUMS').write_text((ROOT/'SHA256SUMS').read_text('utf-8'),encoding='utf-8')
            errors=mod.validate_package(fake)
            self.assertTrue(errors)

if __name__=='__main__': unittest.main()
