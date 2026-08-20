#!/bin/sh

set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s YYYYMMDD\n' "$0" >&2
    exit 2
fi

release=$1
case "$release" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9])
        ;;
    *)
        printf 'release must be exactly eight digits (YYYYMMDD)\n' >&2
        exit 2
        ;;
esac

image="ghcr.io/project-osrm/osrm-backend@sha256:a7091038e39a73659767f34ef2d389909b42ea80b09bd2bdca482dce2991cbad"
source_url="https://download.geofabrik.de/asia/thailand-latest.osm.pbf"
source_md5_url="${source_url}.md5"
bbox="99.3,12.7,101.5,14.8"
release_dir="/srv/strava-osrm/releases/${release}-bangkok-region"

if [ -e "$release_dir" ]; then
    printf 'release directory already exists: %s\n' "$release_dir" >&2
    exit 1
fi

/usr/bin/install -d -m 0755 \
    "$release_dir/source" \
    "$release_dir/foot" \
    "$release_dir/bike"

/usr/bin/curl --fail --location --retry 3 \
    --output "$release_dir/source/thailand-latest.osm.pbf" "$source_url"
/usr/bin/curl --fail --location --retry 3 \
    --output "$release_dir/source/thailand-latest.osm.pbf.md5" "$source_md5_url"
(
    cd "$release_dir/source"
    /usr/bin/md5sum -c thailand-latest.osm.pbf.md5
)

/usr/bin/osmium extract \
    --strategy=complete_ways \
    --bbox "$bbox" \
    --output "$release_dir/source/bangkok-region.osm.pbf" \
    "$release_dir/source/thailand-latest.osm.pbf"

build_profile() {
    graph=$1
    profile=$2

    /usr/bin/docker run --rm \
        --name "strava-osrm-build-${graph}" \
        --network none \
        --cpus 1.5 \
        --memory 4g \
        --memory-swap 6g \
        --pids-limit 512 \
        --cap-drop ALL \
        --security-opt no-new-privileges \
        --volume "$release_dir:/data" \
        "$image" \
        osrm-extract -p "/opt/${profile}.lua" \
        /data/source/bangkok-region.osm.pbf \
        --output "/data/${graph}/thailand"

    /usr/bin/docker run --rm \
        --name "strava-osrm-partition-${graph}" \
        --network none \
        --cpus 1.5 \
        --memory 4g \
        --memory-swap 6g \
        --pids-limit 512 \
        --cap-drop ALL \
        --security-opt no-new-privileges \
        --volume "$release_dir:/data" \
        "$image" \
        osrm-partition "/data/${graph}/thailand.osrm"

    /usr/bin/docker run --rm \
        --name "strava-osrm-customize-${graph}" \
        --network none \
        --cpus 1.5 \
        --memory 4g \
        --memory-swap 6g \
        --pids-limit 512 \
        --cap-drop ALL \
        --security-opt no-new-privileges \
        --volume "$release_dir:/data" \
        "$image" \
        osrm-customize "/data/${graph}/thailand.osrm"
}

build_profile foot foot
build_profile bike bicycle

{
    printf 'created_at_utc=%s\n' "$(/usr/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'source_url=%s\n' "$source_url"
    printf 'bbox=%s\n' "$bbox"
    printf 'image=%s\n' "$image"
    /usr/bin/md5sum "$release_dir/source/thailand-latest.osm.pbf"
} > "$release_dir/MANIFEST"

printf 'built release: %s\n' "$release_dir"
printf 'verify both profiles before switching /srv/strava-osrm/current\n'
