import { useEffect, useState } from "react";
import { api } from "./api";
import { Select, Notice } from "./components";

export default function ClinicSelect({value,onChange}: {value:string;onChange:(value:string)=>void}) {
  const [locations,setLocations]=useState<string[]>([]);
  const [error,setError]=useState("");
  useEffect(() => {
    let active=true;
    api("/analytics/metadata").then((m) => { if(active) setLocations(m.clinic_locations || []); })
      .catch((e) => { if(active) setError(e.message); });
    return () => { active=false; };
  },[]);
  return <>{error && <Notice error>{error}</Notice>}<Select label="Clinic location" value={value} onChange={onChange}
    options={[["","All clinics"],...locations.map((name):[string,string] => [name,name])]} /></>;
}
