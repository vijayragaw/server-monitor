<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class MonitorHealthController extends Controller
{
    private function safeFailure(\Throwable $error, string $kind): string
    {
        $text = strtolower($error->getMessage());
        // Classify locally; never expose exception text or connection credentials.
        foreach ([
            'expired' => 'Provider reports password or credential expired',
            'blocked' => 'Provider reports account or connection blocked',
            'locked' => 'Provider reports account locked',
            '535' => 'SMTP 535: authentication rejected; verify credentials or app password',
            '534' => 'SMTP 534: additional authentication or app password required',
            'access denied' => 'Database authentication or permissions rejected',
            '1049' => 'Configured database does not exist',
            'timed out' => 'Connection timed out; check network, firewall and server availability',
            'timeout' => 'Connection timed out; check network, firewall and server availability',
            'refused' => 'Connection refused; check host, port and running service',
            'certificate' => 'TLS certificate verification failed',
            'starttls' => 'Secure SMTP negotiation failed',
            '550' => 'SMTP 550: recipient or sender rejected by provider policy',
            '553' => 'SMTP 553: sender or recipient address rejected',
            'resolve' => 'Server hostname could not be resolved',
        ] as $match => $message) {
            if (str_contains($text, $match)) { return $message; }
        }
        return $kind === 'mail' ? 'SMTP connection or authentication failed; provider did not supply a recognized cause' : 'Database connection failed; check service, network and credentials';
    }

    public function logs(Request $request)
    {
        abort_unless(app()->environment('local') && in_array($request->server('REMOTE_ADDR'), ['127.0.0.1', '::1'], true), 404);
        $today = date('Y-m-d');
        $root = realpath(storage_path('logs'));
        $output = "Laravel log export for $today (up to last 20 MB per file; redacted)\n";
        foreach (['laravel.log', 'laravel-'.$today.'.log'] as $name) {
            $path = realpath(storage_path('logs/'.$name));
            if (!$path || !$root || !str_starts_with($path, $root.DIRECTORY_SEPARATOR) || !is_readable($path)) { continue; }
            $file = fopen($path, 'rb');
            if (fstat($file)['size'] > 20*1024*1024) { fseek($file, -20*1024*1024, SEEK_END); fgets($file); }
            $include = false;
            while (($line = fgets($file, 8192)) !== false) {
                if (preg_match('/^\[(\d{4}-\d{2}-\d{2}) /', $line, $matches)) { $include = $matches[1] === $today; }
                if (!$include) { continue; }
                // Drop sensitive context lines; redact known configured credentials.
                if (preg_match('/password|authorization|bearer|token|secret|cookie|SQL:|bindings/i', $line)) { $output .= "[sensitive context omitted]\n"; continue; }
                foreach ([config('database.connections.'.config('database.default').'.password'), config('mail.mailers.smtp.password'), config('app.key')] as $secret) {
                    if (is_string($secret) && strlen($secret) > 3) { $line = str_replace($secret, '[REDACTED]', $line); }
                }
                $output .= $line;
                if (strlen($output) >= 20*1024*1024) { break; }
            }
            fclose($file);
            if (strlen($output) >= 20*1024*1024) { break; }
        }
        return response($output)->header('Content-Type', 'text/plain; charset=UTF-8')->header('Content-Disposition', 'attachment; filename="laravel-'.$today.'.log"')->header('Cache-Control', 'no-store');
    }

    public function requestLog(Request $request)
    {
        abort_unless(app()->environment('local') && in_array($request->server('REMOTE_ADDR'), ['127.0.0.1', '::1'], true), 404);
        $path = storage_path('logs/monitor-requests-'.date('Y-m-d').'.jsonl');
        if (!is_file($path)) { return response('', 200)->header('Content-Type', 'application/x-ndjson')->header('Cache-Control', 'no-store'); }
        // Only the fixed current-day file is exposed; never accept a client path.
        $root = realpath(storage_path('logs'));
        $real = realpath($path);
        abort_unless($real && str_starts_with($real, $root.DIRECTORY_SEPARATOR), 404);
        return response()->stream(function () use ($real) {
            $file = fopen($real, 'rb');
            $remaining = 10 * 1024 * 1024;
            while (!feof($file) && $remaining > 0) {
                $part = fread($file, min(65536, $remaining));
                echo $part; $remaining -= strlen($part);
            }
            fclose($file);
        }, 200, ['Content-Type' => 'application/x-ndjson', 'Cache-Control' => 'no-store']);
    }

    public function diagnostics(Request $request)
    {
        abort_unless(app()->environment('local') && in_array(
            $request->server('REMOTE_ADDR'), ['127.0.0.1', '::1'], true
        ), 404);
        $results = [];
        $key = 'monitor_health_'.bin2hex(random_bytes(12));
        try {
            $cache = \Illuminate\Support\Facades\Cache::store();
            $cache->put($key, 'ok', 15);
            $ok = $cache->get($key) === 'ok';
            $results['cache'] = ['status' => $ok ? 'ok' : 'critical'];
        } catch (\Throwable $error) {
            $results['cache'] = ['status' => 'critical'];
        } finally {
            try { if (isset($cache)) { $cache->forget($key); } } catch (\Throwable $error) {}
        }
        foreach (['storage' => storage_path(), 'sessions' => storage_path('framework/sessions'), 'compiled_views' => storage_path('framework/views'), 'bootstrap_cache' => base_path('bootstrap/cache')] as $name => $path) {
            $ok = is_dir($path) && is_writable($path);
            $results[$name] = ['status' => $ok ? 'ok' : 'critical'];
        }
        $results['queue'] = ['status' => 'unknown'];
        $results['failed_jobs'] = ['status' => 'unknown'];
        $queue = config('queue.connections.'.config('queue.default'), []);
        if (($queue['driver'] ?? '') === 'database' && empty($queue['connection'])) {
            try {
                $settings = config('database.connections.'.config('database.default'));
                $settings['options'][\PDO::ATTR_TIMEOUT] = 3;
                config(['database.connections.monitor_diagnostics' => $settings]);
                $db = DB::connection('monitor_diagnostics');
                $pending = $db->table($queue['table'] ?? 'jobs')->where('queue', $queue['queue'] ?? 'default')->count();
                $results['queue'] = ['status' => $pending >= 100 ? 'critical' : ($pending >= 25 ? 'warning' : 'ok'), 'value' => $pending];
                if (config('queue.failed.database') === config('database.default')) {
                    try {
                        $failed = $db->table(config('queue.failed.table', 'failed_jobs'))->where('failed_at', '>=', now()->subDay())->count();
                        $results['failed_jobs'] = ['status' => $failed ? 'warning' : 'ok', 'value' => $failed];
                    } catch (\Throwable $error) {}
                }
            } catch (\Throwable $error) {
                // Unknown does not imply an empty or healthy queue.
            } finally { DB::purge('monitor_diagnostics'); }
        }
        $results['errors_today'] = ['status' => 'unknown'];
        $count = 0; $found = false; $truncated = false;
        $logRoot = realpath(storage_path('logs'));
        foreach (['laravel.log', 'laravel-'.date('Y-m-d').'.log'] as $file) {
            $path = realpath(storage_path('logs/'.$file));
            if (!$logRoot || !$path || !str_starts_with($path, $logRoot.DIRECTORY_SEPARATOR) || !is_readable($path)) { continue; }
            $handle = @fopen($path, 'rb');
            if (!$handle) { continue; }
            $found = true;
            $size = fstat($handle)['size'];
            if ($size > 20 * 1024 * 1024) { $truncated = true; fseek($handle, -20 * 1024 * 1024, SEEK_END); fgets($handle); }
            while (($line = fgets($handle, 8192)) !== false) {
                if (preg_match('/^\['.preg_quote(date('Y-m-d'), '/').' [^\]]+\] \w+\.(ERROR|CRITICAL|ALERT|EMERGENCY):/', $line)) { $count++; }
            }
            fclose($handle);
        }
        if ($found) { $results['errors_today'] = ['status' => $count >= 50 ? 'critical' : ($count >= 10 ? 'warning' : ($truncated ? 'unknown' : 'ok')), 'value' => $count, 'partial' => $truncated]; }
        return response()->json(['checks' => $results])->header('Cache-Control', 'no-store');
    }

    public function mail(Request $request)
    {
        abort_unless(app()->environment('local') && in_array(
            $request->server('REMOTE_ADDR'), ['127.0.0.1', '::1'], true
        ), 404);

        $recipient = null;
        if ($request->isMethod('post')) {
            abort_unless($request->header('X-Monitor-Action') === 'manual', 403);
            $recipient = $request->validate(['email' => 'required|email:rfc|max:254'])['email'];
        }
        $settings = config('mail.mailers.'.config('mail.default'), []);
        $status = 'unknown';
        $summary = 'SMTP login is not configured';
        $transport = null;
        if (($settings['transport'] ?? null) === 'smtp' && !empty($settings['host'])
            && !empty($settings['username']) && !empty($settings['password']) && empty($settings['url'])) {
            try {
                // A dedicated transport with no logger, dispatcher, or send() call.
                $port = (int) ($settings['port'] ?? 587);
                $transport = new \Symfony\Component\Mailer\Transport\Smtp\EsmtpTransport(
                    $settings['host'], $port, ($settings['scheme'] ?? null) === 'smtps' || $port === 465
                );
                $transport->setRequireTls(true);
                $transport->getStream()->setTimeout(5);
                $transport->setUsername($settings['username']);
                $transport->setPassword($settings['password']);
                $transport->start();
                $status = 'ok';
                $summary = 'SMTP login successful';
                if ($recipient) {
                    $message = (new \Symfony\Component\Mime\Email())
                        ->from(config('mail.from.address'))->to($recipient)
                        ->subject('Server Monitor: manual mail test')
                        ->text('This is a manually requested test email from your local server monitor.');
                    $transport->send($message);
                    $summary = 'Test email accepted by SMTP server; inbox delivery is not confirmed';
                }
            } catch (\Throwable $error) {
                $status = 'critical';
                if ($error instanceof \Error || $error instanceof \ErrorException) {
                    $status = 'unknown';
                    $summary = 'Mail probe encountered an internal error; SMTP status unconfirmed';
                } else {
                    $summary = $this->safeFailure($error, 'mail');
                }
            } finally {
                if ($transport) {
                    try { $transport->stop(); } catch (\Throwable $error) {}
                }
            }
        }
        return response()->json(['status' => $status, 'summary' => $summary])
            ->header('Cache-Control', 'no-store');
    }

    public function show(Request $request)
    {
        // This first integration is intentionally available on localhost only.
        abort_unless(app()->environment('local') && in_array(
            $request->server('REMOTE_ADDR'), ['127.0.0.1', '::1'], true
        ), 404);

        $started = microtime(true);
        $checks = ['application' => 'ok', 'database' => 'fail'];
        $databaseDetails = 'Database connection successful';
        $databaseStarted = microtime(true);
        $databaseMs = null;
        try {
            $connection = config('database.connections.'.config('database.default'));
            $connection['options'][\PDO::ATTR_TIMEOUT] = 3;
            config(['database.connections.monitor_health' => $connection]);
            DB::connection('monitor_health')->select('SELECT 1');
            $checks['database'] = 'ok';
            $databaseMs = (int) round((microtime(true) - $databaseStarted) * 1000);
        } catch (\Throwable $error) {
            $databaseDetails = $this->safeFailure($error, 'database');
        } finally {
            DB::purge('monitor_health');
        }

        $healthy = $checks['database'] === 'ok';
        return response()->json([
            'status' => $healthy ? 'ok' : 'fail',
            'checks' => $checks,
            'database_details' => $databaseDetails,
            'database_duration_ms' => $databaseMs,
            'duration_ms' => (int) round((microtime(true) - $started) * 1000),
            'checked_at' => now()->toIso8601String(),
        ], $healthy ? 200 : 503)->header('Cache-Control', 'no-store');
    }
}
