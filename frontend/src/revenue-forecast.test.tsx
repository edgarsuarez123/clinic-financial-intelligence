import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import RevenueForecast from "./revenue-forecast";
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('./api',async(original)=>({...await original<typeof import('./api')>(),api:mocks.api}));
vi.mock('./components',async(original)=>({...await original<typeof import('./components')>(),Chart:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
it('refuses sparse history, renders a validated forecast and hides stale results after changing dates',async()=>{
  let sparse=true;
  mocks.api.mockImplementation(async(path:string)=>{
    if(!path.startsWith('/simulations/forecast'))return {clinic_locations:[]};
    if(sparse)throw new Error('Import at least 24 complete months.');
    expect(path).toContain('clinic_location=North');
    return {currency:'USD',start:'2024-01-01',end:'2025-12-31',clinic_location:'North',periods:[{period:'2026-01-01',revenue:'15000.00',lower_80:'14000.00',upper_80:'16000.00'}],validation_mae:'1000.00',method:'last_month',history_months:24};
  });
  render(<RevenueForecast defaultStart="2024-01-01" defaultEnd="2025-12-31" defaultClinic="North"/>);
  fireEvent.click(screen.getByRole('button',{name:'Run forecast'}));
  expect((await screen.findByRole('alert')).textContent).toContain('24 complete months');
  sparse=false;fireEvent.click(screen.getByRole('button',{name:'Run forecast'}));
  expect(await screen.findByText('Next month revenue')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Forecast history through'),{target:{value:'2025-11-30'}});
  expect(screen.queryByText('Next month revenue')).toBeNull();
  expect(screen.getByText('Selection changed. Run forecast to update the results.')).toBeTruthy();
});
