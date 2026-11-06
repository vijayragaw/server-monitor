import {apiBaseUrl} from './monitorUrls';
import RemoteServers from './RemoteServers';
import StatusIcon from './StatusIcon';
import React, {useState} from 'react';
const columns=[['Site',['Website']],['API',['Backend API']],['Errors',['Laravel errors today']],['Queue',['Queue pending','Failed jobs · 24 hours']],['DB',['Database','Database response time']],['Email',['Mail']],['Storage',['Storage writable','Session folder writable','Compiled views writable','Bootstrap cache writable']],['SSL',['Website SSL','API SSL']]];
const environments={testing:'Testing',uat:'UAT',production:'Production',unassigned:'Unassigned'};
const icons={ok:'✓',warning:'⚠',critical:'✕',offline:'⊘',unknown:'?',disabled:'Ⅱ',missing:'—'};
const names={ok:'Success',warning:'Warning',critical:'Danger',offline:'Offline / unconfirmed',unknown:'Unknown',disabled:'Disabled',missing:'Not configured'};
function Indicator({status,description,onClick}){return <button type="button" className={'overview-status status-'+status} title={description} aria-label={description} onClick={onClick} disabled={!onClick}><span aria-hidden="true"><StatusIcon status={status}/></span><span className="sr-only">{names[status]}</span></button>}
export default function StatusOverview({result,settings,brand,environment:selectedEnvironment,stale,onDetails,onSelect,all=false}){
 const [groupBy,setGroupBy]=useState('brand');
 const configured=result?.configured_apps||settings?.apps||[];
 const brands=all?[...new Set(configured.map(a=>a.brand?.trim()||a.name))]:brand?[brand]:[];
 const rows=brands.flatMap(brand=>{const apps=configured.filter(a=>(a.brand?.trim()||a.name)===brand);return [...['testing','uat','production'].flatMap(environment=>{const group=apps.filter(a=>a.environment===environment);return group.length?group.map(app=>({brand,environment,app})):[{brand,environment}]}),...apps.filter(a=>!a.environment||a.environment==='unassigned').map(app=>({brand,environment:'unassigned',app}))]});
 const environmentOrder = ['production', 'uat', 'testing', 'unassigned'];
 const groups = groupBy === 'brand'
  ? brands.map(brand => ({
    label: brand,
    rows: environmentOrder.flatMap(environment => rows.filter(row => row.brand === brand && row.environment === environment)),
  }))
  : environmentOrder.map(environment => ({
    label: environments[environment],
    rows: rows.filter(row => row.environment === environment),
  }));
 function cell(app,labels,title){
  if(!app)return <Indicator status="missing" description={title+': environment not configured'}/>;
  const live=result?.apps.find(a=>a.id===app.id);
  const all=labels.map(label=>({label,value:live?.checks[label]})).filter(x=>x.value);
  const applicable=labels.filter(label=>app.sshAlias&&!label.startsWith('Website')?['Database','Database response time','Mail','Laravel errors today'].includes(label):label.startsWith('Website')?app.siteUrl:label==='Mail'?app.mailHealthUrl:['Backend API','API SSL'].includes(label)?app.healthUrl:label.startsWith('Database')?app.healthUrl&&app.backend==='laravel':app.diagnosticsUrl);
  const disabled=app.enabled===false||(applicable.length>0&&applicable.every(label=>app.disabledChecks?.includes(label)));
  const worst=['critical','warning','offline','unknown','ok'].flatMap(status=>all.filter(x=>x.value.status===status))[0];
  const status=disabled?'disabled':stale?'unknown':worst?.value.status||(applicable.length?'unknown':'missing');
  const description=`${app.brand||app.name} · ${environments[app.environment]||'Unassigned'} · ${title}: ${names[status]}${worst?' · '+worst.value.summary:''}`;
  return <Indicator status={status} description={description} onClick={worst&&!disabled?()=>onDetails({label:worst.label,value:stale?{status:'unknown',summary:'Previous reading · refresh to confirm'}:worst.value,scope:`${app.brand||app.name} · ${environments[app.environment]||'Unassigned'} · ${app.name}`}):undefined}/>;
 }
 return <section className="status-overview" aria-labelledby="status-overview-title"><div className="overview-title"><div><h2 id="status-overview-title">Brand health overview</h2><p className="muted">{all?'All brands and environments':brand||'Choose a brand'} · select a status for details</p></div>{stale&&<span className="pill maintenance">Stale readings</span>}</div><div className="server-overview"><strong>Server <small>Local watcher only</small></strong>{[['CPU','Watcher computer · CPU'],['RAM','Watcher computer · RAM'],['Disk','Watcher computer · Disk'],['Free disk','Watcher computer · Free disk space'],['Uptime','Watcher computer · Uptime'],['Internet','Watcher internet']].map(([label,key])=>{const value=result?.watcher[key];const status=stale?'unknown':value?.status||(settings?.localMetrics===false&&label!=='Internet'?'disabled':'unknown');return <div key={key}><Indicator status={status} description={`Server ${label}: ${names[status]}${value?' · '+value.summary:''}`} onClick={value?()=>onDetails({label:'Server '+label,value,scope:'Local watcher server'}):undefined}/><span>{label}</span></div>})}</div><RemoteServers result={result} settings={settings} stale={stale} onDetails={onDetails}/>{all?<div>
  <label className="overview-group-select">
    Group by
    <select value={groupBy} onChange={event=>setGroupBy(event.target.value)}>
      <option value="brand">Brand</option>
      <option value="environment">Environment</option>
    </select>
  </label>
  <div className="overview-scroll">
    <table className="simple-overview home-all-checks">
      <caption className="sr-only">All brands and environments with individual check statuses</caption>
      <thead><tr>
        <th>Brand / project</th><th>Environment</th><th>Website URL</th><th>API URL</th>
        {columns.map(([label])=><th key={label}>{label}</th>)}
      </tr></thead>
      {groups.filter(group=>group.rows.length).map(group=><tbody key={group.label}>
        <tr className="overview-group-heading"><th scope="rowgroup" colSpan={columns.length+4}>{group.label}</th></tr>
        {group.rows.map(({brand,environment,app})=><tr key={app?.id||brand+environment}>
          <th scope="row"><button className="overview-brand" onClick={()=>onSelect(app?.id,brand,environment)}>
            {brand}{app&&app.name!==brand&&<small>{app.name}</small>}
          </button></th>
          <td><span className={'environment environment-'+environment}>{environments[environment]}</span></td>
          <td className="overview-api-url">{app?.siteUrl || '—'}</td>
          <td className="overview-api-url">{apiBaseUrl(app?.healthUrl) || '—'}</td>
          {columns.map(([label,labels])=><td key={label}>{cell(app,labels,label)}</td>)}
        </tr>)}
      </tbody>)}
    </table>
  </div>
 </div>:<div className="brand-overview-groups">{[selectedEnvironment].map(environment=><section className="brand-group" key={brand+environment}><div className="environment-heading"><strong>{environments[environment]}</strong><small>{rows.filter(row=>row.environment===environment&&row.app).length} configured monitors</small></div><div className="overview-scroll"><table className="simple-overview"><caption className="sr-only">{brand} · {environments[environment]} status</caption><thead><tr><th>Application / project</th>{columns.map(([label])=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.filter(row=>row.environment===environment).map(({app})=><tr key={app?.id||environment}><th scope="row"><button className="overview-brand" disabled={!app||app.enabled===false} onClick={()=>onSelect(app.id)}>{app?.name||'Not configured'}</button></th>{columns.map(([label,labels])=><td key={label}>{cell(app,labels,label)}</td>)}</tr>)}</tbody></table></div></section>)}</div>}{!rows.length&&<p className="muted">Add a brand and environment in Settings to begin monitoring.</p>}<div className="overview-legend">{['ok','warning','critical','unknown','disabled','missing'].map(status=><span key={status}><span className={'legend-icon status-'+status} aria-hidden="true"><StatusIcon status={status}/></span>{names[status]}</span>)}</div><small>Each grouped status shows its most severe check. Missing environments remain unconfigured. Local server metrics describe this watcher; Ubuntu server metrics come from configured agents.</small></section>
}
