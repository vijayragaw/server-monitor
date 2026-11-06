# Ubuntu server agent installation

This package reports CPU, RAM, disk usage/free capacity and uptime. It performs no remote commands, service changes, database connections or application diagnostics. Run it on each Ubuntu host you want to monitor. A shared host needs only one agent; multiple brands and environments can link to it.

## 1. Install on Ubuntu

Unzip this package on your Ubuntu server, open a terminal in its directory and run:

```bash
sudo bash install.sh
sudo systemctl status server-monitor-agent --no-pager
```

The installer uses Ubuntu apt packages and PyPI dependencies, creates a non-login service account, generates a random token, and enables a systemd service. It does not modify your firewall or expose a public listening address. Re-running preserves your token and environment configuration; it updates agent code/dependencies and restarts the service. Back up custom code before reinstalling. Python 3.10+ is required (Ubuntu 22.04/24.04 or newer with Python 3.10+).

## 2. Connect safely (choose one)

### Option A — SSH tunnel (default; no new server port exposure)

On your Windows monitoring computer, keep this PowerShell command running. Replace the username and server address:

```powershell
ssh -N -L 18449:127.0.0.1:8449 ubuntu@YOUR_SERVER_ADDRESS
```

Use this Agent URL in Settings:

```text
http://127.0.0.1:18449/v1/metrics
```

Use a different local port for each simultaneous server tunnel. If the tunnel closes, readings become unknown. Use your existing SSH access; the installer does not configure SSH keys or passwords.

### Option B — existing private network or VPN

Edit `/etc/server-monitor-agent/agent.env` using `sudoedit`. Set `MONITOR_BIND_HOST` to this server's private/VPN IP (for example `10.0.0.5`), leave `MONITOR_PORT=8449`, and restart:

```bash
sudo systemctl restart server-monitor-agent
```

If UFW is already configured/enabled, permit only the monitoring computer's VPN IP (replace `10.0.0.10`):

```bash
sudo ufw allow from 10.0.0.10 to any port 8449 proto tcp
```

Also restrict cloud firewall/security-group rules. Do not blindly enable UFW on an SSH session; preserve your SSH rule first. HTTP tokens are appropriate only inside the encrypted VPN/SSH transport; for other networks use HTTPS with a valid certificate through your existing reverse proxy. The dashboard refuses public HTTP agent URLs and never follows agent redirects or disables certificate verification.

## 3. Add it to the dashboard

Privately retrieve the token on Ubuntu:

```bash
sudo cat /etc/server-monitor-agent/token
```

Open **Settings → Servers → Add Ubuntu server**:

1. Enter a server name and Agent URL from the selected connection method.
2. Paste the token, then click **Test connection**.
3. Click **Save settings**.
4. In **Applications**, select this server for the relevant apps, brands and environments, and save again.
5. Use **Check now** on Home. Remote readings appear under **Ubuntu servers**.

Server checks follow the dashboard refresh interval while the dashboard is open; there is no independent scheduler or historical storage. A failed connection is unknown/unconfirmed, not a successful or measured critical CPU reading. Disabled servers make no agent requests. Application website/API checks run independently of this link.

Tokens remain in the local watcher's `settings.json` and the agent's protected token file; settings responses and dashboard readings do not reveal them. Protect those files and their backups. A blank token field preserves the existing saved token. To rotate, replace the token file with a new random token of at least 32 characters, restart the agent, and enter the same new token in Settings. Tokens are not encrypted at rest by this version.

## Maintenance

```bash
sudo journalctl -u server-monitor-agent -n 30 --no-pager
sudo systemctl restart server-monitor-agent
sudo systemctl disable --now server-monitor-agent
```

Disk metrics describe `MONITOR_DISK_PATH` (default `/`). Edit the environment file to choose another mounted filesystem, then restart. Additional disks, services, ports, queue, mail and database checks are not part of this host agent. Synchronize server time; readings older than five minutes are rejected.

The service runs without root privileges, with no added capabilities and a read-only filesystem sandbox. This package was validated with automated authentication/metrics tests; actual Ubuntu/systemd installation must be verified on your server.

References: [Ubuntu firewall documentation](https://ubuntu.com/server/docs/firewalls/), [systemd service sandboxing](https://freedesktop.org/software/systemd/man/latest/systemd.exec.html).
