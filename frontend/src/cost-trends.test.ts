import { expect,it } from 'vitest';
import {sumDecimals,costTrends} from './cost-trends';
it('preserves decimal precision and handles duplicate clinic labels and inactive months',()=>{
 expect(sumDecimals(['0.10','0.20','-0.01'])).toBe('0.29');
 expect(sumDecimals(['9999999999999999.99','0.01'])).toBe('10000000000000000.00');
 const result=costTrends([{start:'2026-01-01',staff:[],clinic_costs:[{label:'Rent',total:'0.10'},{label:'Rent',total:'0.20'}]},{start:'2026-02-01',staff:[],clinic_costs:[]}]);
 expect(result.rows[0]['Clinic: Rent']).toBe('0.30');expect(result.rows[1]['Clinic: Rent']).toBe('0');
});
