import {expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import {TaskSatelliteEvidence} from './TaskSatelliteEvidence';

it('displays recorded zero slopes and the resolution and units of saved DEM evidence', () => {
  render(<TaskSatelliteEvidence field="wheat" terrain={[
    {kind:'field_record',source_key:'record',slope_pct:0,aspect:'FLAT',summaries:{}},
    {kind:'dem_product',source_key:'dem',dem_version:'glo30',cell_size_m:30,
      summaries:{slope_deg:{min:0,mean:1,max:2},wadi_distance_m:{min:5,mean:10,max:15}}},
  ]}/>);
  expect(screen.getByText('الميل: 0%')).toBeInTheDocument();
  expect(screen.getByText('حجم خلية النموذج: 30 م')).toBeInTheDocument();
  expect(screen.getByText('الميل (درجة)')).toBeInTheDocument();
  expect(screen.getByText('المسافة إلى الوادي وتراكم الجريان غير محسوبين.')).toBeInTheDocument();
  expect(screen.queryByText('15')).toBeNull();
});
