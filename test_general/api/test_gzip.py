import gzip
import shutil
import io
import tempfile
from pathlib import Path
from typing import List

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from deepdiff import DeepDiff

from prepline_general.api.app import app

MAIN_API_ROUTE = "general/v0/general"


@pytest.mark.parametrize("output_format", ["application/json", "text/csv"])
@pytest.mark.parametrize(
    "filenames_to_gzip, filenames_no_gzip, uncompressed_content_type",
    [
        # fmt: off
        (["fake-html.html"], [], "text/html"),
        (["stanley-cups.csv"], [], "application/csv"),
        (["fake.doc"], [], "application/msword"),
        (["layout-parser-paper-fast.pdf"], [], "application/pdf"),
        (["fake-email-attachment.eml", "fake-email.eml"], [], "message/rfc822"),
        (["fake-email-attachment.eml", "fake-email.eml", "fake-email-image-embedded.eml"], [], "message/rfc822"),
        (["layout-parser-paper-fast.pdf", "list-item-example.pdf"], [], "application/pdf"),
        # now the same but without explicit content type
        # to make the system guess the un-gzipped type based on content.
        (["fake-html.html"], [], ""),
        (["fake-email-attachment.eml", "fake-email.eml"], [], ""),
        (["layout-parser-paper-fast.pdf", "list-item-example.pdf"], [], ""),
        # mix of compressed and uncompressed
        (["layout-parser-paper-fast.pdf"], ["list-item-example.pdf"], "application/pdf"),
        # mix of compressed and uncompressed, and guessing of content type
        (["layout-parser-paper-fast.pdf"], ["list-item-example.pdf"], ""),
        # have to use OCR which is slow, so minimum cases
        (["embedded-images-tables.jpg"], ["english-and-korean.png"], "image/png"),
        (["embedded-images-tables.jpg"], ["english-and-korean.png"], ""),
        # fmt: on
    ],
)
def test_gzipped_files_are_parsed_like_original(
    output_format: str,
    filenames_to_gzip: List[str],
    filenames_no_gzip: List[str],
    uncompressed_content_type: str,
):
    """
    Verify that API supports unzipping gzip and correctly interprets gz_uncompressed_content_type
    by comparing response to directly parsing the same files.
    The one thing which changes is the filenames in metadata, which have to be ignored.
    """

    client = TestClient(app)
    gz_options = {
        "gz_uncompressed_content_type": (
            uncompressed_content_type if uncompressed_content_type else None
        ),
        "output_format": output_format,
    }
    response1 = get_gzipped_response(
        client, filenames_to_gzip, filenames_no_gzip, gz_options, uncompressed_content_type
    )
    response2 = call_api(
        client,
        [],
        filenames_to_gzip + filenames_no_gzip,
        uncompressed_content_type,
        {"output_format": output_format},
    )
    compare_responses(
        response1, response2, output_format, len(filenames_to_gzip + filenames_no_gzip)
    )


def compare_responses(
    response1: httpx.Response, response2: httpx.Response, output_format: str, files_count: int
) -> None:
    if output_format == "application/json":
        if files_count == 1:
            exclude_regex_paths = r"root\[\d+\]\['metadata'\]\['filename'\]"
        else:
            exclude_regex_paths = r"root\[\d+\]\[\d+\]\['metadata'\]\['filename'\]"
        diff = DeepDiff(
            t1=response1.json(),
            t2=response2.json(),
            exclude_regex_paths=exclude_regex_paths,
        )
        assert len(diff) == 0
    else:
        df1 = pd.read_csv(io.StringIO(response1.text))
        df2 = pd.read_csv(io.StringIO(response2.text))
        diff = DeepDiff(
            t1=df1.to_dict(), t2=df2.to_dict(), exclude_regex_paths=r"root\['filename'\]\[\d+\]"
        )
        assert len(diff) == 0


def call_api(
    client: TestClient,
    filenames_gzipped: List[str],
    filenames: List[str],
    content_type: str,
    options: dict,
) -> httpx.Response:
    files = []
    for filename in filenames_gzipped:
        full_path = Path("sample-docs") / filename
        files.append(("files", (str(full_path), open(full_path, "rb"), "application/gzip")))

    for filename in filenames:
        full_path = Path("sample-docs") / filename
        files.append(("files", (str(full_path), open(full_path, "rb"), content_type)))

    response = client.post(
        MAIN_API_ROUTE,
        files=files,
        data=options,
    )
    assert response.status_code == 200, response.text
    assert len(response.text) > 0
    return response


def get_gzipped_response(
    client: TestClient,
    filenames_to_gzip: List[str],
    filenames_no_gzip: List[str],
    options: dict,
    content_type: str,
) -> httpx.Response:
    """
    Gzips the filenames_to_gzip into temporary .gz file and sends to API, along with filenames_no_gzip.
    """
    tempfiles = {}
    for filename in filenames_to_gzip:
        gz_file_extension = f".{Path(filename).suffix}.gz"
        temp_file = tempfile.NamedTemporaryFile(suffix=gz_file_extension)
        full_path = Path("sample-docs") / filename
        gzip_file(str(full_path), temp_file.name)
        tempfiles[filename] = temp_file

    gzipped = [temp_file.name for temp_file in tempfiles.values()]

    response = call_api(client, gzipped, filenames_no_gzip, content_type, options)

    for filename in filenames_to_gzip:
        tempfiles[filename].close()

    return response


def gzip_file(in_filepath: str, out_filepath: str):
    with open(in_filepath, "rb") as f_in:
        with gzip.open(out_filepath, "wb", compresslevel=1) as f_out:
            shutil.copyfileobj(f_in, f_out)
