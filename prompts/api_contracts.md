API principles:
- Provide `/state` for current snapshot.
- Provide `/telemetry` later for timeseries.
- Keep commands idempotent where possible.
- Validate ranges (0..1 for power/valve, sensible bounds for temps).
