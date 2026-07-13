import {blockedUseExplanation,buildSoilWorkspaceSummary} from './soilWorkspace';
describe('soil workspace',()=>{
 it('explains blocked action',()=>expect(blockedUseExplanation({actionType:'gypsum_rate',allowed:false,reasons:['approved_water_profile_required'],approvalRequirement:'soil_specialist'})).toContain('approved_water'));
 it('builds completeness and pending execution',()=>{
  const s=buildSoilWorkspaceSummary({profile_hash:'h',evidence_level:'lab_verified',quality_gate:{completed_properties:8,required_properties:10},blocked_use:['gypsum_rate']},{executions:[{}]});
  expect(s.completenessPct).toBe(80); expect(s.pendingApprovals).toBe(1);
 });
});
