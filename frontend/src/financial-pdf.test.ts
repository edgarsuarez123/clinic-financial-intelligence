import { expect, it } from 'vitest';
import { projectPage, type PDFLayout } from './financial-pdf';
import { financialCSV } from './financial-csv';
const profile={columns:{date:'Date',amount:'Paid',type:'Type',category:'Category',provider:'Provider',medical_insurance:'Insurance',billing_code:'Code'},delimiter:',',date_format:'%Y-%m-%d',allowed_values:{type:['revenue'],category:['Collections'],provider:[],medical_insurance:['Insurer A'],billing_code:['99213']}};
const constant=(value:string)=>({left:0,right:0,constant:value,useConstant:true});
const layout:PDFLayout={firstPage:1,lastPage:1,top:20,bottom:80,columns:{date:constant('2026-01-01'),type:constant('revenue'),category:constant('Collections'),provider:constant(''),medical_insurance:constant('Insurer A'),amount:{left:70,right:90,constant:'',useConstant:false},billing_code:{left:50,right:60,constant:'',useConstant:false}}};
it('projects payment codes and exact amounts without retaining patient columns or outside-table text',()=>{
 const rows=projectPage([{text:'PATIENT SECRET',left:5,right:30,top:40},{text:'99213',left:51,right:58,top:40},{text:'$1,234.50',left:72,right:86,top:40},{text:'Statement header',left:5,right:80,top:10}],layout,profile);
 expect(rows).toEqual([['2026-01-01','1234.50','revenue','Collections','','Insurer A','99213']]);
 expect(JSON.stringify(rows)).not.toContain('SECRET');
 const clean=financialCSV([Object.values(profile.columns),...rows].map(r=>r.join(',')).join('\n'),profile);
 expect(clean.rows).toBe(1);
});
it('rejects ambiguous overlapping columns and cells straddling a boundary',()=>{
 expect(()=>projectPage([], {...layout,columns:{...layout.columns,amount:{left:55,right:80,constant:'',useConstant:false}}},profile)).toThrow();
 expect(()=>projectPage([{text:'secret 99213',left:40,right:59,top:40}],layout,profile)).toThrow();
});
it('does not silently drop incomplete detail rows',()=>{
 const rows=projectPage([{text:'99213',left:51,right:58,top:40}],layout,profile);
 expect(()=>financialCSV([Object.values(profile.columns),...rows].map(r=>r.join(',')).join('\n'),profile)).toThrow();
});
