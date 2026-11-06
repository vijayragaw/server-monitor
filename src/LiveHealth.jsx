import HomeDashboard from './HomeDashboard';
import EnvironmentWorkspace from './EnvironmentWorkspace';
import Settings from './Settings';
import ApplicationTable from './ApplicationTable';
import GroupedChecks from './GroupedChecks';
import CheckDescription from './CheckDescription';
import Speedometer from './Speedometer';
import {toast,notify} from './notifications';
import Actions from './Actions';
import {Meter,Trend} from './Visuals';
import React, {useEffect, useRef, useState} from 'react';

function icon(name){
 const n=name.toLowerCase();
 return n.includes('ssl')?'🔒':n.includes('database')?'🗄️':n.includes('mail')?'✉️':n.includes('cpu')?'⚙️':n.includes('ram')?'🧠':n.includes('disk')?'💾':n.includes('uptime')?'⏱️':n.includes('website')?'🌐':n.includes('api')?'🔌':n.includes('error')||n.includes('failed')?'📋':n.includes('queue')?'📬':n.includes('cache')?'⚡':'📁';
}
function explain(label,value){
 const n=label.toLowerCase();
 if(value.status==='unknown')return value.summary.includes('HTTP URL')?'This address uses HTTP, so there is no TLS certificate to inspect. Configure an HTTPS URL to check certificate expiry.':'The check did not provide a supported result. Verify its XML endpoint and the application configuration. Unknown does not mean healthy or failed.';
 if(n.includes('errors today'))return 'This is the number of ERROR, CRITICAL, ALERT, and EMERGENCY entries dated today in Laravel logs, not a count of currently active incidents. Open storage/logs in your Laravel project and inspect today’s entries. Earlier failures remain in this count after they are fixed.';
 if(n.includes('mail'))return value.status==='ok'?'The configured SMTP connection and login succeeded. No email was sent; delivery is not tested.':'The encrypted SMTP connection or authentication failed. Check Laravel MAIL_HOST, MAIL_PORT, encryption, username and password, provider app-password requirements, and network access. The current probe does not distinguish the exact failure stage.';
 if(n.includes('disk'))return 'This is disk usage on the watcher server. Warning starts at 80%, critical at 90%. Review Windows Storage settings and identify large files before deleting anything.';
 if(n.includes('cpu'))return 'This is a short CPU usage sample on the watcher server. Warning starts at 75%, critical at 90%. Check Task Manager for busy processes and retry to see whether the load persists.';
 if(n.includes('ram'))return 'This is memory usage on the watcher server. Warning starts at 80%, critical at 92%. Check Task Manager for high-memory processes.';
 if(n.includes('database response time'))return 'Measures database connection setup plus SELECT 1 inside Laravel, excluding watcher HTTP latency. Warning starts at 800 ms and critical at 2000 ms. Review network latency, connection setup and server load; this is not a slow-query analysis.';
 if(n.includes('database'))return value.status==='ok'?'Laravel successfully ran SELECT 1 through its configured database connection. This tests connectivity, not all tables or queries.':'Laravel could not complete its database connection test. Check the database service, network reachability, credentials and database permissions in Laravel’s environment configuration.';
 if(n.includes('ssl'))return 'The watcher verifies certificate trust and hostname, then checks expiry. Below 15 days is warning; below 5 days is critical. Check renewal and the certificate chain if validation fails.';
 if(n.includes('api')||n.includes('website'))return 'The watcher requested the configured URL. Review its HTTP status and measured response time above. A warning can mean a slow response even when HTTP 200 is returned. Open the endpoint and inspect application logs for failures. This does not test business workflows.';
 if(n.includes('queue')||n.includes('failed jobs'))return 'The check reads the configured database-backed queue. Pending jobs warn at 25 and are critical at 100; any failed job in 24 hours is a warning. Inspect queue workers and Laravel failed-job records; this monitor does not retry jobs.';
 if(n.includes('cache')&&n.includes('laravel'))return 'The check writes, reads and removes a uniquely named temporary cache key. A failure means the configured cache could not complete that round trip.';
 if(n.includes('writable'))return 'The check confirms that the required directory exists and PHP can write to it. If failing, create the missing directory and grant the PHP process appropriate access.';
 return 'This is a live observation from the configured monitoring source. Use Run checks again to obtain a new result.';
}
export default function LiveHealth({page='monitoring',onNavigate}){
 const [brandChoice,setBrandChoice]=useState('');
 const [environmentChoice,setEnvironmentChoice]=useState('production');
 const [configuredSettings,setConfiguredSettings]=useState(null);
 const savedSettings=useRef(null);
 const [notifications,setNotifications]=useState(true);
 const [tab,setTab]=useState(null);
 const [search,setSearch]=useState('');
 const [settingsOpen,setSettingsOpen]=useState(false);
 const [tableView,setTableView]=useState(false);
 async function changeView(value){
  if(!savedSettings.current)return;
  const candidate={...savedSettings.current,dashboard:{...savedSettings.current.dashboard,tableView:value}};
  try{const response=await fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json','X-Monitor-Action':'manual'},body:JSON.stringify(candidate)});if(!response.ok)throw Error();applySettings(await response.json());setTab(null)}catch{notify('Settings not saved','Could not save view preference. Please try again.','error')}
 }
 const [rechecking,setRechecking]=useState({});
 const [preview,setPreview]=useState(null);
 const [history,setHistory]=useState([]),[issuesOnly,setIssuesOnly]=useState(false),[showCharts,setShowCharts]=useState(true);

 const [result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(false);
 const [seconds,setSeconds]=useState(0),[preferenceError,setPreferenceError]=useState('');
 async function recheckCard(appId,label){
  const key=appId+label;if(rechecking[key])return;
  setRechecking(previous=>({...previous,[key]:true}));
  try{
   const response=await fetch('/api/recheck',{method:'POST',headers:{'Content-Type':'application/json','X-Monitor-Action':'manual'},body:JSON.stringify({app_id:appId,check:label}),signal:AbortSignal.timeout(20000)});
   if(!response.ok)throw new Error();
   const data=await response.json();
   setResult(previous=>{
    if(!previous)return previous;
    const apps=previous.apps.map(item=>{
     if(item.id!==appId)return item;
     const checks={...item.checks,[label]:{...data.result,checked_at:data.checked_at}};
     const meaningful=Object.entries(checks).filter(([name,value])=>!name.includes('SSL')||value.status!=='unknown');
     const status=['critical','warning','offline','unknown'].find(status=>meaningful.some(([,value])=>value.status===status))||'ok';
     return {...item,checks,status};
    });
    const watcher=appId==='__watcher__'?{...previous.watcher,[label]:{...data.result,checked_at:data.checked_at}}:previous.watcher;
    const counts=Object.fromEntries(['ok','warning','critical','unknown','offline'].map(status=>[status,apps.flatMap(a=>Object.values(a.checks)).filter(c=>c.status===status).length]));
    return {...previous,apps,watcher,counts};
   });
   toast(`${label}: ${data.result.summary}`,data.result.status==='ok'?'success':data.result.status==='critical'?'error':'info');
  }catch{notify('Recheck failed','The selected check could not be refreshed. Its previous result is retained.','error')}
  finally{setRechecking(previous=>({...previous,[key]:false}))}
 }
 const running=useRef(false),checkSequence=useRef(0);
 async function check(force=false){
  if(running.current&&force!==true)return;
  const sequence=++checkSequence.current;
  running.current=true;setBusy(true);
  try{
   const response=await fetch('/api/live',{cache:'no-store',signal:AbortSignal.timeout(20000)});
   if(!response.ok)throw new Error();
   const data=await response.json();
   if(!data.apps)throw new Error();
   if(sequence!==checkSequence.current)return;
   setResult(data);setHistory(previous=>[...previous,{at:Date.now(),apps:data.apps,watcher:data.watcher}].slice(-30));setError(false);
  }catch{if(sequence===checkSequence.current)setError(true)}
  finally{if(sequence===checkSequence.current){running.current=false;setBusy(false)}}
 }
 function applySettings(data){savedSettings.current=data;setConfiguredSettings(data);setPreferenceError('');setSeconds(data.dashboard.refreshSeconds);setTableView(data.dashboard.tableView);setIssuesOnly(data.dashboard.issuesOnly);setShowCharts(data.dashboard.showCharts);setNotifications(data.dashboard.notifications)}
 useEffect(()=>{fetch('/api/settings',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(applySettings).catch(()=>setPreferenceError('Saved settings could not be loaded. Open Settings to retry.'));check()},[]);
 useEffect(()=>{
  const query=window.matchMedia('(prefers-reduced-motion: reduce)');
  function move(event){
   if(query.matches||event.pointerType==='touch')return;
   const card=event.target.closest('.tab-content .live-checks>div,.stat');
   if(!card)return;
   const box=card.getBoundingClientRect();
   card.style.setProperty('--mouse-x',`${event.clientX-box.left}px`);
   card.style.setProperty('--mouse-y',`${event.clientY-box.top}px`);
  }
  document.addEventListener('pointermove',move,{passive:true});
  return ()=>document.removeEventListener('pointermove',move);
 },[]);
 useEffect(()=>{if(!seconds)return;const timer=setInterval(()=>{if(!document.hidden)check()},seconds*1000);return ()=>clearInterval(timer)},[seconds]);
 const symbols={ok:'✓',warning:'⚠',critical:'✕',unknown:'?',offline:'⊘'};
 const configuredApps=result?.configured_apps||configuredSettings?.apps||[];
 const brands=[...new Set(configuredApps.map(a=>a.brand?.trim()||a.name))];
 const selectedBrand=brands.includes(brandChoice)?brandChoice:brands[0]||'';
 const brandConfigured=configuredApps.filter(a=>(a.brand?.trim()||a.name)===selectedBrand);
 const environmentTabs=[['production','Production'],['uat','UAT'],['testing','Testing'],...(brandConfigured.some(a=>!a.environment||a.environment==='unassigned')?[['unassigned','Unassigned']]:[])];
 const selectedEnvironment=environmentTabs.some(([key])=>key===environmentChoice)?environmentChoice:'production';
 const brandApps=result?.apps.filter(a=>(a.brand?.trim()||a.name)===selectedBrand&&(a.environment||'unassigned')===selectedEnvironment)||[];
 const selectedApp=tab==='watcher'||tableView?null:brandApps.find(item=>item.id===tab)||brandApps[0];
 function selectApplication(id){setTab(id);setTableView(false);requestAnimationFrame(()=>{const panel=document.getElementById('panel-'+id);if(panel){const group=panel.closest('details');if(group)group.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'})}})}
 const currentIssues=result?.apps.flatMap(item=>Object.entries(item.checks).filter(([,value])=>['critical','warning'].includes(value.status)).map(([label,value])=>({app:item,label,value})))||[];
 return <section className="live-panel dashboard-workspace"><div className="section-heading"><div><h2>{page==='home'?'Server Monitor':'Infrastructure overview'}</h2><p className="muted">{seconds?`Auto-refresh every ${seconds} seconds while this tab is visible`:'Manual refresh · Use Check now for the latest results'}</p></div>{page!=='home'&&selectedApp&&<div className="selected-app-header"><div className="selected-app-title"><strong>📡 {selectedApp.name}</strong><span className="backend-tag">{selectedApp.backend}</span><span className={'pill '+(error?'maintenance':selectedApp.status)}>{error?'Stale':symbols[selectedApp.status]+' '+selectedApp.status}</span></div><div className="selected-app-links">{selectedApp.site_url&&<a href={selectedApp.site_url} target="_blank" rel="noreferrer">🌐 {selectedApp.site_url}</a>}{selectedApp.health_url&&<a href={selectedApp.health_url} target="_blank" rel="noreferrer">🔌 {selectedApp.health_url}</a>}</div></div>}
 <div className="overview-actions">{notifications&&<details className="notification-menu"><summary aria-label={'Notifications: '+(error?'unavailable':currentIssues.length+' findings')}>🔔 <span>{error?'?':currentIssues.length}</span></summary><div className="notification-popover"><div className="notification-heading"><strong>Current notifications</strong><small>Latest checks · not alert history</small></div>{error?<p className="muted">Watcher unavailable. Refresh to confirm current issues.</p>:currentIssues.length?currentIssues.map(({app,label,value})=><button key={app.id+label} onClick={event=>{setBrandChoice(app.brand?.trim()||app.name);setTab(app.id);setPreview({label,value,scope:app.name});event.currentTarget.closest('details').open=false}}><span className={'issue-mark '+value.status}>{symbols[value.status]}</span><span><strong>{app.name}</strong><small>{label}</small><small>{value.summary}</small></span><span>↗</span></button>):<p className="muted">✅ No warnings or critical app findings.</p>}</div></details>}<button className="refresh-choice" aria-haspopup="dialog" onClick={()=>setSettingsOpen(true)}>⚙ Settings</button><button className="primary" disabled={busy} onClick={check}>{busy?'Checking…':'Check now'}</button></div></div>
 {settingsOpen&&<Settings onClose={()=>setSettingsOpen(false)} onSaved={data=>{applySettings(data);setTab(null);setResult(null);setHistory([]);check(true);toast('Settings saved')}}/>}
 {page==='home'?<HomeDashboard onDetails={setPreview} result={result} settings={configuredSettings} stale={error} busy={busy} onOpen={(brand,environment)=>{setBrandChoice(brand);setEnvironmentChoice(environment);setSearch('');setTab(null);onNavigate?.('monitoring')}}/>:<>
<div className="brand-navigation"> <label className="brand-selector">Brand<select aria-label="Choose brand" value={selectedBrand} disabled={!brands.length} onChange={event=>{setBrandChoice(event.target.value);setTab(null);setSearch('')}}>{!brands.length&&<option value="">No brands configured</option>}{brands.map(brand=><option key={brand} value={brand}>{brand}</option>)}</select></label><label className="switch-label watcher-toggle"><span>🖥️ Watcher server</span><input type="checkbox" role="switch" aria-label="Show watcher server" checked={tab==='watcher'} onChange={event=>setTab(event.target.checked?'watcher':null)}/><span className="switch-track"/></label></div>
 {result&&<> {tab==='watcher'?<section role="tabpanel" id="panel-watcher" aria-labelledby="tab-watcher" className="tab-content"><h2>🖥️ Watcher server</h2><p className="muted">Local watcher server · separate from application servers</p><div className="live-checks">{Object.entries(result.watcher).filter(([name,value])=>!issuesOnly||['critical','warning'].includes(value.status)).map(([name,value])=><div key={name}><span>{icon(name)} {name.replace('Watcher computer · ','')}</span><span className={'pill '+(error?'maintenance':value.status)}>{error?'Stale':symbols[value.status]+' '+value.summary}</span><CheckDescription label={name} value={value} stale={error}/>{showCharts&&!error&&<Meter value={value}/>}<button className="recheck-button" disabled={busy||rechecking['__watcher__'+name]} onClick={()=>recheckCard('__watcher__',name)}>{rechecking['__watcher__'+name]?'Checking…':'↻ Recheck'}</button>{value.checked_at&&<small>Rechecked {new Date(value.checked_at).toLocaleTimeString()}</small>}<button className="details-button" onClick={()=>setPreview({label:name,value,scope:'Watcher server'})}>View details →</button></div>)}</div>{!Object.keys(result.watcher).length&&<p className="muted">Local metrics are disabled in Settings.</p>}</section>:tableView?null:null} </>}

 <div className="environment-tabs" role="tablist" aria-label="Monitoring environment">{environmentTabs.map(([key,label])=><button type="button" role="tab" id={'environment-tab-'+key} key={key} aria-selected={selectedEnvironment===key} aria-controls="environment-content" tabIndex={selectedEnvironment===key?0:-1} onClick={()=>{setEnvironmentChoice(key);setTab(null);setSearch('')}} onKeyDown={event=>{const index=environmentTabs.findIndex(([value])=>value===key);const next=event.key==='ArrowRight'?(index+1)%environmentTabs.length:event.key==='ArrowLeft'?(index+environmentTabs.length-1)%environmentTabs.length:event.key==='Home'?0:event.key==='End'?environmentTabs.length-1:null;if(next!==null){event.preventDefault();setEnvironmentChoice(environmentTabs[next][0]);setTab(null);document.getElementById('environment-tab-'+environmentTabs[next][0])?.focus()}}}>{label}</button>)}</div>
 <div role="tabpanel" id="environment-content" aria-labelledby={'environment-tab-'+selectedEnvironment}>


 {preferenceError&&<p className="notice" role="alert">{preferenceError}</p>}
 {error&&<p className="notice" role="alert">Watcher unavailable. Previous results below are stale; start the watcher backend and check again.</p>}

 {result&&<>
 {!result.apps.length&&<p className="notice">No enabled applications. Open Settings to add or enable an application.</p>}
 <div className="operations-strip"><div><span className={'pulse-dot '+(error?'unknown':result.watcher['Watcher internet']?.status||'unknown')}/><strong>{error?'Watcher unavailable':result.watcher['Watcher internet']?.status==='offline'?'Watcher offline':'Local watcher connected'}</strong><span className="muted">{result.apps.length} applications · {Object.values(result.counts).reduce((a,b)=>a+b,0)} app checks</span></div><span className="last-sync">Last sync {new Date(result.checked_at).toLocaleTimeString()}</span></div>
 {result.watcher['Watcher internet']?.status==='offline'&&<div className="notice" role="alert">⊘ Internet probes failed. Remote application results are unconfirmed; local checks continue.</div>}

 <div className="workspace-tools"><div><span className="eyebrow">APPLICATION WORKSPACE</span><p className="muted">{selectedBrand} · environments and application checks</p></div><div className="workspace-view-tools"><label className="switch-label table-switch"><span>{tableView?'☷ Table':'▦ Cards'}</span><input type="checkbox" role="switch" aria-label="Table view" checked={tableView} onChange={e=>changeView(e.target.checked)}/><span className="switch-track"/></label><label className="search-box"><span aria-hidden="true">⌕</span><input type="search" aria-label="Find application" placeholder="Find application…" value={search} onChange={e=>setSearch(e.target.value)}/></label></div></div>
 <EnvironmentWorkspace environment={selectedEnvironment} checkedAt={result.checked_at} apps={brandApps} brand={selectedBrand} search={search} tableView={tableView} error={error} issuesOnly={issuesOnly} showCharts={showCharts} history={history} busy={busy} rechecking={rechecking} onRecheck={recheckCard} onDetails={setPreview}/>

 </>}
 </div>
 </>}
 {preview&&<div className="detail-overlay" onClick={()=>setPreview(null)}><section className="detail-dialog" role="dialog" aria-modal="true" aria-labelledby="check-detail-title" onClick={event=>event.stopPropagation()} onKeyDown={event=>{if(event.key==='Escape')setPreview(null)}}><div className="section-heading"><h2 id="check-detail-title">{icon(preview.label)} {preview.label.replace('Watcher computer','Watcher server')}</h2><button autoFocus aria-label="Close details" onClick={()=>setPreview(null)}>✕</button></div><p className="muted">{preview.scope}</p><p className={'pill '+(error?'maintenance':preview.value.status)}>{error?'Stale result':preview.value.summary}</p><h3>Check details</h3>{preview.value.details&&<p className="notice">{preview.value.details}</p>}<h3>What this means</h3><p>{explain(preview.label,preview.value)}</p>{preview.url&&<p className="muted">Configured endpoint: {preview.url}</p>}<p className="muted">Checked: {result?new Date(result.checked_at).toLocaleString():'Not yet checked'}</p><p className="muted">Sensitive provider responses, credentials, and raw application logs are not included.</p><button className="primary" onClick={()=>{setPreview(null);check()}}>↻ Run checks again</button></section></div>}
 <p className="muted" role="status">{result?`Last completed check: ${new Date(result.checked_at).toLocaleTimeString()}`:'Waiting for the first live result…'}</p><small>Connections and preferences are managed in Settings. HTTP URLs have no SSL certificate. Database check uses SELECT 1 only.</small></section>
}
