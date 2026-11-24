#!/bin/sh
# carl -- a curl-like client for a canary request server (the file binding).
#
# Installed by `canary server start` as <workspace>/.canary/share/carl.  It needs nothing
# but a POSIX shell: it writes the request into the server's inbox, waits for the result
# and prints it, as curl prints a response.  URLs have the shape the HTTP binding will
# have, with the workspace's directory where a host would be.
#
# Copyright NTESS. See COPYRIGHT file for details.
# SPDX-License-Identifier: MIT

set -u

usage() {
    cat >&2 <<'EOF'
usage: carl [options] METHOD file:///path/to/workspace[/ROUTE] [options]

  POST|PUT .../canary/ENDPOINT     submit a request (body: -d), wait, print its result
  POST|PUT .../                    submit a whole envelope given with -d
  GET      .../requests/ID         print a request's result, or its status if unfinished
  GET      .../server              print server.json
  POST     .../requests/ID/cancel  cancel a request

options:
  -d, --data DATA          request body (JSON); @FILE reads FILE, @- reads stdin
  -H, --header HEADER      'Idempotency-Key: ID' sets the request id (default: generated)
  -o, --output FILE        write the result to FILE instead of stdout
  -s, --silent             no progress messages
  -f, --fail               exit 22 if the result's status_code is 400 or more
  -m, --max-time SECONDS   stop waiting after SECONDS (exit 28; the request goes on)
      --cwd DIR            working directory, relative to the workspace (default: .)
      --env NAME=VALUE     set a variable for the request (repeatable)
  -h, --help               this message

Ctrl-C while waiting cancels the request.  Exit codes follow curl: 0 a result arrived,
2 bad usage, 6 no workspace at the URL, 7 no server running, 22 (-f) an error result,
28 timed out; 130 cancelled.
EOF
}

fail() { code=$1; shift; echo "carl: $*" >&2; exit "$code"; }
note() { [ "$silent" = 1 ] || echo "carl: $*" >&2; }
json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
nap() { sleep 0.2 2>/dev/null || sleep 1; }

method="" url="" data="" have_data=0 id="" output="" silent=0 failon=0 maxtime=""
cwd="." envjson=""

while [ $# -gt 0 ]; do
    case $1 in
        -d|--data|--data-raw|--data-binary) [ $# -ge 2 ] || fail 2 "$1 needs a value"; data=$2; have_data=1; shift 2 ;;
        -H|--header) [ $# -ge 2 ] || fail 2 "$1 needs a value"
            case $2 in
                [Ii]dempotency-[Kk]ey:*) id=$(printf '%s' "${2#*:}" | sed 's/^ *//; s/ *$//') ;;
                *) fail 2 "unsupported header: $2 (only Idempotency-Key)" ;;
            esac
            shift 2 ;;
        -o|--output) [ $# -ge 2 ] || fail 2 "$1 needs a value"; output=$2; shift 2 ;;
        -s|--silent) silent=1; shift ;;
        -f|--fail) failon=1; shift ;;
        -m|--max-time) [ $# -ge 2 ] || fail 2 "$1 needs a value"; maxtime=$2; shift 2 ;;
        --cwd) [ $# -ge 2 ] || fail 2 "$1 needs a value"; cwd=$2; shift 2 ;;
        --env) [ $# -ge 2 ] || fail 2 "$1 needs a value"
            case $2 in *=*) ;; *) fail 2 "--env wants NAME=VALUE, not $2" ;; esac
            pair="$(json_str "${2%%=*}"): $(json_str "${2#*=}")"
            envjson="${envjson:+$envjson, }$pair"; shift 2 ;;
        -X|--request) [ $# -ge 2 ] || fail 2 "$1 needs a value"; method=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        -*) fail 2 "unknown option: $1 (see carl --help)" ;;
        *) if [ -z "$method" ]; then method=$1; elif [ -z "$url" ]; then url=$1
           else fail 2 "unexpected argument: $1"; fi; shift ;;
    esac
done

