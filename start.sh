#!/usr/bin/env sh

set -eu

mkdir -p /app/.streamlit

# No Railway, o conteúdo do secrets.toml ficará em uma variável protegida.
if [ -n "${STREAMLIT_SECRETS_TOML:-}" ]; then
    umask 077
    printf '%s\n' "$STREAMLIT_SECRETS_TOML" \
        > /app/.streamlit/secrets.toml
fi

exec streamlit run app.py \
    --server.address=0.0.0.0 \
    --server.port="${PORT:-8501}" \
    --server.headless=true \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false
