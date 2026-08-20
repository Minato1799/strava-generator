#!/bin/sh

set -eu

backup_dir="/var/backups/strava-generator"
timestamp=$(/usr/bin/date -u '+%Y%m%dT%H%M%SZ')
archive="${backup_dir}/strava-config-${timestamp}.tar.gz"
partial="${archive}.partial"

/usr/bin/install -d -m 0700 "$backup_dir"
work_dir=$(/usr/bin/mktemp -d "${backup_dir}/.backup.XXXXXX")

cleanup() {
    /usr/bin/rm -f "$partial"
    /usr/bin/rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

copy_config() {
    source_path=$1
    if [ -f "$source_path" ]; then
        destination="${work_dir}${source_path}"
        /usr/bin/install -d -m 0700 "$(/usr/bin/dirname "$destination")"
        /usr/bin/install -m 0600 "$source_path" "$destination"
    fi
}

copy_config /etc/caddy/Caddyfile
copy_config /etc/strava-generator.env
copy_config /etc/systemd/system/strava-generator.service
copy_config /etc/systemd/system/strava-osrm-foot.service
copy_config /etc/systemd/system/strava-osrm-bike.service
copy_config /etc/systemd/system/strava-healthcheck.service
copy_config /etc/systemd/system/strava-healthcheck.timer
copy_config /etc/systemd/system/strava-config-backup.service
copy_config /etc/systemd/system/strava-config-backup.timer
copy_config /usr/local/sbin/strava-healthcheck
copy_config /usr/local/sbin/strava-config-backup
copy_config /usr/local/sbin/strava-osrm-build

commit="unknown"
if commit_value=$(/usr/bin/git -C /opt/strava-generator/app rev-parse HEAD 2>/dev/null); then
    commit=$commit_value
fi

{
    printf 'created_at_utc=%s\n' "$timestamp"
    printf 'application_commit=%s\n' "$commit"
    printf 'hostname=%s\n' "$(/usr/bin/hostname)"
} > "${work_dir}/MANIFEST"
/usr/bin/chmod 0600 "${work_dir}/MANIFEST"

(
    cd "$work_dir"
    /usr/bin/find . -type f ! -name SHA256SUMS -print0 \
        | /usr/bin/sort -z \
        | /usr/bin/xargs -0 /usr/bin/sha256sum > SHA256SUMS
)
/usr/bin/chmod 0600 "${work_dir}/SHA256SUMS"

/usr/bin/tar -C "$work_dir" -czf "$partial" .
/usr/bin/chmod 0600 "$partial"
/usr/bin/mv "$partial" "$archive"

/usr/bin/find "$backup_dir" -maxdepth 1 -type f \
    -name 'strava-config-*.tar.gz' -mtime +14 -delete

/usr/bin/logger -p daemon.notice -t strava-config-backup \
    "configuration backup completed"