[ -n "$method" ] && [ -n "$url" ] || { usage; exit 2; }
method=$(printf '%s' "$method" | tr '[:lower:]' '[:upper:]')
case $method in GET|POST|PUT) ;; *) fail 2 "unsupported method: $method" ;; esac
case $url in file://*) path=${url#file://} ;; *) fail 2 "only file:// URLs are supported: $url" ;; esac
case $path in /*) ;; *) fail 2 "the URL needs an absolute path: $url" ;; esac
[ -z "$maxtime" ] || case $maxtime in *[!0-9]*) fail 2 "--max-time wants whole seconds" ;; esac

# The workspace is the longest prefix of the path holding .canary; the rest is the route.
while [ "${path%/}" != "$path" ] && [ "$path" != / ]; do path=${path%/}; done
anchor=$path route=""
until [ -d "$anchor/.canary" ]; do
    [ "$anchor" = / ] && fail 6 "no canary workspace in $url"
    route="/${anchor##*/}$route"
    anchor=${anchor%/*}; [ -n "$anchor" ] || anchor=/
done
S="$anchor/.canary/var/server"

[ -f "$S/server.json" ] || fail 7 "no canary server is running for $anchor (canary server start)"

emit() {  # FILE: the response
    if [ -n "$output" ]; then cat "$1" > "$output"; else cat "$1"; fi
}
status_code() { sed -n 's/.*"status_code": *\([0-9][0-9]*\).*/\1/p' "$1" | head -n 1; }

case $method:$route in
    GET:/server) emit "$S/server.json"; exit 0 ;;
    GET:/requests/*/*|GET:/requests/) fail 2 "GET /requests/ID wants just an id" ;;
    GET:/requests/*)
        rid=${route#/requests/}; d="$S/requests/$rid"
        if [ -f "$d/result.json" ]; then emit "$d/result.json"
        elif [ -f "$d/status.json" ]; then emit "$d/status.json"
        else fail 22 "no request $rid"; fi
        exit 0 ;;
    POST:/requests/*/cancel|PUT:/requests/*/cancel)
        rid=${route#/requests/}; rid=${rid%/cancel}; d="$S/requests/$rid"
        [ -d "$d" ] || fail 22 "no request $rid"
        touch "$d/cancel"; note "asked to cancel $rid"
        [ -f "$d/status.json" ] && emit "$d/status.json"
        exit 0 ;;
    GET:*) fail 2 "GET works on /server and /requests/ID; submit with POST" ;;
esac

# Submit.
if [ "$have_data" = 1 ]; then
    case $data in
        @-) data=$(cat) ;;
        @*) [ -r "${data#@}" ] || fail 2 "cannot read ${data#@}"; data=$(cat "${data#@}") ;;
    esac
fi
case $(printf '%s' "$data" | tr -d ' \t\n\r' | cut -c1) in
    ''|'{') ;;
    *) fail 2 "the body must be a JSON object" ;;
esac
if [ -n "$route" ]; then
    [ -n "$data" ] || data='{}'
    envelope="{\"version\": 1, \"path\": $(json_str "$route"), \"request\": $data, \"cwd\": $(json_str "$cwd"), \"env\": {$envjson}}"
else
    [ -n "$data" ] || fail 2 "POST to the workspace itself needs the whole envelope with -d"
    [ "$cwd" = . ] && [ -z "$envjson" ] || fail 2 "--cwd/--env go with a route in the URL"
    envelope=$data
fi

[ -n "$id" ] || id="carl-$(date +%Y%m%dT%H%M%S)-$$"
printf '%s' "$id" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' || fail 2 "invalid request id: $id"
[ ! -e "$S/requests/$id" ] || fail 2 "request $id already exists"

printf '%s\n' "$envelope" > "$S/inbox/$id.json.tmp" && mv "$S/inbox/$id.json.tmp" "$S/inbox/$id.json" \
    || fail 7 "cannot write to $S/inbox"
note "submitted $id"

cancelled=0
on_interrupt() {
    if [ "$cancelled" = 1 ]; then exit 130; fi
    cancelled=1
    if [ -d "$S/requests/$id" ]; then
        touch "$S/requests/$id/cancel"; note "cancelling $id (Ctrl-C again to stop waiting)"
    elif rm -f "$S/inbox/$id.json" 2>/dev/null && [ ! -e "$S/requests/$id" ]; then
        note "withdrew $id"; exit 130
    fi
}
trap on_interrupt INT

start=$(date +%s)
result="$S/requests/$id/result.json"
until [ -f "$result" ]; do
    if [ ! -f "$S/server.json" ]; then
        fail 7 "the server stopped; $id waits for the next one (carl GET .../requests/$id)"
    fi
    if [ -n "$maxtime" ] && [ $(( $(date +%s) - start )) -ge "$maxtime" ]; then
        fail 28 "timed out after ${maxtime}s; $id goes on (carl GET .../requests/$id)"
    fi
    nap
done

emit "$result"
[ "$cancelled" = 1 ] && exit 130
if [ "$failon" = 1 ]; then
    code=$(status_code "$result")
    [ -n "$code" ] && [ "$code" -ge 400 ] && exit 22
fi
exit 0
