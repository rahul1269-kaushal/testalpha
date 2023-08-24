from pathlib import Path

import io
import pytest
import re
import requests
import pandas as pd
from fastapi.testclient import TestClient
from unstructured_api_tools.pipelines.api_conventions import get_pipeline_path

from prepline_general.api.app import app
import tempfile

MAIN_API_ROUTE = get_pipeline_path("general")


def test_general_api_health_check():
    client = TestClient(app)
    response = client.get("/healthcheck")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "example_filename, content_type",
    [
        # Note(yuming): Please sort filetypes alphabetically according to
        # https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/auto.py#L14
        ("stanley-cups.csv", "application/csv"),
        ("fake.doc", "application/msword"),
        ("fake.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("family-day.eml", "message/rfc822"),
        ("alert.eml", "message/rfc822"),
        ("announcement.eml", "message/rfc822"),
        ("fake-email-attachment.eml", "message/rfc822"),
        ("fake-email-image-embedded.eml", "message/rfc822"),
        ("fake-email.eml", "message/rfc822"),
        ("winter-sports.epub", "application/epub"),
        ("fake-html.html", "text/html"),
        ("layout-parser-paper-fast.jpg", "image/jpeg"),
        ("spring-weather.html.json", "application/json"),
        ("README.md", "text/markdown"),
        ("fake-email.msg", "application/x-ole-storage"),
        ("fake.odt", "application/vnd.oasis.opendocument.text"),
        ("layout-parser-paper.pdf", "application/pdf"),
        ("fake-power-point.ppt", "application/vnd.ms-powerpoint"),
        (
            "fake-power-point.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("README.rst", "text/x-rst"),
        ("fake-doc.rtf", "application/rtf"),
        ("fake-text.txt", "text/plain"),
        ("stanley-cups.tsv", "text/tsv"),
        (
            "stanley-cups.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("fake-xml.xml", "application/xml"),
    ],
)
def test_general_api(example_filename, content_type):
    client = TestClient(app)
    test_file = Path("sample-docs") / example_filename
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(test_file), open(test_file, "rb"), content_type))]
    )
    assert response.status_code == 200
    assert len(response.json()) > 0
    for i in response.json():
        assert i["metadata"]["filename"] == example_filename
    assert len("".join(elem["text"] for elem in response.json())) > 20

    # Just hit the second path (posting multiple files) to bump the coverage
    # We'll come back and make smarter tests
    response = client.post(
        MAIN_API_ROUTE,
        files=[
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
        ],
    )
    assert response.status_code == 200
    assert all(x["metadata"]["filename"] == example_filename for i in response.json() for x in i)

    assert len(response.json()) > 0

    csv_response = client.post(
        MAIN_API_ROUTE,
        files=[
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
            ("files", (str(test_file), open(test_file, "rb"), content_type)),
        ],
        data={"output_format": "text/csv"},
    )
    assert csv_response.status_code == 200
    dfs = pd.read_csv(io.StringIO(csv_response.text))
    assert len(dfs) > 0


def test_coordinates_param():
    """
    Verify that responses do not include coordinates unless requested
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper-fast.jpg"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"strategy": "hi_res"},
    )

    assert response.status_code == 200
    response_without_coords = response.json()

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"coordinates": "true", "strategy": "hi_res"},
    )

    assert response.status_code == 200
    response_with_coords = response.json()

    # Each element should be the same except for the coordinates field
    for i in range(len(response_with_coords)):
        assert "coordinates" in response_with_coords[i]["metadata"]
        del response_with_coords[i]["metadata"]["coordinates"]
        assert response_with_coords[i] == response_without_coords[i]


def test_ocr_languages_param():
    """
    Verify that we get the corresponding languages from the response with ocr_languages
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "english-and-korean.png"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"strategy": "ocr_only", "ocr_languages": ["eng", "kor"]},
    )

    assert response.status_code == 200
    elements = response.json()
    assert elements[3]["text"].startswith("안녕하세요, 저 희 는 YGEAS 그룹")


