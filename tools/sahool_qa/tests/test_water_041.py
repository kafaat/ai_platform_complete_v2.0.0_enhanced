"""Counterexamples from the 0.4.0 review; no optional DB dependency."""
import copy
import datetime as dt
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sahool_qa.config import DEFAULT_RULES, validate_water_rules
from sahool_qa.demo import write_demo
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.items import GenContext
from sahool_qa.waterbal import Series, window_delta, daily_increments, balance, kc_refs
from sahool_qa.facts import Indicator
from sahool_qa.generators import water
from sahool_qa.audit import audit
from sahool_qa.pipeline import generate, fingerprint
from sahool_qa.preview import evidence_line


class RawMeters(unittest.TestCase):
    def series(self, rows):
        s=Series('meter','meter_total_X')
        for stamp,v in rows:
            t=dt.datetime.fromisoformat(stamp)
            s.records.setdefault(t.date(),[]).append(Indicator('f',s.indicator_id,v,t,conv=v))
        return s

    def test_reset_hidden_by_later_recovery_is_unknown(self):
        s=self.series([('2026-01-01T21:00',100),('2026-01-02T08:00',150),
                       ('2026-01-02T09:00',0),('2026-01-02T21:00',200)])
        a,b=dt.date(2026,1,1),dt.date(2026,1,2)
        self.assertEqual(window_delta(s,a,b),(None,'meter_decrease'))
        self.assertEqual(daily_increments(s,a,b),(None,'meter_decrease',b))

    def test_reset_before_starting_endpoint_does_not_poison_window(self):
        s=self.series([('2026-01-01T08:00',999),('2026-01-01T09:00',0),
                       ('2026-01-01T21:00',100),('2026-01-02T21:00',150)])
        self.assertEqual(window_delta(s,dt.date(2026,1,1),dt.date(2026,1,2)),(50,None))

    def test_conflicting_same_timestamp_is_unknown(self):
        s=self.series([('2026-01-01T21:00',100),('2026-01-02T10:00',150),
                       ('2026-01-02T10:00',160),('2026-01-02T21:00',200)])
        self.assertEqual(window_delta(s,dt.date(2026,1,1),dt.date(2026,1,2)),(None,'meter_timestamp_conflict'))

    def test_monotone_subdaily_and_missing_interior_day(self):
        s=self.series([('2026-01-01T21:00',100),('2026-01-03T08:00',120),('2026-01-03T21:00',150)])
        a,b=dt.date(2026,1,1),dt.date(2026,1,3)
        self.assertEqual(window_delta(s,a,b),(50,None))
        self.assertEqual(daily_increments(s,a,b)[1],'missing_daily_reading')


class WaterPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.fx,_=write_demo(cls.tmp.name)
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def ctx(self):
        s=load_fixture(str(self.fx),'demo-tenant');rules=copy.deepcopy(DEFAULT_RULES);s.prepare(rules)
        return GenContext(s,rules)
    def fw(self,ctx,fid='demo_pivot_1'):
        return next(w for w in water._fw(ctx).values() if w.field.id==fid)
    def window(self,ctx):
        return water.irrigation_window(ctx,self.fw(ctx),dt.date(2026,1,5),dt.date(2026,1,12))
    def remove(self,ctx,*ids):
        ctx.store.indicators=[r for r in ctx.store.indicators if not(r.field_id=='demo_pivot_1' and r.indicator_id in ids)]
        ctx.cache.clear()

    def test_missing_volume_stream_with_hours_is_unknown(self):
        c=self.ctx();self.remove(c,'meter_total_P1B')
        self.assertEqual(self.window(c)['problem'],'missing_expected_meter')
        self.assertNotIn('depth',self.window(c))

    def test_both_streams_removed_still_detected_by_inventory(self):
        c=self.ctx();self.remove(c,'meter_total_P1B','pump_hours_P1B')
        self.assertEqual(self.window(c)['problem'],'missing_expected_meter')
        fw=self.fw(c)
        self.assertEqual(water.irrigation_daily(c,fw,dt.date(2026,1,5),dt.date(2026,1,12))[1],'missing_expected_meter')

    def test_no_inventory_cannot_assert_total(self):
        c=self.ctx();c.store.provenance.pop('water_well_inventory')
        self.assertEqual(self.window(c)['problem'],'well_inventory_missing')

    def test_inventory_tenant_and_period_are_respected(self):
        c=self.ctx();key=self.fw(c).field.key
        inv=c.store.provenance['water_well_inventory'].pop(key)
        c.store.provenance['water_well_inventory']['other-tenant::demo_pivot_1']=inv
        self.assertEqual(self.window(c)['problem'],'well_inventory_missing')
        c.rules['water']['well_inventory'][key]=[{'from':'2026-01-06','to':'2026-12-31','wells':['P1A','P1B']}]
        self.assertEqual(self.window(c)['problem'],'well_inventory_gap')

    def test_assignment_change_and_unassigned_stream_are_unknown(self):
        c=self.ctx();key=self.fw(c).field.key
        c.rules['water']['well_inventory'][key]=[
          {'from':'2025-01-01','to':'2026-01-08','wells':['P1A','P1B']},
          {'from':'2026-01-09','to':'2026-12-31','wells':['P1A']}]
        self.assertEqual(self.window(c)['problem'],'well_assignment_changed')
        c.rules['water']['well_inventory'][key]=[{'from':'2025-01-01','to':'2026-12-31','wells':['P1A']}]
        self.assertEqual(self.window(c)['problem'],'unassigned_meter')

    def test_fixture_inventory_respects_tenant_scope(self):
        data=json.loads(Path(self.fx).read_text())
        data['sahool_qa']['provenance']['water_well_inventory']['other-tenant::secret-field']=[
            {'from':'2025-01-01','to':'2026-12-31','wells':['secret-well']}]
        with tempfile.TemporaryDirectory() as tmp:
            fp=Path(tmp)/'fx.json';fp.write_text(json.dumps(data))
            st=load_fixture(str(fp),'demo-tenant')
        self.assertNotIn('other-tenant::secret-field',st.provenance['water_well_inventory'])

    def test_inventory_affects_fingerprint(self):
        c=self.ctx();old=fingerprint(c.store)
        c.store.provenance['water_well_inventory']['demo-tenant::demo_pivot_1'][0]['wells']=['P1A']
        self.assertNotEqual(old,fingerprint(c.store))

    def test_audit_sees_intraday_reset(self):
        c=self.ctx();fw=self.fw(c);s=fw.of('meter')['p1a'];d=dt.date(2026,1,7)
        template=s.records[d][0]
        for hour,v in [(9,200000),(10,0)]:
            r=copy.deepcopy(template);r.recorded_ts=r.recorded_ts.replace(hour=hour);r.value=r.conv=v
            c.store.indicators.append(r)
        issues=audit(c.store,c.rules)
        self.assertTrue(any(i['code']=='cumulative_meter_decrease' and i.get('timestamp','').startswith('2026-01-07T10:') for i in issues))

    def change_pivot(self,c,kind,fn):
        fw=self.fw(c)
        for s in fw.of(kind).values():
            start=s.days()[0]
            for day,rs in s.records.items():
                for r in rs:r.value=r.conv=fn((day-start).days)
        c.cache['water'].pop('stress',None)

    def test_zero_flow_without_status_is_unknown_and_preserves_other_fields(self):
        # 0.4.2: hours advance while the volume meter stays flat. A stuck meter, a dry well and a
        # closed valve look the same, so neither the depth nor the flow is a known zero.
        c=self.ctx();self.change_pivot(c,'meter',lambda k:1000.)
        stress=[i for i in water.gen_stress_status(c) if i['field_refs'][0].endswith('demo_pivot_1')]
        self.assertTrue(stress)
        self.assertTrue(all(not i['answerable'] and i['evidence']['values']['problem']=='volume_meter_stalled' for i in stress))
        items=list(water.gen_refill_feasibility(c))
        self.assertFalse([i for i in items if any(r.get('field_id')=='demo_pivot_1' for r in i['evidence']['records'])])
        self.assertTrue(items)                                   # other fields keep their questions
        self.assertFalse(c.cache.get('case_errors'))
        depth=water.irrigation_window(c,self.fw(c),dt.date(2026,1,5),dt.date(2026,1,12))
        self.assertEqual(depth['problem'],'volume_meter_stalled')
        self.assertIn('volume_meter_stalled',[i['code'] for i in audit(c.store,c.rules)])

    def test_fractional_hours_not_rounded_before_division(self):
        c=self.ctx();self.change_pivot(c,'pump_hours',lambda k:10+k*.0005)
        items=list(water.gen_refill_feasibility(c))
        self.assertFalse(c.cache.get('case_errors'))
        item=next(i for i in items if i['answerable'] and any(r.get('field_id')=='demo_pivot_1' for r in i['evidence']['records']))
        for f in item['evidence']['values']['flows'].values():
            self.assertAlmostEqual(f['hours'],.0035,places=8)
            self.assertAlmostEqual(f['flow_m3_h'],f['volume_m3']/f['hours'])

    def test_case_error_is_reported_without_dropping_whole_family(self):
        c=self.ctx();original=water._gen_refill_cases
        def broken(ctx,cases):
            if cases[0]['field'].id=='demo_pivot_1':raise ValueError('injected case failure')
            yield from original(ctx,cases)
        with patch.object(water,'_gen_refill_cases',broken):
            items=list(water.gen_refill_feasibility(c))
        self.assertTrue(items);self.assertTrue(c.cache['case_errors'])
        self.assertTrue(all(e['field_key']=='demo-tenant::demo_pivot_1' for e in c.cache['case_errors']))

    def test_pipeline_zero_flow_has_no_family_or_case_errors(self):
        c=self.ctx();self.change_pivot(c,'meter',lambda k:1000.)
        with tempfile.TemporaryDirectory() as tmp:
            m=generate(c.store,c.rules,str(Path(tmp)/'qa'),families='water.refill_feasibility',images=False)
        self.assertFalse(m['family_errors']);self.assertFalse(m['case_errors']);self.assertGreater(m['counts']['items_total'],0)

    def test_answerable_balance_has_precise_kc_record_refs(self):
        c=self.ctx()
        for i in list(water.gen_stress_status(c))+list(water.gen_refill_feasibility(c)):
            if not i['answerable']:continue
            refs=[r for r in i['evidence']['records'] if r.get('indicator_id')=='kc']
            self.assertTrue(refs,i['id']);self.assertTrue(all(r['record_keys'] and r['recorded_at'] for r in refs))
        fw=self.fw(c);s=next(iter(fw.of('kc').values()))
        refs=kc_refs(s,dt.date(2026,1,6),dt.date(2026,1,19))
        self.assertEqual([r['from'] for r in refs],['2025-12-20','2026-01-15'])


