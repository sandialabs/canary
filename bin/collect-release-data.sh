#!/usr/bin/env bash
# collect_release_data.sh
#
# Usage:
#   ./collect_release_data.sh <old-ref> <new-ref> > release_data.txt
#
# Example:
#   ./collect_release_data.sh v2025.05.01 v2025.06.12 > canary_2025.06.12_release_data.txt
#
# Notes:
# - Only uses local git history (no GitHub API).
# - Output is structured so it can be parsed deterministically.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <old-ref> <new-ref> > release_data.txt" >&2
  exit 2
fi

OLD_REF="$1"
NEW_REF="$2"
RANGE="${OLD_REF}..${NEW_REF}"

# Ensure refs exist
git rev-parse --verify -q "${OLD_REF}^{commit}" >/dev/null
git rev-parse --verify -q "${NEW_REF}^{commit}" >/dev/null

repo_url() {
  # Try to convert common GitHub remotes into https://github.com/OWNER/REPO
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"

  if [[ -z "$url" ]]; then
    return 0
  fi

  # git@github.com:OWNER/REPO(.git)
  if [[ "$url" =~ ^git@github\.com:(.+)$ ]]; then
    url="https://github.com/${BASH_REMATCH[1]}"
  fi

  # ssh://git@github.com/OWNER/REPO(.git)
  if [[ "$url" =~ ^ssh://git@github\.com/(.+)$ ]]; then
    url="https://github.com/${BASH_REMATCH[1]}"
  fi

  # https://github.com/OWNER/REPO(.git)
  if [[ "$url" =~ ^https://github\.com/(.+)$ ]]; then
    url="https://github.com/${BASH_REMATCH[1]}"
  fi

  url="${url%.git}"
  echo "$url"
}

echo "=== RELEASE_DATA_V1 ==="
echo "generated_utc=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "repo_root=$(git rev-parse --show-toplevel)"
echo "repo_url=$(repo_url)"
echo "old_ref=${OLD_REF}"
echo "new_ref=${NEW_REF}"
echo "range=${RANGE}"
echo

echo "=== SUMMARY ==="
echo "commit_count=$(git rev-list --count "${RANGE}")"
echo "author_count=$(git shortlog -sne "${RANGE}" | wc -l | tr -d ' ')"
echo

echo "=== AUTHORS_SHORTLOG ==="
# Format: "<count>\t<name> <email>"
git shortlog -sne "${RANGE}"
echo

echo "=== COMMITS_PARSEABLE ==="
# Each commit is 6 lines, key=value pairs, terminated by a blank line:
# commit=<sha>
# date=<YYYY-MM-DD>
# author_name=...
# author_email=...
# subject=...
# body_b64=...   (base64 of raw body; safe for parsing)
git log "${RANGE}" --date=short --no-decorate --pretty=format:$'commit=%H\ndate=%ad\nauthor_name=%an\nauthor_email=%ae\nsubject=%s\nbody_b64=%b%n--ENDCOMMIT--' \
  | while IFS= read -r line; do
      if [[ "$line" == "--ENDCOMMIT--" ]]; then
        echo
      elif [[ "$line" == body_b64=* ]]; then
        # Encode everything after "body_b64=" in base64 (may be empty)
        body="${line#body_b64=}"
        printf 'body_b64=%s\n' "$(printf '%s' "$body" | base64 | tr -d '\n')"
      else
        printf '%s\n' "$line"
      fi
    done
echo

echo "=== REFERENCES ==="
# Extract likely GitHub references from subject+body:
# - PR references: "#123" (GitHub PRs and Issues share the same number space)
# - Alternate PR style: "PR #123" or "pull request #123"
# Output: unique sorted numbers only.
git log "${RANGE}" --pretty=format:'%s%n%b' \
  | grep -Eoi '(pull request[[:space:]]*#[0-9]+|pr[[:space:]]*#[0-9]+|#[0-9]+)' \
  | grep -Eo '#[0-9]+' \
  | tr -d '#' \
  | sort -n -u \
  | awk '{print "ref=" $0}'
echo

echo "=== MERGE_COMMITS_ONLY ==="
# Useful if you do merge commits instead of squash.
git log "${RANGE}" --merges --date=short --no-decorate \
  --pretty=format:$'merge_commit=%H\ndate=%ad\nauthor_name=%an\nsubject=%s\n\n'
echo
