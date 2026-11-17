#!/usr/bin/env bash
# Compatibility alias; all current logic/environment/preflight lives in clinic_experiment.sh.
set -eo pipefail
exec "$(dirname -- "${BASH_SOURCE[0]}")/clinic_experiment.sh" episode --probe source "$@"
