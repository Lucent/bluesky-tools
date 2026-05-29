#!/bin/sh
# `docker build` doesn't read .env (only `docker compose` does), so source it
# ourselves and pass ARCHIVE_DID through as a build arg.
set -e
set -a; . ./.env; set +a
exec docker build --build-arg "ARCHIVE_DID=$ARCHIVE_DID" -t thread-browser:latest "$@" .
