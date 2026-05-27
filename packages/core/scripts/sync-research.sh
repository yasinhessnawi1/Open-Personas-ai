#!/usr/bin/env bash
# Mirror the rendered Persona-RAG report into packages/core/research/.
#
# The Persona-RAG project (at ~/Desktop/Desktop/Persona-RAG) holds the
# persona-vector and drift-detection research that informs persona-core. The
# rendered report (PDF) is the only artefact this directory keeps; everything
# else (research code, scripts, figures, persona YAMLs) lives in the
# Persona-RAG repo itself and is not vendored.
#
# Usage:
#   packages/core/scripts/sync-research.sh                 # default source + dest
#   PERSONA_RAG_DIR=/path/to/Persona-RAG ./sync-research.sh
#
# After syncing, the source commit SHA (if Persona-RAG is a git repo) is
# written to packages/core/research/RESEARCH_VERSION so the mirror's
# provenance is recorded in Open-Persona's git history.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_DIR="${CORE_DIR}/research"
SRC_DIR="${PERSONA_RAG_DIR:-${HOME}/Desktop/Desktop/Persona-RAG}"
REPORT_PDF="${SRC_DIR}/docs/report/main.pdf"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "error: Persona-RAG source not found at ${SRC_DIR}" >&2
  echo "       set PERSONA_RAG_DIR to override." >&2
  exit 1
fi

if [[ ! -f "${REPORT_PDF}" ]]; then
  echo "error: report PDF not found at ${REPORT_PDF}" >&2
  echo "       compile the report in Persona-RAG first." >&2
  exit 1
fi

mkdir -p "${DEST_DIR}"

# Copy the rendered report. The PDF is the only artefact this mirror keeps.
echo "copying report PDF: ${REPORT_PDF} -> ${DEST_DIR}/report.pdf"
cp "${REPORT_PDF}" "${DEST_DIR}/report.pdf"

# Record the source commit SHA so we know which Persona-RAG snapshot is
# vendored. Falls back to a timestamp if the source isn't a git repo.
VERSION_FILE="${DEST_DIR}/RESEARCH_VERSION"
if git -C "${SRC_DIR}" rev-parse HEAD >/dev/null 2>&1; then
  SHA="$(git -C "${SRC_DIR}" rev-parse HEAD)"
  BRANCH="$(git -C "${SRC_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  # Note: we intentionally do not run `git diff` here. On a worktree with a
  # large unindexed virtualenv, the worktree-walk dirty-check can hang for
  # minutes. The commit SHA plus the sync timestamp give enough provenance
  # to identify which Persona-RAG snapshot the report PDF came from.
  {
    echo "source:  ${SRC_DIR}"
    echo "commit:  ${SHA}"
    echo "branch:  ${BRANCH}"
    echo "synced:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "${VERSION_FILE}"
else
  {
    echo "source:  ${SRC_DIR}"
    echo "commit:  (not a git repo)"
    echo "synced:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "${VERSION_FILE}"
fi

echo "done. snapshot info -> ${VERSION_FILE}"
