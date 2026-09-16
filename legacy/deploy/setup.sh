#!/usr/bin/env bash
set -euo pipefail

# Alpha trading bot -- Linux VM setup. Run from anywhere; it locates the project
# root itself. Run this WITHOUT sudo -- it only asks for your password (via sudo)
# for the two systemd steps at the end, not for the venv/pip install.
#
# What this does:
#   1. Creates a Python venv (.venv) and installs requirements.txt into it
#   2. Copies .env.example to .env if you don't already have one (you still need
#      to edit it with real credentials -- this script never fills in secrets)
#   3. Installs deploy/alpha.service into systemd, pointed at THIS directory and
#      running as the current user
#   4. Enables the service (auto-starts on every VM boot) but does NOT start it --
#      review .env and config.yaml first, then start it yourself.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
echo "Project directory: $PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating venv..."
    python3 -m venv .venv
fi

echo "Installing requirements..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

if [ ! -f ".env" ]; then
    echo "No .env found -- copying .env.example."
    cp .env.example .env
    echo "*** YOU MUST EDIT $PROJECT_DIR/.env with real credentials before starting the service. ***"
fi

echo "Installing systemd service (will prompt for sudo password)..."
sed -e "s|/opt/alpha|$PROJECT_DIR|g" -e "s|^User=alpha|User=$(whoami)|" \
    deploy/alpha.service | sudo tee /etc/systemd/system/alpha.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable alpha

cat <<EOF

Setup complete. Before starting the bot:
  1. Edit $PROJECT_DIR/.env with your real Angel One credentials
  2. Review $PROJECT_DIR/config.yaml -- especially paper_trading, risk limits,
     and the current holiday_list_<year> block
  3. sudo systemctl start alpha
  4. sudo journalctl -u alpha -f      # watch it live
  5. sudo systemctl status alpha      # check it's running

The service is already enabled, so it will auto-start on every future VM boot
without needing any of these steps again.
EOF
