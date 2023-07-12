#!/usr/bin/env bash

set -eu -o pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"/..

PIPELINE_OUTPUT_DIR=tmp-api-check-output-$RANDOM
FILE_INDICTATING_FAILURE="$PIPELINE_OUTPUT_DIR"-has-failures
mkdir -p $PIPELINE_OUTPUT_DIR
touch $PIPELINE_OUTPUT_DIR/__init__.py

function tmp_pipeline_comp_cleanup () {
    cd "$SCRIPT_DIR"/..
    rm -f "$FILE_INDICTATING_FAILURE"
    if [[ "$1" -eq 0 ]]; then
      rm -rf $PIPELINE_OUTPUT_DIR
    fi
    exit "$1"
}

unstructured_api_tools convert-pipeline-notebooks \
  --input-directory ./pipeline-notebooks \
  --output-directory "$PIPELINE_OUTPUT_DIR"

NUM_PIPELINE_API_FILES_GENERATED=$(find "$PIPELINE_OUTPUT_DIR" -name "*.py" | wc -l)

if [[ "$NUM_PIPELINE_API_FILES_GENERATED" -eq 0 ]]; then
    echo "No pipelines where created by unstructured_api_tools convert-pipeline-notebooks"
    tmp_pipeline_comp_cleanup 1
fi

NUM_EXISTING_PIPELINE_API_FILES=$(find "$PACKAGE_NAME"/api -name "*.py" | wc -l)

if [[ "$NUM_PIPELINE_API_FILES_GENERATED" -gt "$NUM_EXISTING_PIPELINE_API_FILES"  ]]; then
    echo "More pipeline api files were autogenerated than appear in the ${PACKAGE_NAME}/api"
    tmp_pipeline_comp_cleanup 1
elif [[ "$NUM_PIPELINE_API_FILES_GENERATED" -lt "$NUM_EXISTING_PIPELINE_API_FILES"  ]]; then
    echo "Fewer pipeline api files were autogenerated than appear in the ${PACKAGE_NAME}/api"
    tmp_pipeline_comp_cleanup 1
fi

cd "$PACKAGE_NAME"/api
find . -name "*.py" -print0 | while IFS= read -r -d '' pipeline_file; do
    set +o pipefail
    if ! diff -u "$pipeline_file" ../../"$PIPELINE_OUTPUT_DIR/$pipeline_file"; then
	touch "../../$FILE_INDICTATING_FAILURE"
    fi
    set -o pipefail
done
cd -

if [ -r "$FILE_INDICTATING_FAILURE" ]; then
    echo
    echo "Autogenerated pipeline api file(s) do not match existing versions, see above for diff's"
    echo " or run: diff -ru ${PACKAGE_NAME}/api/ ${PIPELINE_OUTPUT_DIR}/"
    echo $( pwd )  $FILE_INDICTATING_FAILURE
    cp $FILE_INDICTATING_FAILURE OUCH.txt
    tmp_pipeline_comp_cleanup 1
fi
tmp_pipeline_comp_cleanup 0
