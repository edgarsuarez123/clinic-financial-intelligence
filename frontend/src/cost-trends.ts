import type { Row } from './types';
// Sum API decimals as scaled integers; Number is used only by the chart renderer.
export function sumDecimals(values: string[]): string {
  const scale = Math.max(0, ...values.map(v => (v.split('.')[1] || '').length));
  const total = values.reduce((sum,v) => {const negative=v.startsWith('-');const [whole,fraction='']=v.replace(/^-/,'').split('.');return sum+(negative?-1n:1n)*BigInt(whole+fraction.padEnd(scale,'0'));},0n);
  const digits=(total<0n?-total:total).toString().padStart(scale+1,'0');
  return (total<0n?'-':'')+(scale?digits.slice(0,-scale)+'.'+digits.slice(-scale):digits);
}
export function costTrends(periods: Row[]): {keys:string[];rows:Row[]} {
  const components = [['salary','Staff: salary'],['benefits','Staff: benefits'],['payroll_taxes','Staff: payroll taxes'],['malpractice','Staff: malpractice'],['other_fixed_cost','Staff: other fixed costs'],['variable_cost','Staff: variable costs'],['onboarding_cost','Staff: onboarding']];
  const clinic = Array.from(new Set<string>(periods.flatMap(p=>p.clinic_costs.map((c:Row)=>'Clinic: '+c.label))));
  return {keys:[...components.map(([,label])=>label),...clinic],rows:periods.map(p=>({start:p.start,
    ...Object.fromEntries(components.map(([key,label])=>[label,sumDecimals(p.staff.map((s:Row)=>String(s[key])))])),
    ...Object.fromEntries(clinic.map(label=>[label,sumDecimals(p.clinic_costs.filter((c:Row)=>'Clinic: '+c.label===label).map((c:Row)=>String(c.total)))]))
  }))};
}
