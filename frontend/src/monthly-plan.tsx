import { useState } from "react";
import { Card, Field, Select } from "./components";
import type { Plan } from "./types";

// BigInt fixed-point transformations preserve cents, including fill-forward edits.
export function adjustDecimal(value: string, percent: string): string {
  function scaled(s: string, digits: number) {
    if (!/^-?\d+(\.\d+)?$/.test(s)) throw new Error("Enter a valid amount and percentage.");
    const negative=s.startsWith("-"); const [whole,fraction=""]=s.replace("-","").split(".");
    const padded=fraction.padEnd(digits+1,"0");
    let n=BigInt(whole)*10n**BigInt(digits)+BigInt(padded.slice(0,digits));
    if (Number(padded[digits])>=5) n++;
    return negative ? -n : n;
  }
  const factor=10000n+scaled(percent,2);
  if (factor<0) throw new Error("A reduction cannot exceed 100%.");
  const cents=(scaled(value,2)*factor+5000n)/10000n;
  return `${cents/100n}.${(cents%100n).toString().padStart(2,"0")}`;
}
export function monthLabel(start: string, index: number) {
  const [year,month]=start.split("-").map(Number);
  return new Date(Date.UTC(year,month-1+index,1)).toLocaleDateString("en-US",{month:"short",year:"numeric",timeZone:"UTC"});
}
export default function MonthlyPlan({plan,onChange}:{plan:Plan;onChange:(plan:Plan)=>void}) {
  const [target,setTarget]=useState("revenue"),[from,setFrom]=useState("1"),[percent,setPercent]=useState("0"),[error,setError]=useState("");
  const months=Array.from({length:Math.min(120,Math.max(1,plan.months))},(_,i)=>i+1);
  const rows=[...(plan.revenue_mode==='drivers' ? [] : [{key:"revenue",label:"Existing clinic revenue",start:1,end:plan.months,base:plan.existing_monthly_revenue,values:plan.existing_revenue_by_month||{}}]),
    ...plan.clinic_costs.map((c,i)=>({key:`cost-${i}`,label:c.label,start:c.start_month,end:c.end_month,base:c.monthly_amount,values:c.monthly_amounts||{}})),
    ...plan.staff.map((s,i)=>({key:`staff-${i}`,label:`${s.role_type} · salary / person`,start:s.start_month,end:s.end_month,base:annualToMonthly(s.annual_salary),values:s.monthly_salary||{}}))];
  function replace(key:string,values:Record<number,string>) {
    const next=structuredClone(plan);
    if(key==='revenue') next.existing_revenue_by_month=values;
    else if(key.startsWith('cost-')) next.clinic_costs[Number(key.slice(5))].monthly_amounts=values;
    else next.staff[Number(key.slice(6))].monthly_salary=values;
    onChange(next);
  }
  function bulk(fill:boolean) {
    try {
      const row=rows.find(r=>r.key===target); if(!row) return;
      const month=Number(from); const values={...row.values};
      for(const m of months.filter(m=>m>=month&&m>=row.start&&m<=row.end)) values[m]=fill ? row.values[month]??row.base : adjustDecimal(row.values[m]??row.base,percent);
      replace(target,values);setError("");
    } catch(e) {setError((e as Error).message);}
  }
  return <Card title="Monthly revenue & expenses">
    <div className="monthly-tools">
      <Select label="Change row" value={target} onChange={setTarget} options={rows.map(r=>[r.key,r.label])}/>
      <Select label="From month" value={from} onChange={setFrom} options={months.map(m=>[String(m),monthLabel(plan.start_date,m-1)])}/>
      <Field label="Change %" type="number" min={-100} value={percent} onChange={setPercent}/>
      <button type="button" onClick={()=>bulk(false)}>Apply % forward</button>
      <button type="button" onClick={()=>bulk(true)}>Fill forward</button>
    </div>
    {error&&<p role="alert">{error}</p>}
    <div className="table-scroll monthly-grid"><table><thead><tr><th>Category</th>{months.map(m=><th key={m}>{monthLabel(plan.start_date,m-1)}</th>)}</tr></thead>
      <tbody>{rows.map(r=><tr key={r.key}><th scope="row">{r.label}</th>{months.map(m=><td key={m}>{m<r.start||m>r.end ? <span className="muted">—</span> : <input aria-label={`Month ${m} ${r.key==='revenue'?'revenue':r.label}`} type="number" min="0" step="0.01" value={r.values[m]??r.base} onChange={e=>replace(r.key,{...r.values,[m]:e.target.value})}/>}</td>)}</tr>)}</tbody></table></div>
    <button type="button" onClick={()=>onChange({...plan,existing_revenue_by_month:{},clinic_costs:plan.clinic_costs.map(c=>({...c,monthly_amounts:{}})),staff:plan.staff.map(s=>({...s,monthly_salary:{}}))})}>Reset monthly overrides</button>
  </Card>;
}
function annualToMonthly(value:string) {
  if(!/^\d+(\.\d+)?$/.test(value)) return "0";
  const [w,f=""]=value.split('.');const cents=BigInt(w)*100n+BigInt(f.padEnd(2,'0').slice(0,2));const monthly=(cents+6n)/12n;
  return `${monthly/100n}.${(monthly%100n).toString().padStart(2,'0')}`;
}
