import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
const state=vi.hoisted(()=>({fieldId:'a',error:false,refetch:vi.fn(),save:vi.fn()}));
vi.mock('../hooks/useSelectedField',()=>({useSelectedField:()=>({fieldId:state.fieldId,options:[{id:'a',name:'A'},{id:'b',name:'B'}],setFieldId:vi.fn()})}));
vi.mock('../hooks/useApi',()=>({useLabSamples:()=>({data:[],isLoading:false,isError:false,refetch:state.refetch}),useLabDecisionContext:()=>({isLoading:false,isError:state.error,error:new Error('offline'),data:undefined,refetch:state.refetch}),useCreateLabSample:()=>({mutateAsync:state.save,isPending:false}),useSubmitSoilLabResult:()=>({mutateAsync:state.save,isPending:false})}));
vi.mock('react-router',()=>({useLocation:()=>({state:null}),useNavigate:()=>vi.fn()}));
vi.mock('../lib/leafletSetup',()=>({}));
vi.mock('react-leaflet',()=>({MapContainer:({children}:any)=><div>{children}</div>,TileLayer:()=>null,Polygon:()=>null,Marker:()=>null,useMapEvents:()=>({})}));
import LabSamplingPage from './LabSamplingPage';
beforeEach(()=>{cleanup();state.fieldId='a';state.error=false;vi.clearAllMocks();});
describe('lab context repairs',()=>{
 it('does not carry coordinates into a different field',()=>{
   const view=render(<LabSamplingPage/>);
   fireEvent.change(screen.getByRole('spinbutton',{name:'Latitude'}),{target:{value:'15'}});
   fireEvent.change(screen.getByRole('spinbutton',{name:'Longitude'}),{target:{value:'44'}});
   expect(screen.getByRole('spinbutton',{name:'Latitude'})).toHaveValue(15);
   state.fieldId='b';view.rerender(<LabSamplingPage/>);
   expect(screen.getByRole('spinbutton',{name:'Latitude'})).toHaveValue(null);
   expect(screen.getByRole('spinbutton',{name:'Longitude'})).toHaveValue(null);
 });
 it('renders context failure with retry instead of missing data',()=>{
   state.error=true;render(<LabSamplingPage/>);
   expect(screen.getByText('تعذّر تحميل سياق المختبر')).toBeInTheDocument();
   expect(screen.queryByText('لا يوجد سياق قرار متاح بعد.')).not.toBeInTheDocument();
   fireEvent.click(screen.getByRole('button',{name:/إعادة/}));
   expect(state.refetch).toHaveBeenCalledTimes(1);
 });
});
