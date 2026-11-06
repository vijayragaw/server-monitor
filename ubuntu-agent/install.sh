#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run: sudo bash install.sh' >&2
  exit 1
fi
agent_source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
apt-get update
apt-get install -y python3 python3-venv
if ! id server-monitor-agent >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin server-monitor-agent
fi
install -d -m 0755 /opt/server-monitor-agent
install -d -m 0750 -o root -g server-monitor-agent /etc/server-monitor-agent
install -m 0644 "$agent_source_dir/agent.py" /opt/server-monitor-agent/agent.py
install -m 0644 "$agent_source_dir/requirements.txt" /opt/server-monitor-agent/requirements.txt
python3 -m venv /opt/server-monitor-agent/.venv
/opt/server-monitor-agent/.venv/bin/python -m pip install -r /opt/server-monitor-agent/requirements.txt
if [[ ! -f /etc/server-monitor-agent/token ]]; then
  (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > /etc/server-monitor-agent/token)
fi
chown root:server-monitor-agent /etc/server-monitor-agent/token
chmod 0640 /etc/server-monitor-agent/token
if [[ ! -f /etc/server-monitor-agent/agent.env ]]; then
  install -m 0640 -o root -g server-monitor-agent "$agent_source_dir/agent.env.example" /etc/server-monitor-agent/agent.env
fi
install -m 0644 "$agent_source_dir/server-monitor-agent.service" /etc/systemd/system/server-monitor-agent.service
systemctl daemon-reload
systemctl enable --now server-monitor-agent
systemctl restart server-monitor-agent
if ! systemctl is-active --quiet server-monitor-agent; then
  echo 'Service did not start. Run: sudo journalctl -u server-monitor-agent -n 30 --no-pager' >&2
  exit 1
fi
echo 'Agent installed on loopback port 8449 (unless previously configured otherwise).'
echo 'Use an SSH tunnel or configure a private/VPN address; see README.md.'
echo 'Retrieve your token privately: sudo cat /etc/server-monitor-agent/token'
