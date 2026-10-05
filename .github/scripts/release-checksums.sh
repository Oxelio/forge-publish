#!/usr/bin/env bash
set -euo pipefail

# Missing a distribution or its SBOM must fail before attestation/publication.
cd "${1:-dist}"
sha256sum -- *.whl *.tar.gz forge-publish.cdx.json > SHA256SUMS
sha256sum --check SHA256SUMS
