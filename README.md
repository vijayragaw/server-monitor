## Brand and environment overview

The always-visible top overview groups configured monitors by brand and Testing, UAT and Production. Use Settings to assign a brand and environment to each application endpoint. Existing records without these fields remain Unassigned. Greentrends, Naturals and Innocare are brand suggestions; no endpoints or healthy sample readings are created for them. Missing environment rows show a dash. Multiple named projects can share a brand/environment and appear as separate rows.

Status icons show success, warning, danger, unknown, disabled and not configured. Select a populated icon for details or an application name to open its detailed checks. Grouped columns show the most severe available result. The server strip measures only the local watcher server. Services, ports, SMS and version monitoring are not supplied by current probes.

# Local settings

Open **Settings** in the dashboard to add/edit/remove applications, enable or disable apps and individual checks, and save refresh, table view, issue filter, charts, current notifications and local computer metrics preferences. Save applies changes to the next check without a backend restart. Cancel discards form edits.

Settings are read from `config.xml` at backend startup. Dashboard saves update the same file atomically. On first startup with a legacy XML file, existing `settings.json` values migrate into XML, with JSON retained as a backup. The new `<dashboard>` element marks the migration complete.

For manual changes, stop the backend, edit `config.xml`, and restart it. Edit `<dashboard>` for refresh and display settings, `<app>` for application URLs, SSH aliases and enable switches, and `<server>` for remote server settings. To disable a check inside an application, add a child such as `<disabledCheck name="Website SSL"/>`. The monitor root keeps the disk path, connectivity probes and local metrics switch. The file can contain agent tokens. Restrict access to it and keep it out of source control.

Disabled apps do not run checks. Disabled individual probes are skipped; Laravel health and diagnostics checks share endpoints, so an enabled sibling may still request the same endpoint and perform its server-side diagnostics. Disabling current notifications hides the findings menu; it does not send or suppress external alerts. No scheduler, database server or email sending is added by settings saves.

The older implementation notes below describe the original XML/browser configuration and are superseded by this section for settings storage and app management.

# Server Monitor — local watcher

Only live checks are shown. Monitoring URLs and the polling interval are manually configured in `config.xml`. Restart the watcher backend after editing XML. This initial XML format supports one brand.

## Start

1. Install Python dependencies: `.venv\Scripts\python.exe -m pip install -r backend/requirements.txt` (create the virtual environment with `python -m venv .venv` first).
2. Start backend: `.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8081 --workers 1`
3. Run `npm install`, then `npm run dev` for the dashboard at http://127.0.0.1:5173.
4. Keep Angular and Laravel running separately.

Checks: Angular HTTP availability/response time, Laravel health/response time, MySQL status from Laravel, and verified TLS certificate expiry for website and API HTTPS URLs. HTTP URLs show SSL as not applicable. Website availability checks do not exercise Angular login or business workflows. Database probe uses SELECT 1 only.

Certificates warn below 15 days and are critical below 5 days. Certificate validation remains enabled; invalid certificates are critical and network failures are unknown. The TLS probe checks the configured hostname; configure the final HTTPS URL when a site redirects to another hostname.

No credentials are stored in this project. The local Laravel endpoint is restricted to loopback and the local Laravel environment. This development watcher is loopback-only and has no login yet. Checks run when the dashboard polls; an independent scheduler is a future step. No historical data is stored.

Validation: `npm run build` and `.venv\Scripts\python.exe -m pytest backend -q` (install pytest for tests).

Mail monitoring: optional mailHealthUrl in config.xml points to Laravel's loopback-only /api/health/mail endpoint. It uses Laravel's existing SMTP configuration, requires encrypted SMTP, and only connects/authenticates (no email sent). Unsupported mailer/URL-only configurations show unknown. Connection and authentication failures show critical without exposing provider errors or credentials. The check follows the user-selected refresh setting.


Additional diagnostics: diagnosticsUrl in XML points to the local Laravel /api/health/diagnostics endpoint. It tests cache with a unique temporary key, folder writability, database-backed default queue counts when supported, failed jobs in the last 24 hours, and current-day Laravel error entries (bounded to 20 MB per standard log file). Error messages and credentials are never returned. Unsupported queues or unavailable tables are unknown. Error counts include earlier failures today, not just active incidents. localMetrics=true and diskPath in XML enable CPU/RAM/disk/uptime for the watcher computer only; a remote Linux agent is still required for production machine metrics. Refresh controls are browser-local; default manual, presets or custom seconds, with one initial check on opening.

Multi-application XML: add one <app> per application with unique id, name, backend, and optional siteUrl/healthUrl. backend=http checks HTTP status only (any technology); backend=json checks a JSON field (statusPath defaults to status, expectedValue defaults to ok); backend=laravel expects the existing database health contract and optionally mailHealthUrl/diagnosticsUrl. Apps can use entirely different hosts and ports. Only configured checks run. Restart backend after XML changes. Current configured apps are Billing local and Devtest online; no sample apps are shown. This is an incremental live overview, not completion of all security, alerts, remote-agent or screen requirements in the reference spec.

Manual tools: configure mailTestUrl and logDownloadUrl per Laravel app in XML. The UI sends email only on explicit submit, with recipient validation and a 6/minute Laravel throttle. Provider acceptance does not guarantee delivery. The manual POST requires a custom action header and rejects non-local browser origins. Log download exports current-day standard Laravel log entries with a 20 MB bound, omitting sensitive context and known credentials. Treat remaining log content as confidential. Database and SMTP details classify exceptions locally without exposing raw connection errors. These Laravel diagnostic routes remain local-environment/loopback only.