def test_skip_infer_table_types_param():
    """
    Verify that we skip table instruction unless specified
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper-with-table.jpg"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
    )

    assert response.status_code == 200
    # test we skip table extraction by default
    elements = response.json()
    table = [el["metadata"]["text_as_html"] for el in elements if "text_as_html" in el["metadata"]]
    assert len(table) == 0

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"skip_infer_table_types": "['pdf']"},
    )

    assert response.status_code == 200
    # test we didn't specify to skip table extration with image
    elements = response.json()
    table = [el["metadata"]["text_as_html"] for el in elements if "text_as_html" in el["metadata"]]
    assert len(table) == 1
    assert "Layouts of history Japanese documents" in table[0]


def test_strategy_param_400():
    """Verify that we get a 400 if we pass in a bad strategy"""
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper.pdf"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
        data={"strategy": "not_a_strategy"},
    )
    assert response.status_code == 400


def test_valid_encoding_param():
    """
    Verify that we get a 200 for passing an encoding param
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "fake-xml.xml"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
        data={"encoding": "ascii"},
    )
    assert response.status_code == 200


def test_invalid_encoding_param():
    """
    Verify that we get a 500 if we pass an invalid encoding through to partition
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "fake-html.html"
    with pytest.raises(LookupError) as excinfo:
        client.post(
            MAIN_API_ROUTE,
            files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
            data={"encoding": "not_an_encoding"},
        )
    assert "unknown encoding" in str(excinfo.value)


def test_api_with_different_encodings():
    """
    Verify that we get different text results for different encodings
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "fake-text-utf-32.txt"

    # utf-16
    response_16 = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
        data={"encoding": "utf-16"},
    )
    assert response_16.status_code == 200
    elements_16 = response_16.json()
    assert elements_16[0]["text"].startswith("\x00T\x00h\x00i\x00s\x00 \x00i\x00s\x00")

    # utf-32
    response_32 = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
        data={"encoding": "utf-32"},
    )
    assert response_32.status_code == 200
    elements_32 = response_32.json()
    assert elements_32[2]["text"].startswith("Important points:")

    # utf-8
    with pytest.raises(UnicodeDecodeError) as excinfo:
        client.post(
            MAIN_API_ROUTE,
            files=[("files", (str(test_file), open(test_file, "rb"), "text/plain"))],
            data={"encoding": "utf8"},
        )
    assert "invalid start byte" in str(excinfo.value)


def test_xml_keep_tags_param():
    """
    Verify that responses do not include xml tags unless requested
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "fake-xml.xml"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"strategy": "hi_res"},
    )
    assert response.status_code == 200
    response_without_xml_tags = response.json()

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"xml_keep_tags": "true", "strategy": "hi_res"},
    )
    assert response.status_code == 200
    response_with_xml_tags = response.json()[3:]  # skip the initial encoding tag(s)

    # The responses should have the same content except for the xml tags
    response_with_xml_tags_index, response_without_xml_tags_index = 0, 0
    while response_without_xml_tags_index < len(response_without_xml_tags):
        xml_tagged_line = response_with_xml_tags[response_with_xml_tags_index]["text"]
        assert xml_tagged_line.startswith("<")
        assert xml_tagged_line.endswith(">")

        # if there is content on this line, ensure it matches the content on the non tagged line
        xml_tagged_line_content = xml_tagged_line.split(">", 1)[1]  # remove opening tag
        if not xml_tagged_line_content:
            response_with_xml_tags_index += 1

        else:
            xml_tagged_line_content = xml_tagged_line_content.split("<", 1)[0]  # remove closing tag

            xml_untagged_line = response_without_xml_tags[response_without_xml_tags_index]["text"]
            xml_tagged_line_content_parsed = re.sub(
                "&amp;", "&", xml_tagged_line_content
            )  # xml_keep_tags does not currently parse the inner content
            assert xml_tagged_line_content_parsed == xml_untagged_line

            response_with_xml_tags_index += 1
            response_without_xml_tags_index += 1


def test_include_page_breaks_param():
    """
    Verify that responses do not include page breaks unless requested
    """
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper-fast.pdf"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"strategy": "fast"},
    )
    assert response.status_code == 200
    response_without_page_breaks = response.json()

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"include_page_breaks": "true", "strategy": "fast"},
    )
    assert response.status_code == 200
    response_with_page_breaks = response.json()

    # The responses should have the same content except extra PageBreak objects
    response_with_page_breaks_index, response_without_page_breaks_index = 0, 0
    while response_with_page_breaks_index <= len(response_without_page_breaks):
        curr_response_with_page_breaks_element = response_with_page_breaks[
            response_with_page_breaks_index
        ]
        curr_response_without_page_breaks_element = response_without_page_breaks[
            response_without_page_breaks_index
        ]
        if curr_response_with_page_breaks_element["type"] == "PageBreak":
            assert curr_response_without_page_breaks_element["type"] != "PageBreak"

            response_with_page_breaks_index += 1
        else:
            assert (
                curr_response_without_page_breaks_element["text"]
                == curr_response_with_page_breaks_element["text"]
            )

            response_with_page_breaks_index += 1
            response_without_page_breaks_index += 1

    last_response_with_page_breaks_element = response_with_page_breaks[
        response_with_page_breaks_index
    ]
    assert last_response_with_page_breaks_element["type"] == "PageBreak"
    assert response_without_page_breaks[-1]["type"] != "PageBreak"


@pytest.mark.parametrize(
    "example_filename",
    [
        "fake-xml.xml",
    ],
)
def test_general_api_returns_400_unsupported_file(example_filename):
    client = TestClient(app)
    test_file = Path("sample-docs") / example_filename
    filetype = "invalid/filetype"
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(test_file), open(test_file, "rb"), filetype))]
    )
    assert response.json() == {
        "detail": f"Unable to process {str(test_file)}: " f"File type {filetype} is not supported."
    }
    assert response.status_code == 400


def test_general_api_returns_400_bad_pdf():
    """
    Verify that we get a 400 for invalid PDF files
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf")
    tmp.write(b"This is not a valid PDF")
    client = TestClient(app)
    response = client.post(
        MAIN_API_ROUTE, files=[("files", (str(tmp.name), open(tmp.name, "rb"), "application/pdf"))]
    )
    assert response.json() == {"detail": f"{tmp.name} does not appear to be a valid PDF"}
    assert response.status_code == 400
    tmp.close()


