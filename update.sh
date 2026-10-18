#!/usr/bin/env sh
set -eu

# Local-only publication workflow. Credentials are resolved inside
# github_graphql.py from GITHUB_TOKEN, GH_TOKEN, or `gh auth token`; this
# script never reads, echoes, stores, or forwards token text itself.

ROOT_DIR=${PROFILE_ROOT_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}
PYTHON=${PROFILE_PYTHON:-python3}
PORTRAIT_PYTHON=${PROFILE_PORTRAIT_PYTHON:-$PYTHON}
GIT=${PROFILE_GIT:-git}
COMMIT_MESSAGE=${PROFILE_COMMIT_MESSAGE:-chore(profile): refresh dashboard assets}

DO_COMMIT=1
DO_PUSH=1
FORCE_PORTRAIT=0

usage() {
  printf '%s\n' \
    "Usage: ./update.sh [--no-push] [--no-commit] [--refresh-portrait]" \
    "" \
    "  --no-push          generate, validate, and commit without pushing" \
    "  --no-commit        generate and validate without committing or pushing" \
    "  --refresh-portrait regenerate the approved Variant B particle map"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-push)
      DO_PUSH=0
      ;;
    --no-commit)
      DO_COMMIT=0
      DO_PUSH=0
      ;;
    --refresh-portrait)
      FORCE_PORTRAIT=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

for required in github_graphql.py generate.py snake.py validate.py README.md; do
  if [ ! -f "$ROOT_DIR/$required" ]; then
    printf 'Profile update failed: missing %s\n' "$required" >&2
    exit 1
  fi
done

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/github-profile-update.XXXXXX")
case "$WORK_DIR" in
  */github-profile-update.*) ;;
  *)
    printf 'Profile update failed: unsafe temporary directory\n' >&2
    exit 1
    ;;
esac

cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

STAGE_ASSETS="$WORK_DIR/assets"
STAGE_PREVIEWS="$WORK_DIR/previews"
STAGE_STATS="$STAGE_ASSETS/github-stats.json"
STAGE_DOTS="$STAGE_ASSETS/dots.json"
mkdir -p "$STAGE_ASSETS" "$STAGE_PREVIEWS"

printf '%s\n' 'Refreshing authenticated GitHub statistics...'
"$PYTHON" "$ROOT_DIR/github_graphql.py" --output "$STAGE_STATS"

SOURCE_PATH="$ROOT_DIR/assets/source/snoozies-nft.jpg"
if [ ! -f "$SOURCE_PATH" ] && [ -f "$ROOT_DIR/assets/source/Snoozies_nft.jpg" ]; then
  SOURCE_PATH="$ROOT_DIR/assets/source/Snoozies_nft.jpg"
fi

REFRESH_PORTRAIT=$FORCE_PORTRAIT
if [ ! -f "$ROOT_DIR/assets/dots.json" ]; then
  REFRESH_PORTRAIT=1
elif [ -f "$SOURCE_PATH" ] && [ "$SOURCE_PATH" -nt "$ROOT_DIR/assets/dots.json" ]; then
  REFRESH_PORTRAIT=1
fi

if [ "$REFRESH_PORTRAIT" -eq 1 ]; then
  if [ ! -f "$SOURCE_PATH" ]; then
    printf '%s\n' 'Profile update failed: portrait source image is missing' >&2
    exit 1
  fi
  printf '%s\n' 'Regenerating approved Variant B portrait data...'
  "$PORTRAIT_PYTHON" "$ROOT_DIR/portrait.py" \
    --input "$SOURCE_PATH" \
    --output "$STAGE_DOTS" \
    --preview-dir "$STAGE_PREVIEWS" \
    --variant variant-b
else
  cp "$ROOT_DIR/assets/dots.json" "$STAGE_DOTS"
fi

printf '%s\n' 'Generating staged dashboard and snake assets...'
"$PYTHON" "$ROOT_DIR/generate.py" \
  --stats "$STAGE_STATS" \
  --dots "$STAGE_DOTS" \
  --output-dir "$STAGE_ASSETS" \
  --preview-dir "$STAGE_PREVIEWS"
"$PYTHON" "$ROOT_DIR/snake.py" \
  --stats "$STAGE_STATS" \
  --output-dir "$STAGE_ASSETS" \
  --preview-dir "$STAGE_PREVIEWS"

