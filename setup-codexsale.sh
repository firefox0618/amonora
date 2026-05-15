#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-gpt-5.4}"
BASE_URL="https://codex.sale/v1"

read -s -p "Вставь API ключ CodexSale: " API_KEY
echo ""

CODEX_HOME="$HOME/.codex"
CONFIG_FILE="$CODEX_HOME/config.toml"
BACKUP_FILE="$CODEX_HOME/config.toml.bak"

mkdir -p "$CODEX_HOME"

if [ -f "$CONFIG_FILE" ]; then
  cp "$CONFIG_FILE" "$BACKUP_FILE"
  echo "Бэкап создан: $BACKUP_FILE"
fi

cat > "$CONFIG_FILE" <<EOF
model = "$MODEL"
model_provider = "openai"
openai_base_url = "$BASE_URL"
EOF

if [ -f "$HOME/.bashrc" ]; then
  grep -q "OPENAI_API_KEY" "$HOME/.bashrc" || echo "export OPENAI_API_KEY=\"$API_KEY\"" >> "$HOME/.bashrc"
fi

export OPENAI_API_KEY="$API_KEY"

echo ""
echo "Готово."
echo "Конфиг Codex:"
cat "$CONFIG_FILE"
echo ""
echo "Теперь выполни:"
echo "source ~/.bashrc"
echo "codex"
