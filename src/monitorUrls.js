export function monitorDefaults(app) {
  if (app.backend !== 'laravel') return {};
  try {
    const url = new URL(app.healthUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return {};
    const health = app.healthUrl && /\/health\/?$/.test(url.pathname)
      ? url.origin + url.pathname.replace(/\/$/, '')
      : url.origin + '/api/health';
    return {
      healthUrl: health,
      mailHealthUrl: health + '/mail',
      diagnosticsUrl: health + '/diagnostics',
      mailTestUrl: health + '/mail-test',
      logDownloadUrl: health + '/logs-today',
      requestLogUrl: health + '/request-log',
    };
  } catch {
    return {};
  }
}

export function updateMonitorField(app, key, value) {
  const next = { ...app, [key]: value };
  if (!['healthUrl', 'backend'].includes(key) || next.backend !== 'laravel') return next;

  const previousDefaults = monitorDefaults(app);
  const defaults = monitorDefaults(next);
  for (const field of new Set([...Object.keys(previousDefaults), ...Object.keys(defaults)])) {
    if (field !== 'healthUrl' && (!next[field] || next[field] === previousDefaults[field])) {
      next[field] = defaults[field] || '';
    }
  }
  return next;
}


export function apiBaseUrl(healthUrl) {
  if (!healthUrl) return '';
  try {
    const url = new URL(healthUrl);
    if (/\/health\/?$/.test(url.pathname)) {
      return url.origin + url.pathname.replace(/\/health\/?$/, '');
    }
  } catch {
    return healthUrl;
  }
  return healthUrl;
}

export function withApiBaseUrl(app, baseUrl) {
  if (!baseUrl.trim()) return updateMonitorField(app, 'healthUrl', '');
  const url = new URL(baseUrl.trim());
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Enter an HTTP or HTTPS API URL without credentials, a query, or a fragment.');
  }
  const path = url.pathname.replace(/\/+$/, '');
  const healthUrl = url.origin + path + (path.endsWith('/health') ? '' : '/health');
  return updateMonitorField(app, 'healthUrl', healthUrl);
}
