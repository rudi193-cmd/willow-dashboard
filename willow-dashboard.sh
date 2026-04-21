#!/usr/bin/env bash
# willow-dashboard.sh — Launch the Willow terminal dashboard.
# b17: WDASH  ΔΣ=42
#
# Usage:
#   ./willow-dashboard.sh             — normal launch (boot + dashboard)
#   ./willow-dashboard.sh --dev       — skip boot sequence
#   ./willow-dashboard.sh --agent X   — run as agent X
#   ./willow-dashboard.sh --setup     — force re-run onboarding

set -euo pipefail

DASH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Find willow-1.7 root ──────────────────────────────────────────────────────
# Check: env override → sibling directory → common locations
if [[ -n "${WILLOW_ROOT:-}" ]] && [[ -f "${WILLOW_ROOT}/willow.sh" ]]; then
    : # already set
elif [[ -f "${DASH_ROOT}/../willow-1.7/willow.sh" ]]; then
    WILLOW_ROOT="$(cd "${DASH_ROOT}/../willow-1.7" && pwd)"
elif [[ -f "${HOME}/github/willow-1.7/willow.sh" ]]; then
    WILLOW_ROOT="${HOME}/github/willow-1.7"
else
    WILLOW_ROOT=""
fi
export WILLOW_ROOT

# ── Python — willow venv if available ────────────────────────────────────────
if [[ -z "${WILLOW_PYTHON:-}" ]]; then
    if [[ -x "${HOME}/.willow-venv/bin/python3" ]]; then
        WILLOW_PYTHON="${HOME}/.willow-venv/bin/python3"
    elif [[ -x "${DASH_ROOT}/.venv/bin/python3" ]]; then
        WILLOW_PYTHON="${DASH_ROOT}/.venv/bin/python3"
    else
        WILLOW_PYTHON="$(command -v python3)"
    fi
fi
export WILLOW_PYTHON

# ── Core environment ──────────────────────────────────────────────────────────
# Inherit from willow.sh defaults where available, apply dashboard overrides.

export WILLOW_STORE_ROOT="${WILLOW_STORE_ROOT:-${HOME}/.willow/store}"
export WILLOW_SAFE_ROOT="${WILLOW_SAFE_ROOT:-${HOME}/SAFE/Applications}"
export WILLOW_PG_DB="${WILLOW_PG_DB:-willow}"
export WILLOW_PG_USER="${WILLOW_PG_USER:-$(whoami)}"
export WILLOW_AGENT_NAME="${WILLOW_AGENT_NAME:-heimdallr}"

# Postgres — Unix socket only (no TCP vars)
unset WILLOW_PG_HOST WILLOW_PG_PORT WILLOW_PG_PASS 2>/dev/null || true

# SAP fingerprint — boot.py will populate this if set in boot config
if [[ -f "${HOME}/.willow/willow-dashboard-boot.json" ]]; then
    _fp="$(python3 -c "
import json,sys
try:
    d=json.loads(open('${HOME}/.willow/willow-dashboard-boot.json').read())
    print(d.get('pgp_fingerprint',''))
except:
    print('')
" 2>/dev/null || echo "")"
    if [[ -n "$_fp" ]]; then
        export WILLOW_PGP_FINGERPRINT="$_fp"
        export SAP_PGP_FINGERPRINT="$_fp"
    fi
fi

# ── Load .env if present ──────────────────────────────────────────────────────
for _env_file in "${DASH_ROOT}/.env" "${WILLOW_ROOT}/.env"; do
    if [[ -f "${_env_file}" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "${_env_file}"
        set +a
        break
    fi
done

# ── Parse arguments ───────────────────────────────────────────────────────────
DASH_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --dev)      DASH_ARGS+=("--skip-boot") ;;
        --agent)    shift; export WILLOW_AGENT_NAME="$1" ;;
        --agent=*)  export WILLOW_AGENT_NAME="${arg#--agent=}" ;;
        --setup)    DASH_ARGS+=("--force-setup") ;;
        *)          DASH_ARGS+=("$arg") ;;
    esac
done

# ── Launch ────────────────────────────────────────────────────────────────────
cd "${DASH_ROOT}"
exec "${WILLOW_PYTHON}" dashboard.py "${DASH_ARGS[@]+"${DASH_ARGS[@]}"}"
