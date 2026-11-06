set -u

read_file=""
read_max_bytes=4294967296
confirm_idle=0
paths=""

usage() {
    echo "usage: sh probe-linux.sh [--read-test FILE --confirm-idle [--max-bytes N]] PATH..." >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --read-test) [ $# -ge 2 ] || usage; read_file="$2"; shift 2 ;;
        --max-bytes) [ $# -ge 2 ] || usage; read_max_bytes="$2"; shift 2 ;;
        --confirm-idle) confirm_idle=1; shift ;;
        -h|--help) usage ;;
        *) paths="$paths
$1"; shift ;;
    esac
done

json_string() {
    printf '%s' "$1" | awk 'BEGIN { ORS = "" } { gsub(/\\/, "\\\\"); gsub(/"/, "\\\""); gsub(/\t/, "\\t"); gsub(/\r/, ""); if (NR > 1) printf "\\n"; printf "%s", $0 }' | sed 's/^/"/; s/$/"/'
}

json_or_null() {
    if [ -n "$1" ]; then printf '%s' "$1"; else printf 'null'; fi
}

command_json() {
    if command -v "$1" >/dev/null 2>&1; then
        output=$("$@" 2>/dev/null) && [ -n "$output" ] && { printf '%s' "$output"; return; }
    fi
    printf 'null'
}

notes=""
add_note() {
    if [ -n "$notes" ]; then notes="$notes,"; fi
    notes="$notes$(json_string "$1")"
}

path_entries=""
old_ifs=$IFS
IFS='
'
for path in $paths; do
    [ -n "$path" ] || continue
    if [ ! -e "$path" ]; then
        add_note "path not found: $path"
        continue
    fi
    df_line=$(df -P -B1 "$path" 2>/dev/null | awk 'NR == 2 { print $2 " " $3 " " $4 " " $6 }')
    total=$(printf '%s' "$df_line" | awk '{ print $1 }')
    used=$(printf '%s' "$df_line" | awk '{ print $2 }')
    free=$(printf '%s' "$df_line" | awk '{ print $3 }')
    mount=$(printf '%s' "$df_line" | awk '{ print $4 }')
    fs_type=$(stat -f -c %T "$path" 2>/dev/null)
    findmnt_json=$(command_json findmnt -J -T "$path" -o TARGET,SOURCE,FSTYPE,OPTIONS)
    entry="{\"path\": $(json_string "$path"), \"mount_point\": $(json_string "$mount"), \"fs_type\": $(json_string "$fs_type"), \"total_bytes\": $(json_or_null "$total"), \"used_bytes\": $(json_or_null "$used"), \"free_bytes\": $(json_or_null "$free"), \"findmnt\": $findmnt_json}"
    if [ -n "$path_entries" ]; then path_entries="$path_entries, "; fi
    path_entries="$path_entries$entry"
done
IFS=$old_ifs

lsblk_json=$(command_json lsblk -J -b -o NAME,TYPE,SIZE,ROTA,TRAN,MODEL,FSTYPE,MOUNTPOINT)

gpu_compute=null
if command -v nvidia-smi >/dev/null 2>&1; then
    gpu_compute=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c '[0-9]')
fi

read_test=null
if [ -n "$read_file" ]; then
    if [ "$confirm_idle" -ne 1 ]; then
        add_note "read test skipped: --confirm-idle not given"
    elif [ "$gpu_compute" != "null" ] && [ "$gpu_compute" -gt 0 ]; then
        add_note "read test skipped: nvidia-smi lists $gpu_compute compute processes"
    elif [ ! -f "$read_file" ]; then
        add_note "read test skipped: not a file: $read_file"
    else
        size=$(stat -c %s "$read_file")
        block=4194304
        bytes=$size
        if [ "$bytes" -gt "$read_max_bytes" ]; then bytes=$read_max_bytes; fi
        count=$((bytes / block))
        direct=true
        start=$(date +%s.%N)
        if ! dd if="$read_file" of=/dev/null bs=$block count=$count iflag=direct 2>/tmp/probe-dd.$$; then
            direct=false
            add_note "iflag=direct refused ($(tr '\n' ' ' < /tmp/probe-dd.$$)): buffered read, cold not guaranteed"
            start=$(date +%s.%N)
            dd if="$read_file" of=/dev/null bs=$block count=$count 2>/tmp/probe-dd.$$
        fi
        end=$(date +%s.%N)
        summary=$(tail -n 1 /tmp/probe-dd.$$)
        rm -f /tmp/probe-dd.$$
        read_bytes=$((count * block))
        seconds=$(awk -v s="$start" -v e="$end" 'BEGIN { printf "%.3f", e - s }')
        rate=$(awk -v b="$read_bytes" -v s="$seconds" 'BEGIN { if (s > 0) printf "%.1f", b / s / 1048576; else print "null" }')
        read_test="{\"file\": $(json_string "$read_file"), \"file_bytes\": $size, \"read_bytes\": $read_bytes, \"block_bytes\": $block, \"direct_io\": $direct, \"seconds\": $seconds, \"mib_per_second\": $rate, \"dd\": $(json_string "$summary")}"
    fi
fi

kernel=$(uname -r)
host=$(uname -n)
in_container=false
if [ -f /.dockerenv ] || grep -qa 'docker\|containerd' /proc/1/cgroup 2>/dev/null; then in_container=true; fi
wsl=false
if grep -qi microsoft /proc/version 2>/dev/null; then wsl=true; fi

printf '{\n'
printf '  "schema": 1,\n'
printf '  "probe": "linux",\n'
printf '  "generated_at": %s,\n' "$(json_string "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
printf '  "kernel": %s,\n' "$(json_string "$kernel")"
printf '  "hostname": %s,\n' "$(json_string "$host")"
printf '  "in_container": %s,\n' "$in_container"
printf '  "wsl_kernel": %s,\n' "$wsl"
printf '  "gpu_compute_processes": %s,\n' "$gpu_compute"
printf '  "paths": [%s],\n' "$path_entries"
printf '  "lsblk": %s,\n' "$lsblk_json"
printf '  "read_test": %s,\n' "$read_test"
printf '  "notes": [%s]\n' "$notes"
printf '}\n'
