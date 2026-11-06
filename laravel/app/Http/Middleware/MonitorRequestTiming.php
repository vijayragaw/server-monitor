<?php

namespace App\Http\Middleware;

use Closure;

class MonitorRequestTiming
{
    public function handle($request, Closure $next)
    {
        if (!app()->environment('local') || !config('monitor.request_timing', true) || $request->is('api/health', 'api/health/*')) {
            return $next($request);
        }
        $start = microtime(true);
        $status = 500;
        try {
            $response = $next($request);
            $status = $response->getStatusCode();
            return $response;
        } catch (\Throwable $error) {
            if ($error instanceof \Symfony\Component\HttpKernel\Exception\HttpExceptionInterface) {
                $status = $error->getStatusCode();
            } elseif ($error instanceof \Illuminate\Validation\ValidationException) {
                $status = 422;
            } elseif ($error instanceof \Illuminate\Auth\AuthenticationException) {
                $status = 401;
            }
            throw $error;
        } finally {
            // Observational only: never include input, query parameters, users or IPs.
            try {
                // Retain only today and yesterday for this monitor-owned source.
                $root = realpath(storage_path('logs'));
                foreach (glob(storage_path('logs/monitor-requests-*.jsonl')) ?: [] as $old) {
                    if (!is_link($old) && dirname(realpath($old) ?: '') === $root
                        && preg_match('/^monitor-requests-(\d{4}-\d{2}-\d{2})\.jsonl$/', basename($old), $match)
                        && $match[1] < date('Y-m-d', strtotime('-1 day'))) {
                        @unlink($old);
                    }
                }
                $route = $request->route();
                $record = ['at' => date('c'), 'time' => microtime(true), 'method' => $request->method(),
                    'route' => $route ? $route->uri() : '[unmatched]', 'status' => $status,
                    'duration_ms' => round((microtime(true) - $start) * 1000, 1)];
                $file = @fopen(storage_path('logs/monitor-requests-'.date('Y-m-d').'.jsonl'), 'ab');
                if ($file) {
                    if (flock($file, LOCK_EX)) {
                        if (fstat($file)['size'] < 10 * 1024 * 1024) {
                            fwrite($file, json_encode($record)."\n");
                        }
                        flock($file, LOCK_UN);
                    }
                    fclose($file);
                }
            } catch (\Throwable $ignored) {}
        }
    }
}
