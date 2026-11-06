import React from 'react';
export function Meter({value}){
 const number=parseFloat(value.summary);
 if(!value.summary.includes('%')||!Number.isFinite(number))return null;
 const bounded=Math.max(0,Math.min(100,number));
 return <div className={'gauge '+value.status} role="meter" aria-label="Usage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={bounded}><svg viewBox="0 0 120 72" aria-hidden="true"><path className="gauge-track" d="M 12 60 A 48 48 0 0 1 108 60"/><path className="gauge-fill" d="M 12 60 A 48 48 0 0 1 108 60" pathLength="100" strokeDasharray={`${bounded} 100`}/><text x="60" y="57" textAnchor="middle">{number}%</text></svg><small>0% <span>100%</span></small></div>
}
export function Trend({history,appId,stale}){
 const points=history.map(h=>({at:h.at,value:h.apps.find(a=>a.id===appId)?.checks['Backend API']?.duration_ms??h.apps.find(a=>a.id===appId)?.checks.Website?.duration_ms})).filter(p=>Number.isFinite(p.value));
 if(points.length<2)return <div className="trend-wait"><span>📈 Response trend</span><small>{points.length} reading · refresh again to build the chart</small></div>;
 const max=Math.max(100,...points.map(p=>p.value));
 const coordinates=points.map((p,i)=>`${20+i*660/Math.max(1,points.length-1)},${130-p.value/max*100}`).join(' ');
 return <details className="trend compact-trend"><summary>📈 Response trend <small> · {points.length} readings · click to expand</small></summary><div className="section-heading"><h3>📈 Response time</h3><small>{stale?'Last known readings':`${points.length} readings · this browser session`}</small></div>{points.length<2?<p className="muted">Collecting live readings. Refresh again to start the chart.</p>:<><svg viewBox="0 0 700 155" role="img" aria-label="Response times from the last 30 successful refreshes"><path d="M20 30H680 M20 80H680 M20 130H680" className="chart-grid"/><polyline points={coordinates} className="chart-line"/>{points.map((p,i)=><circle key={i} cx={20+i*660/(points.length-1)} cy={130-p.value/max*100} r="4" fill="#8d9fff"><title>{new Date(p.at).toLocaleTimeString()}: {p.value} ms</title></circle>)}</svg><div className="chart-caption"><span>{new Date(points[0].at).toLocaleTimeString()}</span><span>Scale: 0–{max} ms</span><span>{new Date(points.at(-1).at).toLocaleTimeString()}</span></div></>}<small>API response time when available; otherwise website. Up to 30 readings, cleared on page reload.</small></details>
}
