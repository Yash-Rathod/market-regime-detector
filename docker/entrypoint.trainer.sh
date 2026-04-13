#!/bin/sh
# Fix volume mount ownership then drop to appuser
chown -R appuser:appgroup /app/mlartifacts
exec gosu appuser "$@"
