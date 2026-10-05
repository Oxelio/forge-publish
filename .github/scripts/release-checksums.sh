#!/usr/bin/env bash
set -euo pipefail

# Missing either distribution type must fail before attestation or publication.
cd "${1:-dist}"
sha256sum -- *.whl *.tar.gz > SHA256SUMS
sha256sum --check SHA256SUMS
