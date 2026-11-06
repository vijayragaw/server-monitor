import React,{useState} from 'react';
import CheckDescription from './CheckDescription';
import Speedometer from './Speedometer';
import Actions from './Actions';
const categories=[['Database',['Database','Database response time'],'🗄️'],['SSL certificates',['Website SSL','API SSL'],'🔒'],['Laravel storage',['Storage writable','Session folder writable','Compiled views writable','Bootstrap cache writable'],'📁'],['Queue processing',['Queue pending','Failed jobs · 24 hours'],'📬']];
export default function GroupedChecks({item,error,issuesOnly,showCharts,busy,rechecking,onRecheck,onDetails,checkedAt}){
 const [expanded,setExpanded]=useState({});
 const groups=[];const seen=new Set();
 for(const [label,value] of Object.entries(item.checks)){
  if(seen.has(label))continue;
  const category=categories.find(([,labels])=>labels.includes(label));
  const labels=category?category[1].filter(name=>item.checks[name]):[label];
  labels.forEach(name=>seen.add(name));
  const entries=labels.map(name=>[name,item.checks[name]]).filter(([,check])=>!issuesOnly||['critical','warning'].includes(check.status));
  if(entries.length)groups.push({name:category?.[0]||label,emoji:category?.[2]||(label==='Mail'?'✉️':label==='Website'?'🌐':label==='Backend API'?'🔌':label.includes('cache')?'⚡':'📋'),entries});
 }
 const symbols={ok:'✓',warning:'⚠',critical:'✕',unknown:'?',offline:'⊘'};
 function content(label,value){return <>
 {showCharts&&!error&&value.duration_ms!==undefined&&<Speedometer value={value.duration_ms} status={value.status}/>}
 <small className="subcheck-time">{value.expires_at?`Expires ${new Date(value.expires_at).toLocaleDateString()}`:`Checked ${new Date(value.checked_at||checkedAt).toLocaleTimeString()}`}</small>
 <div className="card-primary-actions"><button className="recheck-button" disabled={busy||rechecking[item.id+label]} onClick={()=>onRecheck(item.id,label)}>{rechecking[item.id+label]?'Checking…':'↻ Recheck'}</button><button className="details-button" onClick={()=>onDetails({label,value,scope:item.name,url:label.includes('Website')?item.site_url:item.health_url})}>Details ↗</button></div>
 <Actions app={item} checkLabel={label}/></>}
 function pill(value){return <span className={'pill '+(error||['unknown','offline'].includes(value.status)?'maintenance':value.status)}>{error?'Stale':symbols[value.status]+' '+value.summary}</span>}
 return <div className="live-checks app-check-grid">{groups.map(group=><div className="organized-card grouped-card" key={group.name}>
 <div className="group-heading"><span className="check-emoji" aria-hidden="true">{group.emoji}</span><strong>{group.name}</strong>{group.entries.length>1&&<small>{group.entries.length} checks</small>}</div>
 <div className="group-body">{group.entries.map(([label,value])=>group.entries.length>1?<div className="compact-subcheck" key={label}><div className="subcheck-summary"><span className="subcheck-title">{label}</span>{pill(value)}<label className="switch-label subcheck-switch"><input type="checkbox" role="switch" aria-label={'Show '+label+' actions'} checked={!!expanded[label]} onChange={event=>setExpanded(previous=>({...previous,[label]:event.target.checked}))}/><span className="switch-track"/></label></div>{expanded[label]&&<div className="expanded-subcheck">{content(label,value)}</div>}</div>:<div className="group-check" key={label}>
 {pill(value)}<CheckDescription label={label} value={value} stale={error}/>{content(label,value)}
 </div>)}</div>
 {group.entries.length>1&&<small className="group-hint">Switch on a check to show actions and details</small>}
 </div>)}</div>
}
