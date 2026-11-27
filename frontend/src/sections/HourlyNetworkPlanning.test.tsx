import { describe, expect, it } from 'vitest';
import { hourlyPayload } from './HourlyNetworkPlanning';
const sample = {source:'test',start:'2026-01-01T10:00',capacity:'80',derate:'.85',temperatureCoefficient:'-.004',
  curve:'100,80,.75\n200,70,.8',hours:'200,60,70,80,800,25'};
describe('hourly network form',()=>{
  it('binds every flow to this field and preserves the UTC start',()=>{
    const p=hourlyPayload(sample,'pivot2');
    expect(p.start_at).toBe('2026-01-01T10:00:00.000Z');
    expect(p.hours[0].well_inflows_m3_h).toEqual({'well:pivot2:1':60,'well:pivot2:2':70,'well:pivot2:3':80});
  });
  it('rejects blank cells instead of assigning zero flow',()=>{
    expect(()=>hourlyPayload({...sample,hours:'200,60,,80,800,25'},'a')).toThrow();
  });
});
