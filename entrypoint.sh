#!/bin/sh
set -e
chown recipes:recipes /data
exec gosu recipes "$@"
