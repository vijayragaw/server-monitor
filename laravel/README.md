# Laravel Server Monitor integration

These files come from the Billing Laravel integration at commit 740805b. Copy the
app/ and config/ files into the matching directories in the Laravel project.

Paste the contents of routes/api-monitor.snippet.txt into the existing
routes/api.php after its imports, outside any existing route group. The snippet
uses Billing's controller namespace convention and its middleware classes.
Adapt those references if your Laravel project uses different registrations.

To record request timings, add this line to the API middleware group in
app/Http/Kernel.php alongside the existing middleware:

    \App\Http\Middleware\MonitorRequestTiming::class,

The controller restricts these routes to loopback requests in Laravel's local
environment. Keep those restrictions in place. Direct SSH monitoring can
collect supported diagnostics without installing these Laravel routes.

Check registration from the Laravel project directory:

    php artisan route:list --path=api/health
