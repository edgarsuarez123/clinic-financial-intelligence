import { useEffect, useRef, useState } from 'react';
import { Card, Field, Notice, Select, Table } from './components';
import { sumDecimals } from './cost-trends';
import type { ColumnProfile } from './financial-csv';
import { financialPDF, type PDFLayout } from './financial-pdf';
export default function PDFImport({file, profile, onPrepared}: {file: File; profile: ColumnProfile; onPrepared: (body: Blob | null) => void}) {
  const [layout, setLayout] = useState<PDFLayout>(() => ({firstPage:1,lastPage:1,top:20,bottom:90,columns:Object.fromEntries(Object.keys(profile.columns).map(key => [key,{left:0,right:10,constant:'',useConstant:['type','category','provider','medical_insurance'].includes(key)}]))}));
  const [error,setError] = useState(''), [busy,setBusy] = useState(false), [clean,setClean] = useState<{csv:string;rows:number;records:Record<string,string>[]}|null>(null);
  const generation = useRef(0);
  const [expected,setExpected] = useState('');
  const total = clean ? sumDecimals(clean.records.map(r=>r.amount)) : '0';
  const reconciled = /^-?\d+(?:\.\d{1,2})?$/.test(expected) && /^-?0(?:\.0+)?$/.test(sumDecimals([total,expected.startsWith('-')?expected.slice(1):'-'+expected]));
  useEffect(() => { generation.current++; setClean(null); onPrepared(null); }, [layout, file, profile]);
  return <Card title="Insurance payment statement layout">
    <p>Select the detail rows containing actual insurer payments, excluding headings, subtotals and totals. Positions are percentages measured from the page’s top-left corner. Use the same layout only on pages with the same table structure.</p>
    <p className="fine">Map paid amounts, not billed charges, allowed amounts or patient responsibility. No patient names, claim IDs or account numbers may be mapped. Original PDF bytes stay in this browser.</p>
    <div className="form-grid">{(['firstPage','lastPage','top','bottom'] as const).map(key => <Field key={key} label={{firstPage:'First page',lastPage:'Last page',top:'Table top (%)',bottom:'Table bottom (%)'}[key]} type="number" value={layout[key]} onChange={v => setLayout({...layout,[key]:Number(v)})} />)}</div>
    {Object.keys(profile.columns).map(key => <div className="editor-row" key={key}><h3>{key.replaceAll('_',' ')}</h3><div className="form-grid">
      <Select label={`${key} source`} value={layout.columns[key].useConstant?'constant':'column'} options={key==='amount'||key==='billing_code' ? [['column','PDF column']] : [['column','PDF column'],['constant','Same value for selected rows']]} onChange={v => setLayout({...layout,columns:{...layout.columns,[key]:{...layout.columns[key],useConstant:v==='constant'}}})} />
      {layout.columns[key].useConstant ? (key==='date' ? <Field label="Statement payment date" value={layout.columns[key].constant} onChange={v=>setLayout({...layout,columns:{...layout.columns,[key]:{...layout.columns[key],constant:v}}})} /> : <Select label={`${key} value`} value={layout.columns[key].constant} options={[["",key==='provider'?'No provider':'Choose an approved value'],...(profile.allowed_values[key]||[]).map(v=>[v,v] as [string,string])]} onChange={v=>setLayout({...layout,columns:{...layout.columns,[key]:{...layout.columns[key],constant:v}}})} />) : (['left','right'] as const).map(edge=><Field key={edge} label={`${key} ${edge} (%)`} type="number" value={layout.columns[key][edge]} onChange={v=>setLayout({...layout,columns:{...layout.columns,[key]:{...layout.columns[key],[edge]:Number(v)}}})} />)}
    </div></div>)}
    <button type="button" disabled={busy} onClick={async()=>{const request = generation.current;setBusy(true);setError('');setClean(null);onPrepared(null);try { const result=await financialPDF(file,profile,layout);if(request===generation.current)setClean(result); } catch {if(request===generation.current)setError('The selected layout could not produce valid financial rows. Check page range, row area, column boundaries, dates and approved codes. Nothing was uploaded.');} finally {setBusy(false);} }}>{busy?'Reading locally…':'Extract financial rows locally'}</button>
    {error&&<Notice error>{error}</Notice>}
    {clean&&<><Notice>{clean.rows} financial rows extracted. Review the financial-only CSV before confirming. Check that its sum matches the insurer’s payment total and that no payment rows were omitted.</Notice>
      <p><strong>Extracted paid total: {total}</strong> · Showing up to 100 rows below.</p>
      <Table rows={clean.records.slice(0,100)} />
      <details><summary>All extracted rows (CSV)</summary><textarea aria-label="Extracted financial CSV" readOnly value={clean.csv} rows={10} style={{width:'100%'}} /></details>
      <Field label="Expected paid total for selected rows" value={expected} onChange={v=>{setExpected(v);onPrepared(null);}} />
      {!reconciled && <p>Enter the payment total from your statement to reconcile the selected rows before confirming.</p>}
      <button type="button" disabled={!reconciled} onClick={()=>onPrepared(new Blob([clean.csv],{type:'text/csv'}))}>Confirm extracted rows for import</button></>}
  </Card>;
}
