#!/usr/bin/env bash
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/support/clinic_runtime/environment.sh"
cd "$CLINIC_RUNTIME_ROOT"
exec /usr/bin/python3 -m support.clinic_runtime "$@"
