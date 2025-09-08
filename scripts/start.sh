#!/usr/bin/env bash
set -e

echo "Extralit"
echo " Copyright: 2024-present Extralit Labs, Inc."
echo " License: GNU AGPLv3 - https://www.gnu.org/licenses/agpl-3.0.html"

# HF-Spaces OAuth helpers (if using HF OAUTH)
export OAUTH2_HUGGINGFACE_CLIENT_ID=$OAUTH_CLIENT_ID
export OAUTH2_HUGGINGFACE_CLIENT_SECRET=$OAUTH_CLIENT_SECRET
export OAUTH2_HUGGINGFACE_SCOPE=$OAUTH_SCOPES

# Default credentials
if [ -n "${SPACE_CREATOR_USER_ID}" ]; then
  DEFAULT_USERNAME=$(curl -s https://huggingface.co/api/users/${SPACE_CREATOR_USER_ID}/overview \
    | jq -r '.user' 2>/dev/null || echo "${SPACE_AUTHOR_NAME}")
else
  DEFAULT_USERNAME="${SPACE_AUTHOR_NAME}"
fi
export USERNAME="${USERNAME:-$DEFAULT_USERNAME}"
export PASSWORD="${PASSWORD:-$(pwgen -s 16 1)}"

# Start Elasticsearch, Redis, Extralit & extraction processes
honcho start
