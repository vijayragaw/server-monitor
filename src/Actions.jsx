import LogReport from './LogReport';
import React,{useState} from 'react';
import {notify,loading,toast,emailPrompt} from './notifications';
export default function Actions({app,checkLabel}){
 const [report,setReport]=useState(null),[analysing,setAnalysing]=useState(false);
 const [busy,setBusy]=useState(false),[downloading,setDownloading]=useState(false);
 async function send(){
  if(busy)return;setBusy(true);const choice=await emailPrompt(app.name);if(!choice.isConfirmed){setBusy(false);return}const email=choice.value;loading('Sending test email',`Testing ${app.name}. Please wait…`);
  try{
   const r=await fetch(`/api/apps/${encodeURIComponent(app.id)}/mail-test`,{method:'POST',headers:{'Content-Type':'application/json','X-Monitor-Action':'manual'},body:JSON.stringify({email}),signal:AbortSignal.timeout(25000)});
   const data=await r.json();const text=typeof data.summary==='string'?data.summary:typeof data.detail==='string'?data.detail:'Test failed';
   notify(r.ok&&data.status==='ok'?'SMTP accepted the test email':'Mail test needs attention',text,r.ok&&data.status==='ok'?'success':'error');
  }catch{const text='Mail test unavailable or timed out. Delivery is unconfirmed; check before retrying.';notify('Mail test unavailable',text,'error')}finally{setBusy(false)}
 }
 async function download(){
  if(downloading)return;setDownloading(true);loading('Preparing today’s log','Collecting and redacting Laravel log entries…');
  try{
   const r=await fetch(`/api/apps/${encodeURIComponent(app.id)}/logs-today`,{signal:AbortSignal.timeout(25000)});
   if(!r.ok)throw new Error('Log export unavailable. Check that Laravel and the watcher are running.');
   const blob=await r.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='today-laravel.log';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);toast('Log download started');
  }catch{notify('Download failed','The log export could not be downloaded. Check that Laravel and the watcher are running.','error')}finally{setDownloading(false)}
 }
 async function analyse(){
  if(analysing)return;setAnalysing(true);loading('Analysing today’s logs','Reading bounded sources and grouping errors in memory…');
  try{const response=await fetch(`/api/apps/${encodeURIComponent(app.id)}/analyse-logs`,{method:'POST',headers:{'X-Monitor-Action':'manual'},signal:AbortSignal.timeout(45000)});if(!response.ok)throw new Error();const data=await response.json();toast('Analysis ready');setReport(data)}catch{notify('Analysis unavailable','Check the app’s XML log URLs and that Laravel is running. No copied log file was saved.','error')}finally{setAnalysing(false)}
 }
 return <div className="card-actions">{report&&<LogReport report={report} onClose={()=>setReport(null)}/>}{checkLabel==='Mail'&&app.actions?.mail&&<button className="refresh-choice" disabled={busy} onClick={send}>✉️ {busy?'Sending…':'Send test email'}</button>}{checkLabel==='Laravel errors today'&&app.actions?.analysis&&<button className="refresh-choice" disabled={analysing} onClick={analyse}>🔎 {analysing?'Analysing…':'Analyse today’s logs'}</button>}{checkLabel==='Laravel errors today'&&app.actions?.logs&&<button className="refresh-choice" disabled={downloading} onClick={download}>📥 {downloading?'Preparing…':'Download today’s log'}</button>}</div>
}
