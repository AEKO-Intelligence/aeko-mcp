"""The hosted server must not read its own disk from model-supplied HTML.

Local ``<img src>`` references (file://, ./, ../) are refused unless the
operator opts in with AEKO_MCP_ALLOW_LOCAL_IMAGE_FILES for a self-hosted
stdio server. Opted-in reads stay inside a root directory, accept only
regular image files and are size-capped before any bytes are read.
"""

import os

import pytest

from aeko_mcp.tools import store_write

SOURCE = "store-product:integration:1234"
DOMAIN = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def no_backend(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no backend call expected")

    for method in ("get", "post", "put", "patch", "delete"):
        monkeypatch.setattr(store_write.client, method, fail)


@pytest.fixture
def no_disk_reads(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the server must not read local files")

    monkeypatch.setattr(store_write, "_read_local_image", fail)
    monkeypatch.setattr(store_write, "_resolve_local_image", fail)


@pytest.fixture
def opted_in(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv(store_write.LOCAL_IMAGE_FILES_ENV, "1")
    monkeypatch.setenv(store_write.LOCAL_IMAGE_ROOT_ENV, str(root))
    return root


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeHttp:
    puts: list = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def put(self, url, content=None, headers=None):
        _FakeHttp.puts.append({"url": url, "content": content, "headers": headers})
        return _FakeResponse()


@pytest.mark.parametrize(
    "src",
    ["file:///etc/passwd.png", "./photo.png", "../photo.png", "FILE:///dev/zero.png"],
)
def test_local_references_are_refused_by_default(monkeypatch, no_backend, no_disk_reads, src):
    monkeypatch.delenv(store_write.LOCAL_IMAGE_FILES_ENV, raising=False)
    with pytest.raises(store_write._LocalImagesDisabled) as caught:
        store_write._upload_local_images_for_aeko_shop(SOURCE, f'<p><img src="{src}"></p>', DOMAIN)
    assert "aeko_request_media_upload" in str(caught.value)


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsy_opt_in_values_keep_local_reads_disabled(monkeypatch, no_backend, no_disk_reads, value):
    monkeypatch.setenv(store_write.LOCAL_IMAGE_FILES_ENV, value)
    with pytest.raises(store_write._LocalImagesDisabled):
        store_write._upload_local_images_for_aeko_shop(SOURCE, '<img src="./a.png">', DOMAIN)


def test_html_without_local_images_is_returned_unchanged(monkeypatch, no_backend, no_disk_reads):
    monkeypatch.delenv(store_write.LOCAL_IMAGE_FILES_ENV, raising=False)
    html = '<img src="https://cdn.example/a.png"><img src="/static/b.png">'
    assert store_write._upload_local_images_for_aeko_shop(SOURCE, html, None) == html


def test_update_product_description_refuses_local_images_and_writes_nothing(
    monkeypatch, no_backend, no_disk_reads
):
    monkeypatch.delenv(store_write.LOCAL_IMAGE_FILES_ENV, raising=False)
    with pytest.raises(store_write._LocalImagesDisabled):
        store_write.aeko_update_product_description(
            integration_id="integration",
            external_product_id="1234",
            description_html='<img src="file:///app/secret.png">',
            domain_id=DOMAIN,
        )


def test_skip_aeko_shop_never_reads_local_files(monkeypatch, no_disk_reads):
    monkeypatch.delenv(store_write.LOCAL_IMAGE_FILES_ENV, raising=False)
    posted = []
    monkeypatch.setattr(
        store_write.client,
        "post",
        lambda path, json=None: posted.append((path, json)) or {"status": "success"},
    )
    store_write.aeko_update_product_description(
        integration_id="integration",
        external_product_id="1234",
        description_html='<img src="./a.png">',
        skip_aeko_shop=True,
    )
    assert posted[0][1]["description"] == '<img src="./a.png">'


def test_opted_in_upload_reads_file_inside_root(monkeypatch, opted_in):
    (opted_in / "photo.png").write_bytes(b"\x89PNG data")
    monkeypatch.chdir(opted_in)
    presigns = []

    def fake_post(path, json=None):
        presigns.append((path, json))
        return {"upload_url": "https://blob.example/upload", "public_url": "https://cdn.example/photo.png"}

    monkeypatch.setattr(store_write.client, "post", fake_post)
    _FakeHttp.puts = []
    monkeypatch.setattr(store_write.httpx, "Client", _FakeHttp)

    out = store_write._upload_local_images_for_aeko_shop(SOURCE, '<img src="./photo.png">', DOMAIN)

    assert out == '<img src="https://cdn.example/photo.png">'
    path, body = presigns[0]
    assert path == "/api/aeko-shop/media/presign"
    assert body["content_type"] == "image/png"
    assert body["byte_length"] == len(b"\x89PNG data")
    assert body["filename"] == "photo.png"
    assert _FakeHttp.puts[0]["content"] == b"\x89PNG data"


def test_opted_in_file_url_inside_root_is_allowed(monkeypatch, opted_in):
    image = opted_in / "nested" / "a b.webp"
    image.parent.mkdir()
    image.write_bytes(b"webp")
    path, content_type = store_write._resolve_local_image(f"file://{image.as_posix().replace(' ', '%20')}")
    assert path == image.resolve()
    assert content_type == "image/webp"


def test_opted_in_rejects_paths_outside_root(monkeypatch, opted_in, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    monkeypatch.chdir(opted_in)
    for src in (f"file://{outside}", "../outside.png"):
        with pytest.raises(store_write._LocalImageRejected):
            store_write._resolve_local_image(src)


def test_opted_in_rejects_symlink_escaping_root(opted_in, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"png")
    (opted_in / "link.png").symlink_to(outside)
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("./link.png")


def test_opted_in_rejects_non_image_extensions(opted_in):
    (opted_in / "notes.txt").write_text("secret")
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("./notes.txt")


def test_opted_in_rejects_missing_files(opted_in):
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("./missing.png")


def test_opted_in_rejects_remote_file_hosts(opted_in):
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("file://evil.example/share/a.png")


def test_opted_in_rejects_oversized_files_before_reading(monkeypatch, opted_in):
    big = opted_in / "big.png"
    with big.open("wb") as handle:
        handle.truncate(store_write.MAX_LOCAL_IMAGE_BYTES + 1)
    monkeypatch.setattr(
        store_write, "_read_local_image", lambda path: pytest.fail("must not read an oversized file")
    )
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("./big.png")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_opted_in_rejects_non_regular_files(opted_in):
    os.mkfifo(opted_in / "pipe.png")
    with pytest.raises(store_write._LocalImageRejected):
        store_write._resolve_local_image("./pipe.png")


def test_read_is_capped_even_if_file_grows(opted_in):
    image = opted_in / "grow.png"
    image.write_bytes(b"x" * (store_write.MAX_LOCAL_IMAGE_BYTES + 1))
    with pytest.raises(store_write._LocalImageRejected):
        store_write._read_local_image(image)
