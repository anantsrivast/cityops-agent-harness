#!/bin/bash
set -e

echo "[1/3] Installing cityops_harness + dev deps..."
pip install -q --no-cache-dir -e ".[dev]"
python -m ipykernel install --user --name harness --display-name "CityOps Harness"

echo "[2/3] Unpacking Oracle wallet from WALLET_B64 secret (if set)..."
if [ -n "${WALLET_B64:-}" ] && [ ! -f wallet/tnsnames.ora ]; then
  mkdir -p wallet
  echo "$WALLET_B64" | base64 -d > /tmp/wallet.zip
  python -m zipfile -e /tmp/wallet.zip wallet/
  rm /tmp/wallet.zip
  echo "  wallet/ unpacked."
elif [ -f wallet/tnsnames.ora ]; then
  echo "  wallet/ already present."
else
  echo "  WALLET_B64 not set - add it as a Codespaces secret, or copy wallet/ manually."
fi

echo "[3/3] Seeding .env from .env.example (if absent)..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env created - fill in DB_PASSWORD / WALLET_PASSWORD / API keys."
fi

echo "Done. Open notebooks/00_setup.ipynb to verify the environment."
