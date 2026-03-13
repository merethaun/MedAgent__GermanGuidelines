#!/bin/sh
set -eu

echo "Waiting for Snowstorm Lite..."
for i in $(seq 1 120); do
  curl -fsS http://snomed-lite:8080/fhir/metadata >/dev/null && break
  sleep 2
done
curl -fsS http://snomed-lite:8080/fhir/metadata >/dev/null || {
  echo "Timed out waiting for Snowstorm Lite"; exit 1; }

# Import the German Edition (includes International)
curl -fSs -u "admin:${SNOMED_ADMIN_PASSWORD}" \
  --form "file=@/data/SnomedCT_Germany-EditionRelease_PRODUCTION_20250515T120000Z.zip" \
  --form "version-uri=http://snomed.info/sct/11000274103/version/20250515" \
  http://snomed-lite:8080/fhir-admin/load-package

echo "All done. Keeping container alive."
tail -f /dev/null
