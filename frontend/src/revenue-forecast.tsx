import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Card, Chart, Field, Metrics, Notice, Select, Table } from "./components";
import ClinicSelect from "./clinic-select";
import type { Row } from "./types";

export default function RevenueForecast({defaultStart,defaultEnd,defaultClinic}:{defaultStart:string;defaultEnd:string;defaultClinic:string}) {
  const [start,setStart]=useState(defaultStart),[end,setEnd]=useState(defaultEnd),[clinic,setClinic]=useState(defaultClinic);
  const [horizon,setHorizon]=useState("3"),[result,setResult]=useState<Row|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const previousDefaults=useRef({defaultStart,defaultEnd,defaultClinic});
  useEffect(()=>{
    const previous=previousDefaults.current;
    setStart(value=>value===previous.defaultStart?defaultStart:value);
    setEnd(value=>value===previous.defaultEnd?defaultEnd:value);
    setClinic(value=>value===previous.defaultClinic?defaultClinic:value);
    previousDefaults.current={defaultStart,defaultEnd,defaultClinic};
  },[defaultStart,defaultEnd,defaultClinic]);
  const selection=JSON.stringify({start,end,clinic,horizon}),latest=useRef(selection);latest.current=selection;
  const [resultSelection,setResultSelection]=useState("");
  async function run() {
    setBusy(true);setError("");const requested=selection;
    try {
      const params=new URLSearchParams({start,end,horizon});if(clinic)params.set('clinic_location',clinic);
      const value=await api(`/simulations/forecast?${params}`);
      if(latest.current===requested){setResult(value);setResultSelection(requested);}
    } catch(e) {if(latest.current===requested){setResult(null);setError((e as Error).message);}}
    finally{setBusy(false);}
  }
  return <Card title="History-based revenue forecast">
    <p className="fine">Estimate future collections from at least 24 consecutive complete months. Your saved scenario remains separate.</p>
    <div className="form-grid">
      <ClinicSelect value={clinic} onChange={setClinic}/>
      <Field label="Forecast history from" type="date" value={start} onChange={setStart}/>
      <Field label="Forecast history through" type="date" value={end} onChange={setEnd}/>
      <Select label="Forecast horizon" value={horizon} onChange={setHorizon} options={Array.from({length:12},(_,i)=>[String(i+1),`${i+1} month${i?'s':''}`] as [string,string])}/>
    </div>
    <button type="button" disabled={busy||!start||!end} onClick={()=>void run()}>{busy?'Calculating forecast…':'Run forecast'}</button>
    {error&&<Notice error>{error}</Notice>}
    {result&&resultSelection!==selection&&<p role="status">Selection changed. Run forecast to update the results.</p>}
    {result&&resultSelection===selection&&<>
      <p className="fine">{result.clinic_location||'All clinics'} · history {result.start} – {result.end}</p>
      <Metrics currency={result.currency} items={[["Next month revenue",result.periods[0].revenue],["Validation error (MAE)",result.validation_mae]]}/>
      <Chart rows={result.periods} keys={["revenue","lower_80","upper_80"]} x="period" currency={result.currency}/>
      <Table rows={result.periods} columns={["period","revenue","lower_80","upper_80"]}/>
      <details><summary>Forecast validation</summary><p>{result.basis}</p><Table rows={[{method:result.method,history_months:result.history_months,benchmark_mae:result.benchmark_mae,benchmark_fallback:result.benchmark_fallback}]}/></details>
    </>}
  </Card>;
}
