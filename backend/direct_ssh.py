"""SSH transport for opt-in direct application checks."""
import asyncio
import json
import re
from pathlib import Path

DIRECT_LABELS = ('Database', 'Database response time', 'Mail', 'Laravel errors today')
PROBE = Path(__file__).with_name('direct_probe.py').read_text(encoding='utf-8-sig')
ALIAS = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')


async def direct_request(item, action, **arguments):
    alias = item['sshAlias']
    if not ALIAS.fullmatch(alias):
        raise ValueError('Invalid SSH alias')
    payload = json.dumps({'app': item['id'], 'action': action, **arguments})
    command = PROBE + f'\nprint(json.dumps(run(json.loads({payload!r}))))\n'
    process = await asyncio.create_subprocess_exec(
        'ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=5', alias, 'python3', '-',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(command.encode()), timeout=17)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode or len(output) > 16 * 1024 * 1024:
        raise ValueError('SSH probe failed')
    data = json.loads(output)
    if not isinstance(data, dict):
        raise ValueError('Invalid SSH probe response')
    return data
