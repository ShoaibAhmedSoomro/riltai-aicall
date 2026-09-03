"""MinIO storage must hand out signed, expiring URLs -- never public ones.

The bucket used to carry an anonymous policy granting GetObject, PutObject,
DeleteObject and ListBucket to everyone, and both URL helpers returned unsigned
URLs that only worked *because* of it. Since the reverse proxy exposes
/voice-audio/ publicly, every call recording was world-readable and
enumerable.

The subtle part of the fix -- and the reason this test exists -- is WHICH HOST
the URL is signed against. SigV4 covers the Host header, so a URL signed for
the internal endpoint (minio:9000) is rejected the moment a browser sends the
public Host. nginx forwards the original Host untouched, so browser-bound URLs
must be signed for the public endpoint and server-side ones for the internal
endpoint. Getting that backwards yields 403s that look like a storage outage.

Signing is only local because `region` is pinned on both clients. Left unset,
the SDK resolves the bucket region over the network on every presign
(GET /<bucket>?location=) -- on the signing client that means the container
hairpinning an HTTPS request out through the proxy and back to itself for every
playback url. `test_signing_needs_no_network` pins that behaviour by signing
against a deliberately unresolvable host.
"""

from urllib.parse import parse_qs, urlparse

import pytest

from api.services.filesystem.minio import MinioFileSystem

INTERNAL = "minio:9000"
PUBLIC = "https://calls.example.com"


@pytest.fixture
def fs():
    return MinioFileSystem(
        endpoint=INTERNAL,
        access_key="key",
        secret_key="secret-value-long-enough",
        bucket_name="voice-audio",
        secure=False,
        public_endpoint=PUBLIC,
    )


def test_public_endpoint_is_required():
    """A missing public endpoint used to yield URLs pointing at minio:9000."""
    with pytest.raises(ValueError):
        MinioFileSystem(endpoint=INTERNAL, public_endpoint=None)
    with pytest.raises(ValueError):
        # no scheme
        MinioFileSystem(endpoint=INTERNAL, public_endpoint="calls.example.com")


async def test_browser_url_is_signed_for_the_public_host(fs):
    url = await fs.aget_signed_url("org/1/run/2/recording.wav")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.hostname == "calls.example.com", (
        f"signed for {parsed.hostname!r}; a browser sending the public Host "
        "would get a 403 SignatureDoesNotMatch"
    )
    assert parsed.scheme == "https"
    # the whole point: it is signed and it expires
    assert "X-Amz-Signature" in qs
    assert "X-Amz-Credential" in qs
    assert int(qs["X-Amz-Expires"][0]) == 3600


async def test_server_side_url_is_signed_for_the_internal_host(fs):
    url = await fs.aget_signed_url("a/b.wav", use_internal_endpoint=True)
    parsed = urlparse(url)
    assert parsed.netloc == INTERNAL
    assert "X-Amz-Signature" in parse_qs(parsed.query)


async def test_expiration_is_honoured(fs):
    url = await fs.aget_signed_url("a/b.wav", expiration=120)
    assert int(parse_qs(urlparse(url).query)["X-Amz-Expires"][0]) == 120


@pytest.mark.parametrize(
    "key,content_type",
    [
        ("a/b.wav", "audio/wav"),
        ("a/b.mp3", "audio/mpeg"),
        ("a/transcript.txt", "text/plain"),
    ],
)
async def test_force_inline_sets_response_overrides(fs, key, content_type):
    """Recordings and transcripts should render in the browser, not download."""
    qs = parse_qs(urlparse(await fs.aget_signed_url(key, force_inline=True)).query)
    assert qs["response-content-disposition"][0] == "inline"
    assert qs["response-content-type"][0] == content_type


async def test_force_inline_ignored_for_other_types(fs):
    qs = parse_qs(
        urlparse(await fs.aget_signed_url("a/b.csv", force_inline=True)).query
    )
    assert "response-content-disposition" not in qs


async def test_upload_url_is_signed_not_anonymous(fs):
    """This one is the write path -- an unsigned URL let anyone overwrite."""
    url = await fs.aget_presigned_put_url("uploads/leads.csv")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.hostname == "calls.example.com"
    assert "X-Amz-Signature" in qs, "unsigned upload URL: anyone could write here"
    assert int(qs["X-Amz-Expires"][0]) == 900


async def test_signing_needs_no_network(fs):
    """`calls.example.com` does not resolve. If this ever starts failing, the
    region pin was lost and every playback url now costs a hairpin round trip
    to the public endpoint -- which fails outright on NAT without hairpinning."""
    assert fs.region == "us-east-1"
    url = await fs.aget_signed_url("a/b.wav")
    assert url is not None, "presign hit the network instead of signing locally"
    assert "X-Amz-Signature" in url


async def test_urls_are_not_bare_public_paths(fs):
    """Guards against a regression to the old `{public}/{bucket}/{key}` form."""
    for url in (
        await fs.aget_signed_url("a/b.wav"),
        await fs.aget_presigned_put_url("a/b.csv"),
    ):
        assert url != f"{PUBLIC}/voice-audio/a/b.wav"
        assert "?" in url and "X-Amz-Signature" in url
