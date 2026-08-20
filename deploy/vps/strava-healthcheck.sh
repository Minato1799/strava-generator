#!/bin/sh

set -eu

service_name="strava-generator.service"
health_url="http://127.0.0.1:8720/health/"

check_health() {
    response=$(
        /usr/bin/curl \
            --silent \
            --show-error \
            --fail \
            --max-time 5 \
            --header "Host: strava.scan-realtime.site" \
            --header "X-Forwarded-Proto: https" \
            "$health_url"
    ) || return 1

    printf '%s' "$response" | /usr/bin/grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
}

check_router() {
    port=$1
    response=$(
        /usr/bin/curl \
            --silent \
            --show-error \
            --fail \
            --max-time 5 \
            "http://127.0.0.1:${port}/route/v1/driving/100.53877,13.73024;100.54268,13.72927?overview=false"
    ) || return 1

    printf '%s' "$response" | /usr/bin/grep -Eq '"code"[[:space:]]*:[[:space:]]*"Ok"'
}

check_router_service() {
    router_service=$1
    port=$2

    if ! /usr/bin/systemctl is-active --quiet "$router_service"; then
        return 0
    fi
    if check_router "$port"; then
        return 0
    fi

    /usr/bin/logger -p daemon.warning -t strava-healthcheck \
        "router health check failed; restarting ${router_service} once"
    /usr/bin/systemctl restart "$router_service"
    /usr/bin/sleep 2
    if check_router "$port"; then
        /usr/bin/logger -p daemon.notice -t strava-healthcheck \
            "router health check recovered after one restart"
        return 0
    fi

    /usr/bin/logger -p daemon.err -t strava-healthcheck \
        "router health check still failing after one restart"
    return 1
}

if ! check_health; then
    /usr/bin/logger -p daemon.warning -t strava-healthcheck \
        "health check failed; restarting ${service_name} once"
    /usr/bin/systemctl restart "$service_name"
    /usr/bin/sleep 2

    if ! check_health; then
        /usr/bin/logger -p daemon.err -t strava-healthcheck \
            "health check still failing after one restart"
        exit 1
    fi

    /usr/bin/logger -p daemon.notice -t strava-healthcheck \
        "health check recovered after one restart"
fi

check_router_service strava-osrm-foot.service 8731
check_router_service strava-osrm-bike.service 8732
