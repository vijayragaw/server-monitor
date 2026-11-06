import React from 'react';
export default function Speedometer({value,status}){
 const max=Math.max(5000,Math.ceil(value/1000)*1000),ratio=Math.max(0,Math.min(1,value/max));
 const point=(angle,radius)=>({x:100+radius*Math.cos(angle*Math.PI/180),y:92+radius*Math.sin(angle*Math.PI/180)});
 const needle=point(180+ratio*180,57);
 return <div className={'speedometer '+status} role="meter" aria-label="Response time in milliseconds; lower is faster" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
 <svg viewBox="0 0 200 125" aria-hidden="true"><path className="speed-track" d="M20 92 A80 80 0 0 1 180 92"/><path className="speed-zone fast" d="M20 92 A80 80 0 0 1 35.3 45"/><path className="speed-zone medium" d="M35.3 45 A80 80 0 0 1 75.3 15.9"/><path className="speed-zone slow" d="M75.3 15.9 A80 80 0 0 1 180 92"/>
 {Array.from({length:11},(_,i)=>{const a=point(180+i*18,68),b=point(180+i*18,i%5===0?57:62);return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="speed-tick"/>})}
 <text x="16" y="107" className="speed-label">0</text><text x="100" y="38" textAnchor="middle" className="speed-label">{max/2}</text><text x="184" y="107" textAnchor="end" className="speed-label">{max}</text>
 <g className="speed-needle" style={{transform:`rotate(${ratio*180}deg)`,transformOrigin:'100px 92px'}}><path d="M100 87 L39 92 L100 97 Z"/></g><circle cx="100" cy="92" r="7" className="speed-hub"/><text x="100" y="119" textAnchor="middle" className="speed-value">{value} ms</text></svg><small>Response time · lower is faster</small></div>
}
