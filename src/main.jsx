import React, {useState, useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import LiveHealth from './LiveHealth';
import './style.css';

function App(){
 const [page,setPage]=useState(()=>location.hash==='#monitoring'?'monitoring':'home');
 useEffect(()=>{const update=()=>setPage(location.hash==='#monitoring'?'monitoring':'home');window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update)},[]);
 function navigate(value){location.hash=value==='home'?'home':'monitoring';setPage(value)}
 const [night,setNight]=useState(()=>{try{return localStorage.getItem('monitor-theme')!=='light'}catch{return true}});
 useEffect(()=>{document.documentElement.dataset.theme=night?'night':'light';try{localStorage.setItem('monitor-theme',night?'night':'light')}catch{}},[night]);

 return <>
  <header>
   <a className="logo" href="/"><span className="logo-icon">⌁</span><span>Server Monitor<small>Local watcher · Settings saved locally</small></span></a>
   <nav className="page-navigation" aria-label="Main navigation"><button className={page==='home'?'active':''} aria-current={page==='home'?'page':undefined} onClick={()=>navigate('home')}><span aria-hidden="true">⌂</span> Home</button><button className={page==='monitoring'?'active':''} aria-current={page==='monitoring'?'page':undefined} onClick={()=>navigate('monitoring')}><span aria-hidden="true">▥</span> Monitoring</button></nav>
   <div className="header-actions"><span className="workspace-label">LOCAL WORKSPACE</span><label className="switch-label theme-toggle"><span>{night?'🌙 Night':'☀️ Light'}</span><input type="checkbox" role="switch" aria-label="Night theme" checked={night} onChange={e=>setNight(e.target.checked)}/><span className="switch-track"/></label></div>
  </header>
  <main>
   <LiveHealth page={page} onNavigate={navigate}/>
   <footer><span>Server Monitor · Localhost</span><span>Latest results only</span></footer>
  </main>
 </>;
}
createRoot(document.getElementById('root')).render(<App/>);
