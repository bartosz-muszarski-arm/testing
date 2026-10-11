#!/usr/bin/env bash
# Normalize a public GitHub URL that contains a branch or commit.
set -euo pipefail

usage() {
    printf 'Usage: %s --repository <GitHub /tree/ref or /commit/SHA URL>\n' "$0" >&2
}

repository=''
while (($#)); do
    case "$1" in
        --repository) repository=${2:?missing value for --repository}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
    esac
done

[[ -n $repository ]] || { printf '%s\n' '--repository is required' >&2; exit 2; }
if [[ ! $repository =~ ^https://github\.com/([^/]+)/([^/]+)/(tree|commit)/(.+)$ ]]; then
    printf '%s\n' 'Repository must be a GitHub /tree/<branch> or /commit/<SHA> URL' >&2
    exit 2
fi

owner=${BASH_REMATCH[1]}
repo=${BASH_REMATCH[2]}
ref=${BASH_REMATCH[4]}
[[ $owner =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ && $repo =~ ^[A-Za-z0-9_.-]+$ ]] || {
    printf 'Invalid GitHub owner or repository name: %s/%s\n' "$owner" "$repo" >&2
    exit 2
}
[[ $ref != -* && $ref != *$'\n'* && $ref != *$'\r'* && $ref != *' '* ]] || {
    printf 'Invalid ref: %s\n' "$ref" >&2
    exit 2
}

printf '%s\t%s\n' "$owner/$repo" "$ref"
