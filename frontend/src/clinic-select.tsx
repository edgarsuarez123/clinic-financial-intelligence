import { useEffect, useState } from "react";
import { api } from "./api";
import { Select, Notice } from "./components";

export default function ClinicSelect({value,onChange}: {value:string;onChange:(value:string)=>void}) {
  const [locations,setLocations]=useState<string[]>([]);
  const [error,setError]=useState("");
  const [revision,setRevision]=useState(0);
  useEffect(()=>{const refresh=()=>setRevision(v=>v+1);window.addEventListener('clinic-data-updated',refresh);return()=>window.removeEventListener('clinic-data-updated',refresh);},[]);
  useEffect(() => {
    let active=true;
    setError("");
    api("/analytics/metadata").then((m) => { if(active) setLocations(m.clinic_locations || []); })
      .catch((e) => { if(active) setError(e.message); });
    return () => { active=false; };
  },[revision]);
  return <>{error && <Notice error>{error}</Notice>}<Select label="Clinic location" value={value} onChange={onChange}
    options={[["","All clinics"],...Array.from(new Set([...locations,...(value?[value]:[])])).map((name):[string,string] => [name,name])]} /></>;
}
