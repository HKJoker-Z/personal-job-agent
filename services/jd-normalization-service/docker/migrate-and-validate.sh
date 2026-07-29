#!/bin/sh
set -eu

flyway migrate
exec flyway validate
