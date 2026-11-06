<?php

return [
    // Local development only; route templates and timings, never payloads.
    'request_timing' => env('MONITOR_REQUEST_TIMING', true),
];
