import { expect, it } from 'vitest';
import { compareSceneFreshness, compareSceneProvenance } from './sceneFreshness';
import { satelliteArchiveLayer } from '../components/fieldhealth/satelliteArchive';
import { timelineRecordByDay } from '../components/fieldhealth/timelineByDay';
import { dateHasPersistedCog } from '../components/maphub/persistedCog';

const captured = '2024-02-27T01:35:20+03:00';
const day = '2024-02-26';
const asset = {date:captured, has_cog:true, indices:['NDVI']};

it('matches the layer and strip on the UTC day and rejects the following day', () => {
  expect(compareSceneFreshness(captured, day).level).toBe('match');
  expect(compareSceneFreshness(captured, '2024-02-27').level).toBe('mismatch');
});
it('keeps the timestamped catalog asset available on the UTC day', () => {
  expect(dateHasPersistedCog('ndvi', day, [asset])).toBe(true);
  expect(timelineRecordByDay([asset]).get(day)).toBe(asset);
});
it('uses the stored segment for an exact UTC observation even without a catalog row', () => {
  expect(satelliteArchiveLayer('vegetation','ndvi',day,[],[{datetime:captured}]).stored).toBe(true);
});
it('invalid dated measurements cannot select a stored layer or earn a freshness badge', () => {
  expect(compareSceneFreshness('2024-02-31','2024-02-31').level).toBe('unknown');
  expect(satelliteArchiveLayer('vegetation','ndvi','latest',[],[{datetime:'invalid'}]).stored).toBe(false);
});
it('a shared boundary revision cannot override a conflicting capture day', () => {
  expect(compareSceneProvenance({field_revision:1,captured_at:day},
    {field_revision:1,captured_at:'2024-02-27'}).level).toBe('mismatch');
});
