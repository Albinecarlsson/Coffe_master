# Running on the Raspberry Pi

The service is a thin wrapper around `uvicorn espresso_mod.main:app`. It is not
required for development: `HARDWARE_MODE=sim` runs on any machine.

## Install

1. Clone the repo to `/home/pi/Coffe_master` (or edit the paths in
   `deploy/coffee-master.service`).

2. Create the virtualenv and install the hardware extras:

   ```bash
   cd /home/pi/Coffe_master
   python3 -m venv .venv
   .venv/bin/pip install -e ".[hardware]"
   ```

3. Create `.env` from `.env.example`. Leave `HARDWARE_MODE=sim` until the machine
   is wired; set `HARDWARE_MODE=rtd` when it is, and keep `PRESSURE_ENABLED=false`
   until the sender is fitted (enabling it with no I2C bus fails the boot loudly,
   on purpose).

4. Give the service user access to the devices. Group names differ between Pi OS
   releases, so check the device nodes first:

   ```bash
   ls -l /dev/gpiomem /dev/i2c-1 /dev/spidev0.0
   sudo usermod -aG gpio,i2c,spi pi   # use the groups the nodes actually show
   ```

   The user must re-login (or the service be restarted) for the groups to apply.

5. Install and start the unit:

   ```bash
   sudo cp deploy/coffee-master.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now coffee-master
   ```

   Logs: `journalctl -u coffee-master -f`.

## Health

`GET /health` answers 200 when the machine is healthy and 503 when it is not.
Healthy means the control thread is alive, it is not reporting a fault and the
temperature sensor reads; a missing pressure sender is never unhealthy. The
runtime (control loop, telemetry, history) is created at application startup, so
the boiler is controlled from boot rather than from behind the first request, and
`uptime_s` is the lifetime of that runtime. A hardware configuration error — an
unknown `HARDWARE_MODE`, or `PRESSURE_ENABLED=true` with no I2C bus — fails the
service at startup, which systemd surfaces in the journal and then restarts.

```bash
curl -fsS http://127.0.0.1:8000/health   # -f exits non-zero on 503
```

Use it for readiness (is the API up and controlling?) from a monitor. It is not a
systemd watchdog: the app does not send `sd_notify`, so `WatchdogSec` is not
available. `Restart=on-failure` already covers a crash. To poll on the machine
itself, a timer is enough:

```ini
# /etc/systemd/system/coffee-health.service
[Service]
Type=oneshot
ExecStart=/usr/bin/curl -fsS --max-time 5 http://127.0.0.1:8000/health
```

```ini
# /etc/systemd/system/coffee-health.timer
[Unit]
Description=Poll the espresso controller health endpoint

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
```

A failed oneshot unit is visible in `systemctl --failed` and the journal.