validate_set() {
  stats_path=$1
  dots_path=$2
  asset_dir=$3
  "$PYTHON" "$ROOT_DIR/validate.py" \
    --readme "$ROOT_DIR/README.md" \
    --stats "$stats_path" \
    --dots "$dots_path" \
    --dashboard-dark "$asset_dir/dark.svg" \
    --dashboard-light "$asset_dir/light.svg" \
    --snake-dark "$asset_dir/snake-dark.svg" \
    --snake-light "$asset_dir/snake-light.svg"
}

printf '%s\n' 'Validating staged publication set...'
validate_set "$STAGE_STATS" "$STAGE_DOTS" "$STAGE_ASSETS"

printf '%s\n' 'Running test suite...'
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s "$ROOT_DIR/tests"

promote_if_changed() {
  source_path=$1
  destination_path=$2
  if [ -f "$destination_path" ] && cmp -s "$source_path" "$destination_path"; then
    return 0
  fi
  destination_dir=$(dirname -- "$destination_path")
  temporary_path="$destination_path.profile-update.$$"
  mkdir -p "$destination_dir"
  cp "$source_path" "$temporary_path"
  mv "$temporary_path" "$destination_path"
  printf 'Updated %s\n' "${destination_path#"$ROOT_DIR/"}"
}

promote_if_changed "$STAGE_STATS" "$ROOT_DIR/assets/github-stats.json"
if [ "$REFRESH_PORTRAIT" -eq 1 ]; then
  promote_if_changed "$STAGE_DOTS" "$ROOT_DIR/assets/dots.json"
fi
promote_if_changed "$STAGE_ASSETS/dark.svg" "$ROOT_DIR/assets/dark.svg"
promote_if_changed "$STAGE_ASSETS/light.svg" "$ROOT_DIR/assets/light.svg"
promote_if_changed "$STAGE_ASSETS/snake-dark.svg" "$ROOT_DIR/assets/snake-dark.svg"
promote_if_changed "$STAGE_ASSETS/snake-light.svg" "$ROOT_DIR/assets/snake-light.svg"

printf '%s\n' 'Validating promoted canonical files...'
validate_set "$ROOT_DIR/assets/github-stats.json" "$ROOT_DIR/assets/dots.json" "$ROOT_DIR/assets"

PUBLICATION_STATUS=$("$GIT" -C "$ROOT_DIR" status --porcelain -- \
  README.md \
  assets/github-stats.json \
  assets/dots.json \
  assets/dark.svg \
  assets/light.svg \
  assets/snake-dark.svg \
  assets/snake-light.svg)

if [ -z "$PUBLICATION_STATUS" ]; then
  printf '%s\n' 'Publication files are unchanged; nothing to commit or push.'
  exit 0
fi

if [ "$DO_COMMIT" -eq 0 ]; then
  printf '%s\n' 'Publication files changed; commit and push skipped by --no-commit.'
  exit 0
fi

"$GIT" -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null
"$GIT" -C "$ROOT_DIR" add -- \
  README.md \
  assets/github-stats.json \
  assets/dots.json \
  assets/dark.svg \
  assets/light.svg \
  assets/snake-dark.svg \
  assets/snake-light.svg
"$GIT" -C "$ROOT_DIR" commit --only -m "$COMMIT_MESSAGE" -- \
  README.md \
  assets/github-stats.json \
  assets/dots.json \
  assets/dark.svg \
  assets/light.svg \
  assets/snake-dark.svg \
  assets/snake-light.svg

if [ "$DO_PUSH" -eq 0 ]; then
  printf '%s\n' 'Created local refresh commit; push skipped by --no-push.'
  exit 0
fi

REMOTE_HEAD=$("$GIT" -C "$ROOT_DIR" symbolic-ref --quiet --short refs/remotes/origin/HEAD || true)
DEFAULT_BRANCH=${REMOTE_HEAD#origin/}
CURRENT_BRANCH=$("$GIT" -C "$ROOT_DIR" branch --show-current)
if [ -z "$REMOTE_HEAD" ] || [ "$DEFAULT_BRANCH" = "$REMOTE_HEAD" ]; then
  printf '%s\n' 'Profile update failed: origin default branch is not configured' >&2
  exit 1
fi
if [ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ]; then
  printf 'Profile update failed: checkout default branch %s before publishing\n' "$DEFAULT_BRANCH" >&2
  exit 1
fi

"$GIT" -C "$ROOT_DIR" push origin "HEAD:$DEFAULT_BRANCH"
printf 'Published refreshed profile assets to %s.\n' "$DEFAULT_BRANCH"
