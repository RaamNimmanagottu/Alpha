# Deploying to a Linux VM

Runs continuously as a `systemd` service — the standard way to run a long-lived
process on Linux: it survives your SSH session ending, auto-restarts itself on a
genuine crash (but not on the bot's own normal daily exit), and can auto-start when
the VM boots. This has been reviewed carefully but **not run on an actual Linux
box** — this project was developed on Windows. Test it on your VM and report back
anything that doesn't match.

## First-time setup

```bash
git clone <your repo, or copy the project> /opt/alpha   # or wherever you like
cd /opt/alpha
chmod +x deploy/setup.sh
./deploy/setup.sh
```

`setup.sh` creates the venv, installs `requirements.txt`, copies `.env.example` to
`.env` if you don't have one, and installs+enables the systemd service (asks for
your `sudo` password only for that last part).

Then, before starting it:

1. Edit `.env` with your real Angel One credentials (`ANGEL_API_KEY`,
   `ANGEL_CLIENT_ID`, `ANGEL_MPIN`, `ANGEL_TOTP_SECRET`).
2. Review `config.yaml` — `paper_trading` should stay `true` until you've reviewed
   at least a few weeks of paper results; also double-check `holiday_list_<year>`
   is current for this year.
3. `sudo systemctl start alpha`

## Day to day

```bash
sudo systemctl status alpha      # is it running?
sudo journalctl -u alpha -f      # live log tail
sudo systemctl restart alpha     # after a config.yaml or .env change
sudo systemctl stop alpha        # stop it
```

Because the service is `enabled`, it restarts automatically every time the VM
boots — no manual step needed once this initial setup is done. `Restart=on-failure`
in `deploy/alpha.service` means it will NOT restart-loop just because the bot
exited normally (holiday, weekend, market closed) — only on a genuine crash.

## What this doesn't do yet

VM power on/off scheduling (starting the VM at 9 AM, stopping it after a holiday
or market close for cost savings) is a separate, cloud-provider-specific piece that
hasn't been built — it depends on which platform (AWS/Azure/GCP) you end up using.
This systemd setup only covers "once the VM is running, the bot starts itself and
stays running correctly" — it assumes something else (you, manually, for now)
starts and stops the VM itself.