def test_general_api_returns_503(monkeypatch, mocker):
    """
    When available memory is below the minimum. return a 503, unless our origin ip is 10.{4,5}.x.x
    """
    monkeypatch.setenv("UNSTRUCTURED_MEMORY_FREE_MINIMUM_MB", "30000")

    client = TestClient(app)
    test_file = Path("sample-docs") / "fake-xml.xml"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
    )

    assert response.status_code == 503

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "10.5.0.0"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
    )

    assert response.status_code == 200

    mock_client.host = "10.4.0.0"
    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
    )

    assert response.status_code == 200


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.body = {}
        self.text = ""

    def json(self):
        return self.body


def test_parallel_mode_returns_errors(monkeypatch):
    """
    If we get an error sending a page to the api, bubble it up
    """
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_ENABLED", "true")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_URL", "unused")
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: MockResponse(status_code=500),
    )

    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper.pdf"

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "application/pdf"))],
    )

    assert response.status_code == 500

    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: MockResponse(status_code=400),
    )

    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper.pdf"

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "application/pdf"))],
    )

    assert response.status_code == 400


def test_partition_file_via_api_will_retry(monkeypatch, mocker):
    """
    Verify number of retries with parallel mode
    """
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_ENABLED", "true")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_URL", "unused")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_THREADS", "1")

    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_RETRY_BACKOFF_TIME", "0.1")

    num_calls = 0

    # Return a transient error the first time
    def mock_response(*args, **kwargs):
        nonlocal num_calls
        num_calls += 1

        if num_calls == 1:
            return MockResponse(status_code=500)

        return MockResponse(status_code=200)

    monkeypatch.setattr(
        requests,
        "post",
        mock_response,
    )

    # This needs to be mocked when we return 200
    mocker.patch("prepline_general.api.general.elements_from_json")

    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper-fast.pdf"

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "application/pdf"))],
    )

    assert response.status_code == 200


def test_partition_file_via_api_no_retryable_error_code(monkeypatch, mocker):
    """
    Verify we didn't retry if the error code is not retryable
    """
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_ENABLED", "true")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_URL", "unused")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_MODE_THREADS", "1")

    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("UNSTRUCTURED_PARALLEL_RETRY_BACKOFF_TIME", "0.1")

    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: MockResponse(status_code=401),
    )
    mock_sleep = mocker.patch("time.sleep")
    client = TestClient(app)
    test_file = Path("sample-docs") / "layout-parser-paper.pdf"

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb"), "application/pdf"))],
        data={"pdf_processing_mode": "parallel"},
    )

    assert response.status_code == 401
    assert mock_sleep.call_count == 0


def test_password_protected_pdf():
    """
    Verify we get a 400 error if the PDF is password protected
    """
    client = TestClient(app)
    # a password protected pdf file, password is "password"
    test_file = Path("sample-docs") / "layout-parser-paper-password-protected.pdf"

    response = client.post(
        MAIN_API_ROUTE,
        files=[("files", (str(test_file), open(test_file, "rb")))],
        data={"strategy": "fast"},
    )
    assert response.status_code == 400
    assert response.json() == {
        "detail": f"File: {str(test_file)} is encrypted. Please decrypt it with password."
    }
