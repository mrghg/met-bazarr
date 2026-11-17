#!/bin/bash
# Build one met-bazarr store on JASMIN's LOTUS2: create, fill every time, then
# check and validate. One CPU; a 193-time UM window takes ~25 min and ~3 GB.
#
# Submit from the repository root on a sci server:
#   sbatch --account=<account> scripts/lotus/build_store.sbatch recipes/um/EUR-Jan.yaml [extra finish flags]
# e.g. add --validation-input for a store built from a tagged release.
# An existing store is kept unless OVERWRITE=1 is exported (sbatch --export=ALL,OVERWRITE=1).
#
# Needs the jaspy-based environment .venv-jaspy (docs/setup.md, "Met Office UM
# on JASMIN"). The job exits non-zero if any step fails or validation fails.
#SBATCH --job-name=metbazarr
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=03:00:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

recipe="${1:?usage: sbatch build_store.sbatch <recipe.yaml> [finish flags]}"
shift
cd "${SLURM_SUBMIT_DIR:-.}"

echo "host $(hostname), commit $(git rev-parse HEAD), recipe ${recipe}, start $(date -u +%FT%TZ)"
.venv-jaspy/bin/metbazarr build "${recipe}" --step create ${OVERWRITE:+--overwrite}
.venv-jaspy/bin/metbazarr build "${recipe}" --step fill
.venv-jaspy/bin/metbazarr build "${recipe}" --step finish "$@"
echo "done $(date -u +%FT%TZ)"
