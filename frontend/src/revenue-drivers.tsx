import { Card, Field, Select } from "./components";
import type { Plan } from "./types";
import { monthLabel } from "./monthly-plan";
export default function RevenueDrivers({plan,onChange}:{plan:Plan;onChange:(p:Plan)=>void}) {
  const drivers=plan.revenue_drivers||[];
  function update(i:number,patch:object) {onChange({...plan,revenue_drivers:drivers.map((d,n)=>n===i?{...d,...patch}:d)});}
  return <Card title="Revenue model">
    <Select label="Project revenue using" value={plan.revenue_mode||'amount'} options={[["amount","Monthly amounts"],["drivers","Insurance / code volume × collected payment"]]} onChange={v=>onChange({...plan,revenue_mode:v as Plan['revenue_mode'],existing_revenue_by_month:{}})}/>
    {plan.revenue_mode==='drivers'&&<>
      <p className="fine">Replaces existing clinic revenue. Enter billable units, not statement row counts; payment amounts are net collections per unit.</p>
      {drivers.map((d,i)=><section className="editor-row" key={i}><div className="form-grid">
        <Field label="Insurance" value={d.insurance} onChange={v=>update(i,{insurance:v})} required/>
        <Field label="Billing code" value={d.billing_code} onChange={v=>update(i,{billing_code:v})} required/>
        <Field label="Monthly units" type="number" min={0} value={d.monthly_units} onChange={v=>update(i,{monthly_units:v})}/>
        <Field label="Collected per unit" type="number" min={0} value={d.collected_per_unit} onChange={v=>update(i,{collected_per_unit:v})}/>
        <button type="button" onClick={()=>onChange({...plan,revenue_drivers:drivers.filter((_,n)=>n!==i)})}>Remove driver</button>
      </div><details><summary>Monthly volume and payment</summary><div className="table-scroll"><table><thead><tr><th>Month</th><th>Units</th><th>Payment / unit</th></tr></thead><tbody>{Array.from({length:Math.min(120,plan.months)},(_,n)=>n+1).map(m=><tr key={m}><th>{monthLabel(plan.start_date,m-1)}</th><td><input aria-label={`${d.insurance} ${d.billing_code} month ${m} units`} type="number" min="0" value={d.units_by_month[m]??d.monthly_units} onChange={e=>update(i,{units_by_month:{...d.units_by_month,[m]:e.target.value}})}/></td><td><input aria-label={`${d.insurance} ${d.billing_code} month ${m} payment`} type="number" min="0" step="0.01" value={d.payment_by_month[m]??d.collected_per_unit} onChange={e=>update(i,{payment_by_month:{...d.payment_by_month,[m]:e.target.value}})}/></td></tr>)}</tbody></table></div></details></section>)}
      <button type="button" disabled={drivers.length>=50} onClick={()=>onChange({...plan,revenue_drivers:[...drivers,{insurance:'New insurance',billing_code:'Code',monthly_units:'0',collected_per_unit:'0',units_by_month:{},payment_by_month:{}}]})}>Add insurance / code</button>
    </>}
    <Field label="Additional variable costs % of existing revenue" type="number" min={0} max={100} value={plan.variable_cost_pct||'0'} onChange={v=>onChange({...plan,variable_cost_pct:v})}/>
  </Card>;
}