class WaterBalanceAndPresentation(unittest.TestCase):
    def test_extreme_accepted_inputs_conserve_mass_and_available_water(self):
        prm={'fc':.12,'wp':.045,'zr':.4,'p_table':.35,'ea':.8,'taw':30.}
        d=dt.date(2026,1,1)
        dr0,rows=balance(prm,.0475,[d],{d:20},{d:1.6},{d:0},{d:0})
        row=rows[0]
        self.assertAlmostEqual(row['eta'],1.)
        self.assertAlmostEqual(row['dr_end'],dr0-row['rain']-row['irr_net']+row['eta']+row['dp'])

    def test_mass_balance_grid_wet_dry_and_stressed(self):
        prm={'fc':.12,'wp':.045,'zr':.4,'p_table':.35,'ea':.8,'taw':30.};d=dt.date(2026,1,1)
        for theta in [.045,.0475,.10,.12]:
            for rain in [0,5,40]:
                for irr in [0,10,50]:
                    dr0,(row,)=balance(prm,theta,[d],{d:20},{d:1.6},{d:rain},{d:irr})
                    self.assertAlmostEqual(row['dr_end'],dr0-rain-.8*irr+row['eta']+row['dp'])
                    self.assertLessEqual(row['eta'],30-dr0+rain+.8*irr+1e-10)
                    self.assertTrue(0<=row['dr_end']<=30)

    def test_invalid_pump_and_efficiency_rules_rejected(self):
        for key,values in {'application_efficiency':[0,-1,1.1,float('nan')],
                           'max_pump_hours_per_day':[0,25,float('inf')],
                           'check_every_days':[0,1.5], 'flow_window_days':[0]}.items():
            for v in values:
                rules=copy.deepcopy(DEFAULT_RULES);rules['water'][key]=v
                with self.assertRaises(ValueError,msg=(key,v)):validate_water_rules(rules)

    def test_formula_is_one_ltr_block_with_original_operand_order(self):
        formula='p = min(0.8, max(0.1, p_table + 0.04 × (5 − ETc)))'
        result=evidence_line(formula)
        self.assertIn('class="formula" dir="ltr"',result)
        self.assertIn('(5 − ETc)',result)
        self.assertNotIn('<span',result)
        self.assertNotIn('<script>',evidence_line('<script>alert(1)</script>'))
