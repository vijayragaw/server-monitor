import React from 'react';
function description(label){
 const n=label.toLowerCase();
 if(n.includes('ssl'))return 'Checks certificate trust, hostname and expiry for this HTTPS address.';
 if(n.includes('database'))return 'Runs a lightweight SELECT 1 through the application’s configured database connection.';
 if(n.includes('mail'))return 'Tests the encrypted SMTP connection and login. This check does not send an email.';
 if(n.includes('errors today'))return 'Counts today’s Laravel error entries, including earlier issues that may already be fixed.';
 if(n.includes('failed jobs'))return 'Counts failed database-queue jobs from the last 24 hours when supported.';
 if(n.includes('queue'))return 'Checks pending jobs in the configured database-backed queue.';
 if(n.includes('laravel cache'))return 'Writes, reads and removes a temporary key to verify the cache works.';
 if(n.includes('session'))return 'Checks that Laravel’s session folder exists and PHP can write to it.';
 if(n.includes('compiled views'))return 'Checks that Laravel can write compiled templates to the views folder.';
 if(n.includes('bootstrap'))return 'Checks that Laravel’s bootstrap cache folder exists and is writable.';
 if(n.includes('storage'))return 'Checks that Laravel’s storage directory exists and is writable.';
 if(n.includes('website'))return 'Requests the configured website and measures its HTTP response time.';
 if(n.includes('api'))return 'Checks the backend endpoint and its configured health response.';
 if(n.includes('cpu'))return 'Current processor load on this local watcher server.';
 if(n.includes('ram'))return 'Percentage of physical memory currently used on this server.';
 if(n.includes('disk'))return 'Used space on the local disk configured in XML.';
 if(n.includes('uptime'))return 'Time since this watcher server last booted.';
 return 'Latest result from this application’s configured monitoring source.';
}
function feedback(label,value){
 const n=label.toLowerCase();
 if(value.status==='offline')return '⊘ Watcher internet probes failed. Remote status is unconfirmed.';
 if(value.status==='unknown')return value.summary.includes('HTTP URL')?'ℹ️ HTTP address — no SSL certificate to check.':'❔ No confirmed result. Check configuration and source availability.';
 if(value.status==='critical'){
  if(n.includes('errors'))return '🚨 Error count is high. Review today’s log to identify the causes.';
  if(n.includes('mail'))return '🚨 SMTP test failed. View details or send a manual test.';
  if(n.includes('database'))return '🚨 Database test failed. Review connection details.';
  if(n.includes('disk'))return '🚨 Disk usage is high. Review available space.';
  return '🚨 Action needed. Open details to investigate this result.';
 }
 if(value.status==='warning')return '⚠️ Attention recommended. Review the reading and check details.';
 if(n.includes('database'))return '✅ Database connection test passed.';
 if(n.includes('mail'))return '✅ SMTP login passed. Inbox delivery is not tested.';
 if(n.includes('writable'))return '✅ Folder is present and writable.';
 if(n.includes('cache'))return '✅ Cache read/write test passed.';
 if(n.includes('ssl'))return '✅ Certificate verified and outside the expiry warning window.';
 if(n.includes('website')||n.includes('api'))return '✅ Endpoint passed its configured availability check.';
 return '✅ Current reading is within the configured healthy range.';
}
export default function CheckDescription({label,value,stale}){
 return <div className="check-description"><div className={'check-feedback '+(stale?'unknown':value.status)}>{stale?'⏸ Previous reading. Refresh to confirm current status.':feedback(label,value)}</div></div>
}
