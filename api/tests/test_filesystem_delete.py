"""Deleting from storage, which the retention purge is built on.

The contract that matters is idempotence: the purge deletes artifacts and then
records that it did. If it dies in between, the next run deletes the same keys
again, and a "not found" that reads as failure would wedge that run on the first
object a previous attempt already removed.

The opposite failure matters equally. A refusal or an unreachable store must
read as False, because the purge only marks a run purged when every artifact is
confirmed gone; reporting True for a delete that never happened would let
private recordings outlive the retention period while the database says they
are gone.
"""

import pytest
from botocore.exceptions import ClientError
from minio.error import S3Error

from api.services.filesystem.minio import MinioFileSystem
from api.services.filesystem.null import NullFileSystem
from api.services.filesystem.s3 import S3FileSystem


def _minio_error(code: str) -> S3Error:
    return S3Error(code, code, "/x", "req", "host", None)


class _MinioClient:
    def __init__(self, raises=None):
        self.removed = []
        self._raises = raises

    def remove_object(self, bucket, key):
        if self._raises:
            raise self._raises
        self.removed.append((bucket, key))


def _minio(client) -> MinioFileSystem:
    fs = MinioFileSystem(public_endpoint="http://localhost:9000", bucket_name="b")
    fs.client = client
    return fs


@pytest.mark.asyncio
async def test_minio_deletes_the_named_key_in_its_bucket():
    client = _MinioClient()
    assert await _minio(client).adelete_file("recordings/1.wav") is True
    assert client.removed == [("b", "recordings/1.wav")]


@pytest.mark.asyncio
async def test_minio_treats_an_already_missing_key_as_success():
    fs = _minio(_MinioClient(raises=_minio_error("NoSuchKey")))
    assert await fs.adelete_file("gone.wav") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["AccessDenied", "InternalError", "SlowDown"])
async def test_minio_reports_a_real_failure_as_not_deleted(code):
    """If this returned True the purge would mark a run purged while the
    recording still sat in the bucket."""
    fs = _minio(_MinioClient(raises=_minio_error(code)))
    assert await fs.adelete_file("x.wav") is False


class _S3Client:
    def __init__(self, raises=None):
        self.deleted = []
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def delete_object(self, Bucket, Key):
        if self._raises:
            raise self._raises
        self.deleted.append((Bucket, Key))


class _Session:
    def __init__(self, client):
        self._client = client

    def client(self, *args, **kwargs):
        return self._client


def _s3(client) -> S3FileSystem:
    fs = S3FileSystem(bucket_name="b")
    fs.session = _Session(client)
    return fs


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "DeleteObject")


@pytest.mark.asyncio
async def test_s3_deletes_the_named_key_in_its_bucket():
    client = _S3Client()
    assert await _s3(client).adelete_file("recordings/1.wav") is True
    assert client.deleted == [("b", "recordings/1.wav")]


@pytest.mark.asyncio
async def test_s3_treats_an_already_missing_key_as_success():
    assert (
        await _s3(_S3Client(raises=_client_error("NoSuchKey"))).adelete_file("g")
        is True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["AccessDenied", "InternalError", "SlowDown"])
async def test_s3_reports_a_real_failure_as_not_deleted(code):
    assert await _s3(_S3Client(raises=_client_error(code))).adelete_file("x") is False


@pytest.mark.asyncio
async def test_the_null_filesystem_still_fails_loudly():
    """A test that reaches storage by accident must not pass quietly."""
    with pytest.raises(RuntimeError):
        await NullFileSystem().adelete_file("x")
