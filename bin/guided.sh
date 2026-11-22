# guided.sh: shared steps for the MEGA applet's guided terminal dialogs.
# SPDX-License-Identifier: GPL-3.0-or-later
# shellcheck shell=bash
#
# Sourced by mega-account-login, mega-add-sync, mega-add-backup and
# mega-edit-backup. Needs gum and MEGAcmd; stops at once when gum is missing.
#
# The choose_* helpers print their answer, so they run in $(...); a cancel
# or a wrong answer makes them exit non-zero, and the caller must stop then:
#   folder=$(choose_local_folder "...") || exit 1

if ! command -v gum >/dev/null 2>&1; then
  echo "gum is not installed; install it to use the MEGA dialogs." >&2
  exit 1
fi

# A MEGAcmd backup period: a time such as "1m12d3h" (m months, M minutes)
# or a cron line with seconds.
PERIOD_PATTERN='^([0-9]+[ymdhMs])+$|^([0-9A-Za-z*,/?-]+ ){5}[0-9A-Za-z*,/?-]+$'

# Prints a message and exits with status 1.
die() {
  gum style --foreground 1 "$*" >&2
  exit 1
}

# Prints an error and exits unless MEGAcmd is logged in.
require_login() {
  mega-whoami >/dev/null 2>&1 || die "MEGAcmd is not logged in. Use \"Log in to MEGA\" in the panel first."
}

# Lets the user pick a local folder below $HOME; prints its absolute path.
choose_local_folder() {
  local header=$1 picked
  picked=$(cd "$HOME" && gum file --directory --height=15 --header="$header (Enter selects, ← goes up)" "$HOME") || exit 1
  [[ -n $picked ]] || exit 1
  [[ -f $picked ]] && picked=$(dirname "$picked")
  [[ -d $picked ]] || die "Not a folder: $picked"
  realpath "$picked"
}

# Asks for a MEGA folder path, suggesting $2; prints it absolute, without trailing slashes.
choose_remote_folder() {
  local header=$1 suggestion=$2 picked
  picked=$(gum input --header="$header" --value="$suggestion" --placeholder="/path/in/MEGA" --char-limit=0) || exit 1
  [[ $picked == /* ]] || picked="/$picked"
  while [[ $picked == */ && $picked != / ]]; do picked=${picked%/}; done
  printf '%s\n' "$picked"
}

# Creates the MEGA folder $1 (and its parents) when it does not exist yet.
ensure_remote_folder() {
  local path=$1
  [[ $path == / ]] && return 0
  mega-ls "$path" >/dev/null 2>&1 && return 0
  mega-mkdir -p "$path" >/dev/null || die "Could not create $path in MEGA"
  echo "Created $path in MEGA."
}

# Lets the user pick a backup schedule; prints MEGAcmd's period string. The
# current period $1, if any, is offered first. Cron times are UTC.
choose_period() {
  local current=${1:-} choice period
  local options=("Daily at 02:00 UTC" "Every 6 hours" "Weekly, Sunday at 03:00 UTC" "Other…")
  [[ -n $current ]] && options=("Keep current ($current)" "${options[@]}")
  choice=$(gum choose --header="When to back up" "${options[@]}") || exit 1
  case $choice in
    "Keep current"*) period=$current ;;
    "Daily at 02:00 UTC") period="0 0 2 * * *" ;;
    "Every 6 hours") period="6h" ;;
    "Weekly, Sunday at 03:00 UTC") period="0 0 3 * * 0" ;;
    "Other…")
      period=$(gum input --header="Period: e.g. 1d, 12h, or a cron line with seconds in UTC (\"0 30 1 * * *\")" \
        --value="$current" --char-limit=0) || exit 1 ;;
    *) exit 1 ;;
  esac
  [[ $period =~ $PERIOD_PATTERN ]] || die "Not a backup period: $period"
  printf '%s\n' "$period"
}

# Asks how many backups to keep, suggesting $1; prints a positive number.
choose_keep() {
  local keep
  keep=$(gum input --header="How many backups to keep" --value="${1:-14}" --char-limit=4) || exit 1
  [[ $keep =~ ^[1-9][0-9]*$ ]] || die "Not a number: $keep"
  printf '%s\n' "$keep"
}

# Joins a MEGA parent folder and a name.
remote_join() {
  if [[ $1 == / ]]; then printf '/%s\n' "$2"; else printf '%s/%s\n' "${1%/}" "$2"; fi
}
