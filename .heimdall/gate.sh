#!/usr/bin/env bash
# gate.sh — Heimdall's publish gate. STANDALONE (no lib dependency) so the vendored copy at
# <repo>/.heimdall/gate.sh runs identically here, in the CLI, and in CI. Run from a repo root.
#
# Usage: gate.sh [--full]
#   --full   also scan full git history (use at first publish / graduation)
#
# ALWAYS enforces leak prevention (secret scan + infra-identifier scrub). License and project
# checks run only if declared in .heimdall.toml. The infra denylist comes from $HEIMDALL_DENYLIST
# or ~/.config/heimdall/config (INFRA_DENYLIST); if neither is available the scrub fails closed.
set -uo pipefail

full=0; [ "${1:-}" = "--full" ] && full=1
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "gate: not inside a git repo" >&2; exit 2; }
cd "$ROOT"
MAN=".heimdall.toml"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
section(){ printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
pass(){ printf '  \033[0;32mPASS\033[0m %s\n' "$*"; }
bad(){ printf '  \033[0;31mFAIL\033[0m %s\n' "$*"; fail=1; }
note(){ printf '       %s\n' "$*"; }

# Minimal TOML reader (scalars/bool plain, arrays newline-joined). Needs python3.
tget(){ # key default
  python3 - "$MAN" "$1" "${2-}" <<'PY' 2>/dev/null || printf '%s' "${2-}"
import sys,tomllib
try: d=tomllib.load(open(sys.argv[1],'rb'))
except Exception: print(sys.argv[3]); sys.exit(0)
cur=d
for p in sys.argv[2].split('.'):
  if isinstance(cur,dict) and p in cur: cur=cur[p]
  else: print(sys.argv[3]); sys.exit(0)
print("\n".join(map(str,cur)) if isinstance(cur,list) else ("true" if cur is True else "false" if cur is False else cur))
PY
}

echo "heimdall gate — $(basename "$ROOT")  $([ $full = 1 ] && echo '(full history)' || echo '(working tree)')"

# ---- 1. secret scan (always) --------------------------------------------------------------
section "secret scan"
scanner="$(tget gate.secret_scan gitleaks)"
if [ "$scanner" = gitleaks ] && command -v gitleaks >/dev/null 2>&1; then
  cfg=(); [ -f .gitleaks.toml ] && cfg=(--config .gitleaks.toml)
  if [ $full = 1 ]; then
    gitleaks detect --no-banner --redact "${cfg[@]}" --source . >"$TMP/gl" 2>&1 \
      && pass "gitleaks clean (full history)" || { bad "gitleaks found secrets"; sed 's/^/    /' "$TMP/gl"; }
  else
    gitleaks detect --no-banner --redact "${cfg[@]}" --source . --no-git >"$TMP/gl" 2>&1 \
      && pass "gitleaks clean (working tree)" || { bad "gitleaks found secrets"; sed 's/^/    /' "$TMP/gl"; }
  fi
else
  [ "$scanner" = gitleaks ] && note "(gitleaks not installed — using built-in grep fallback)"
  # High-signal patterns only (a fallback must not block on every 'password =' in prose).
  pat='(gh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[0-9A-Za-z-]{10,}|(FORGEJO_TOKEN|GITHUB_TOKEN|GITLAB_TOKEN)[[:space:]]*[=:][[:space:]]*['"'"'"]?[0-9A-Za-z_-]{20,})'
  if git grep -nIE "$pat" -- . >"$TMP/gl" 2>/dev/null; then
    bad "possible secrets (grep fallback):"; sed 's/^/    /' "$TMP/gl"
  else pass "no obvious secrets (grep fallback)"; fi
fi

# ---- 2. infra-identifier scrub (always, unless explicitly skipped) ------------------------
# The denylist contains internal identifiers, so it lives only on the internal side. Public CI
# sets HEIMDALL_SKIP_INFRA=1 (the internal gate catches anything before importing community work).
section "infra-identifier scrub"
if [ -n "${HEIMDALL_SKIP_INFRA:-}" ]; then
  note "skipped (HEIMDALL_SKIP_INFRA set — infra scrub runs on the internal side)"
  DENY="__skip__"
else
  DENY="${HEIMDALL_DENYLIST:-}"
  if [ -z "$DENY" ] && [ -f "$HOME/.config/heimdall/config" ]; then
    DENY="$( set +u; . "$HOME/.config/heimdall/config" >/dev/null 2>&1; printf '%s' "${INFRA_DENYLIST:-}" )"
  fi
fi
if [ "$DENY" = "__skip__" ]; then
  :
elif [ -z "$DENY" ]; then
  bad "no denylist (set \$HEIMDALL_DENYLIST or ~/.config/heimdall/config) — refusing to certify clean"
else
  re=""
  for t in $DENY; do
    if printf '%s' "$t" | grep -qE '^[0-9]+$'; then e="\\b${t}\\b"
    else e="$(printf '%s' "$t" | sed 's/[].[\*^$()+?{|]/\\&/g')"; fi
    re="${re:+$re|}$e"
  done
  if git grep -nIE "($re)" -- . >"$TMP/dl" 2>/dev/null; then
    bad "internal identifiers in tracked files:"; sed 's/^/    /' "$TMP/dl"
  else pass "no internal identifiers in working tree"; fi
  if [ $full = 1 ]; then
    hist=0
    for t in $DENY; do
      git log -S"$t" --oneline -- . 2>/dev/null | grep -q . && { note "history contains: $t"; hist=1; }
    done
    [ $hist = 1 ] && bad "internal identifiers in git history (use history=snapshot, or scrub+graduate)" \
                  || pass "no internal identifiers in history"
  fi
fi

# ---- 3. license (only if required) --------------------------------------------------------
if [ "$(tget gate.require_license false)" = true ]; then
  section "license"
  lic="$(ls LICENSE LICENSE.* COPYING 2>/dev/null | head -1 || true)"
  if [ -z "$lic" ]; then bad "require_license is set but no LICENSE file exists (add your own)"
  else
    want="$(tget gate.license "")"
    if [ -n "$want" ] && ! grep -qiF "$want" "$lic"; then
      bad "LICENSE does not appear to match declared SPDX '$want' (file: $lic)"
    else pass "LICENSE present${want:+ (matches $want)}"; fi
  fi
fi

# ---- 4. project checks (only if declared) -------------------------------------------------
checks="$(tget gate.checks "")"
if [ -n "$checks" ]; then
  section "project checks"
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    printf '  $ %s\n' "$c"
    if bash -c "$c" >"$TMP/ck" 2>&1; then pass "$c"; else bad "$c"; sed 's/^/      /' "$TMP/ck" | tail -20; fi
  done <<<"$checks"
fi

echo
if [ $fail = 0 ]; then printf '\033[0;32mheimdall-gate: PASS\033[0m\n'; exit 0
else printf '\033[0;31mheimdall-gate: FAIL\033[0m\n'; exit 1; fi
