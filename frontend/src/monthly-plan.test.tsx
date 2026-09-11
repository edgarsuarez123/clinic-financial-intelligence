import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {useState} from 'react';
import MonthlyPlan,{adjustDecimal} from './monthly-plan';
import {newPlan} from './types';
afterEach(cleanup);
it('changes only the selected future months and fills explicit zero without treating it as missing',()=>{
  function Example(){const [p,set]=useState({...newPlan(),months:3,existing_monthly_revenue:'1000.25'});return <MonthlyPlan plan={p} onChange={set}/>;}
  render(<Example/>);
  fireEvent.change(screen.getByLabelText('From month'),{target:{value:'2'}});
  fireEvent.change(screen.getByLabelText('Change %'),{target:{value:'10'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply % forward'}));
  expect((screen.getByLabelText('Month 1 revenue') as HTMLInputElement).value).toBe('1000.25');
  expect((screen.getByLabelText('Month 2 revenue') as HTMLInputElement).value).toBe('1100.28');
  fireEvent.change(screen.getByLabelText('Month 2 revenue'),{target:{value:'0'}});
  fireEvent.click(screen.getByRole('button',{name:'Fill forward'}));
  expect((screen.getByLabelText('Month 3 revenue') as HTMLInputElement).value).toBe('0');
  expect(adjustDecimal('999999999999.99','0.01')).toBe('1000099999999.99');
});
