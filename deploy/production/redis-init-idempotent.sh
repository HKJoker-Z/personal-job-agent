#!/bin/sh
set -eu

data_dir=/data
redis_account=redis

if [ ! -d "$data_dir" ]; then
    echo '{"redis_init":"failed","reason":"data_directory_missing"}'
    exit 1
fi

expected_uid=$(id -u "$redis_account")
expected_gid=$(id -g "$redis_account")
case "$expected_uid:$expected_gid" in
    *[!0-9:]*|:|*:)
        echo '{"redis_init":"failed","reason":"invalid_image_account"}'
        exit 1
        ;;
esac

data_uid=$(stat -c '%u' "$data_dir")
data_gid=$(stat -c '%g' "$data_dir")
data_mode=$(stat -c '%a' "$data_dir")
first_mismatch=$(find "$data_dir" -xdev \( ! -user "$expected_uid" -o ! -group "$expected_gid" \) -print -quit)

if [ -z "$first_mismatch" ] && [ "$data_uid" = "$expected_uid" ] && \
   [ "$data_gid" = "$expected_gid" ] && [ "$data_mode" = '700' ]; then
    printf '{"redis_init":"already_valid","uid":%s,"gid":%s,"mode":"700"}\n' "$expected_uid" "$expected_gid"
    exit 0
fi

if [ -n "$first_mismatch" ]; then
    find "$data_dir" -xdev \( ! -user "$expected_uid" -o ! -group "$expected_gid" \) \
        -exec chown "$expected_uid:$expected_gid" {} +
fi
[ "$data_mode" = '700' ] || chmod 0700 "$data_dir"

remaining_mismatch=$(find "$data_dir" -xdev \( ! -user "$expected_uid" -o ! -group "$expected_gid" \) -print -quit)
if [ "$(stat -c '%u' "$data_dir")" != "$expected_uid" ] || \
   [ "$(stat -c '%g' "$data_dir")" != "$expected_gid" ] || \
   [ "$(stat -c '%a' "$data_dir")" != '700' ] || [ -n "$remaining_mismatch" ]; then
    echo '{"redis_init":"failed","reason":"post_repair_verification_failed"}'
    exit 1
fi
printf '{"redis_init":"repaired","uid":%s,"gid":%s,"mode":"700"}\n' "$expected_uid" "$expected_gid"