Operational checks: XML internetProbes is a comma-separated list of TCP host:port probes (2 seconds each). Any success confirms watcher connectivity; total failure marks remote checks offline/unconfirmed while local checks continue. Database response time measures Laravel connection setup plus SELECT 1 (warning 800 ms, critical 2000 ms). Local disk reports free and total GiB alongside percentage. UI findings are current readings, not stored alert history; search filters app navigation. No background monitoring or external alerts are implied.

Each card now supports a manual Recheck action. The /api/recheck endpoint selects only that monitor; Laravel database checks share the health endpoint and diagnostics share their diagnostics endpoint. Rechecks update the chosen card and summary counts with a per-card timestamp. They do not send email. Full-page sync time remains the last complete refresh.

Table view: the Cards/Table switch in the workspace toolbar toggles between grouped cards for the selected app and a comparison table with one row per configured app and one column per check. The view preference is stored in this browser. Table cells retain details, per-check recheck, mail tests and log downloads. Unconfigured checks display a dash; search and issue filters apply to app rows. The watcher tab remains separate.

## Log analysis
Use Analyse today’s logs on the Laravel errors card. Error patterns include counts, first/last timestamps, recorded application location, suggested checks and verification steps. Reports are deterministic and do not assert a confirmed diagnosis or correlate an API route unless recorded.

XML requestLogUrl supplies the optional local /api/health/request-log endpoint. Local-only request timing records route templates, methods, statuses and durations, excluding health requests and all payloads, query values, users and IPs. Its app-side source is capped at 10 MB per day. Files named monitor-requests-YYYY-MM-DD.jsonl older than yesterday are cleaned up on application requests. Original Laravel logs are untouched. Set MONITOR_REQUEST_TIMING=false in Laravel to disable timing collection.

No copied log file is saved by the watcher. Processing and the displayed report are in memory. Closing the report discards its React state. Input size limits and the top-100 display limit mean analysis can be partial. Same-route calls within a second are burst candidates across all callers, not proven duplicates. API coverage starts when instrumentation is enabled, not at midnight retroactively.

Brand navigation now uses one Brand dropdown shared by the overview and Application Workspace. Each section groups the selected brand into collapsible Testing, UAT and Production environments, with Unassigned shown only for legacy monitors. Brand selection is a viewing filter; it does not stop other configured monitors from being checked.

Home is the default page and shows all brands across Production, UAT and Testing, summary counts, local watcher server readings, and current warning/danger findings. Select a brand/environment status to open that selection in Monitoring. Home and Monitoring share the same in-memory results and refresh controls. Use header navigation or #home / #monitoring; switching pages does not trigger a separate polling loop.

## Ubuntu remote servers

Settings now includes a Servers tab with Ubuntu server name, agent URL, token, enable switch and Test connection. Link an app to its host using the Server selector in Applications. Home displays remote CPU/RAM/disk/free capacity/uptime in the Ubuntu servers table. All enabled agents are polled concurrently during dashboard refresh; local watcher metrics remain separate. The agent has no application/database/mail/service-control features.

See ubuntu-agent/README.md for installation and SSH tunnel/VPN setup. The installer defaults to loopback and does not modify firewall rules. No remote server has been installed or connected automatically. Saved agent tokens are kept in the local settings file, redacted from settings API responses, and preserved when the token field is left blank. Protect settings files and backups.

## Direct monitoring over SSH

Set an application's **Direct SSH alias** in **Settings → Applications** to use the SSH probe for MySQL, SMTP and Laravel log errors. Laravel health URLs are bypassed in this mode. A Website URL still enables its separate website and certificate checks.

On the monitor host, add an OpenSSH alias for the Ubuntu host in the SSH configuration of the account running the Python backend. Configure key authentication, verify the server host key, and test the same account with:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu-monitor python3 --version
```

On the Ubuntu host, create `~/.config/server-monitor/direct.xml` for the SSH user and restrict it to that user (`chmod 600`). Use the application ID shown in the dashboard. An existing `direct.json` remains readable until you add `direct.xml`.

```xml
<direct>
  <app id="billing-local" logDir="/srv/billing/storage/logs"
       mysqlDefaultsFile="~/.config/server-monitor/billing.cnf">
    <smtp host="smtp.example.com" port="587" username="monitor@example.com"
          password="REPLACE_WITH_SMTP_PASSWORD" from="monitor@example.com"/>
  </app>
</direct>
```

Set only the sources you want. The SSH user needs read access to the configured logs and files. The MySQL option file is a private `[client]` file with the monitoring account's connection options, and the Ubuntu host needs the `mysql` client. The database probe runs `SELECT 1`. SMTP uses STARTTLS by default. Use `tls="implicit"` and the appropriate port for implicit TLS. Keep credentials on Ubuntu and outside the application repository.

The Laravel error check and analysis read bounded tails of today's standard logs. Download in SSH mode exports a sanitized error summary. An optional `requestLog` path can point to an existing compatible JSONL timing file. Cache, queue and Laravel API health checks are not provided by the SSH probe.

## Configuration for a fresh clone

Copy `config.example.xml` to `config.xml` before starting the backend. Set the disk path and add your real applications and servers in the dashboard or XML. Keep the live `config.xml` and any legacy `settings.json` private.
