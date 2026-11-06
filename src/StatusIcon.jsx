import React from 'react';
export default function StatusIcon({status}){
 const paths={ok:<path d="m5 12 4 4L19 6"/>,warning:<><path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5m0 3h.01"/></>,critical:<path d="m6 6 12 12M18 6 6 18"/>,unknown:<><path d="M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5"/><path d="M12 17h.01"/></>,disabled:<path d="M8 5v14M16 5v14"/>,missing:<path d="M5 12h14"/>,offline:<><circle cx="12" cy="12" r="8"/><path d="m6.5 17.5 11-11"/></>};
 return <svg className="status-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[status]||paths.unknown}</svg>
}
