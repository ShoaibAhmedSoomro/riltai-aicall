import asyncio
import io
from datetime import timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from loguru import logger
from minio import Minio
from minio.error import S3Error

from .base import AsyncReadable, BaseFileSystem


class MinioFileSystem(BaseFileSystem):
    """MinIO implementation of the filesystem interface for OSS users.

    Two endpoints, two different purposes:
    - endpoint (host:port) + secure (bool): used by the MinIO SDK for
      container-to-container calls. The SDK requires these split.
    - public_endpoint (full URL, e.g. "https://example.com"): used verbatim
      when building URLs that browsers will fetch. Required.
    """

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket_name: str = "voice-audio",
        secure: bool = False,
        public_endpoint: Optional[str] = None,
        region: str = "us-east-1",
    ):
        if not public_endpoint:
            raise ValueError(
                "MinioFileSystem requires public_endpoint (set MINIO_PUBLIC_ENDPOINT). "
                "Expected a full URL with scheme, e.g. 'http://localhost:9000' or 'https://example.com'."
            )
        if not (
            public_endpoint.startswith("http://")
            or public_endpoint.startswith("https://")
        ):
            raise ValueError(
                f"MINIO_PUBLIC_ENDPOINT must include a scheme (http:// or https://), got: {public_endpoint!r}"
            )

        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self.public_endpoint = public_endpoint.rstrip("/")
        self.secure = secure
        self.access_key = access_key
        self.secret_key = secret_key

        self.region = region

        # `region` is pinned on BOTH clients on purpose. Without it the SDK
        # resolves the bucket's region over the network on every presign
        # (GET /<bucket>?location=). On the signing client that request would
        # go to the *public* endpoint -- i.e. the container hairpinning an
        # HTTPS call out through the proxy and back to itself on every
        # recording playback, which is slow and outright fails on cloud NAT
        # setups that don't support hairpinning. MinIO reports us-east-1;
        # pinning it makes signing purely local.
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )

        # Second client used ONLY to sign URLs that browsers will fetch.
        #
        # SigV4 covers the Host header, so a URL signed against the internal
        # endpoint (minio:9000) is rejected when the browser sends the public
        # Host. The reverse proxy forwards the original Host untouched
        # (`proxy_set_header Host $host` on /voice-audio/ in
        # deploy/templates/nginx.remote.conf.template), so signing against the
        # public endpoint is what actually validates.
        public = urlparse(self.public_endpoint)
        self._signing_client = Minio(
            public.netloc,
            access_key=access_key,
            secret_key=secret_key,
            secure=(public.scheme == "https"),
            region=region,
        )

        # Ensure the bucket exists and is PRIVATE.
        #
        # This previously installed an anonymous policy granting GetObject,
        # PutObject, DeleteObject and ListBucket to Principal "*" -- on every
        # init, with its own comment saying not to use it in production. Since
        # the proxy exposes /voice-audio/ publicly, that made every call
        # recording world-readable AND enumerable via ?list-type=2. Recordings
        # are now reached exclusively through time-limited presigned URLs, so
        # any inherited public policy is actively removed rather than just
        # left unset.
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
            try:
                self.client.delete_bucket_policy(self.bucket_name)
                logger.info(
                    f"MinIO bucket '{self.bucket_name}': anonymous access policy removed; "
                    "objects are served via presigned URLs only"
                )
            except S3Error as e:
                # NoSuchBucketPolicy just means it was already private.
                if e.code not in ("NoSuchBucketPolicy", "NoSuchBucketPolicyException"):
                    raise
        except Exception as e:
            logger.warning(f"MinIO bucket setup: {e}")

    async def acreate_file(self, file_path: str, content: AsyncReadable) -> bool:
        try:
            data = await content.read()

            def _put():
                # The MinIO SDK requires a stream with .read(), not raw bytes.
                self.client.put_object(
                    self.bucket_name,
                    file_path,
                    data=io.BytesIO(data),
                    length=len(data),
                )

            await asyncio.to_thread(_put)
            return True
        except S3Error:
            return False

    async def aupload_file(self, local_path: str, destination_path: str) -> bool:
        try:

            def _fput():
                self.client.fput_object(self.bucket_name, destination_path, local_path)

            await asyncio.to_thread(_fput)
            return True
        except S3Error:
            return False

    # Inline-viewable types, mirroring the S3 backend's force_inline handling
    # so a transcript or recording opens in the browser instead of downloading.
    _INLINE_CONTENT_TYPES = {
        ".txt": "text/plain",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }

    async def aget_signed_url(
        self,
        file_path: str,
        expiration: int = 3600,
        force_inline: bool = False,
        use_internal_endpoint: bool = False,
    ) -> Optional[str]:
        """Presigned GET url. Was an unsigned public url before the bucket was
        made private; it now carries a real signature and expires."""
        response_headers = None
        if force_inline:
            for suffix, content_type in self._INLINE_CONTENT_TYPES.items():
                if file_path.endswith(suffix):
                    response_headers = {
                        "response-content-type": content_type,
                        "response-content-disposition": "inline",
                    }
                    break

        # Server-side fetches go straight to minio:9000 and must be signed for
        # that host; browser-bound URLs are signed for the public host.
        client = self.client if use_internal_endpoint else self._signing_client
        try:

            def _presign():
                return client.presigned_get_object(
                    self.bucket_name,
                    file_path,
                    expires=timedelta(seconds=expiration),
                    response_headers=response_headers,
                )

            return await asyncio.to_thread(_presign)
        except Exception as e:
            logger.error(f"Error generating MinIO presigned GET url: {e}")
            return None

    async def aget_file_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get MinIO object metadata."""
        try:

            def _stat():
                return self.client.stat_object(self.bucket_name, file_path)

            stat = await asyncio.to_thread(_stat)
            return {
                "size": stat.size,
                "created_at": stat.last_modified,
                "modified_at": stat.last_modified,
                "etag": stat.etag.strip('"') if stat.etag else None,
                "content_type": stat.content_type,
                "storage_class": None,  # MinIO doesn't have storage classes like S3
            }
        except S3Error:
            return None

    async def aget_presigned_put_url(
        self,
        file_path: str,
        expiration: int = 900,
        content_type: str = "text/csv",
        max_size: int = 10_485_760,
    ) -> Optional[str]:
        """Presigned PUT url for direct browser upload.

        Previously an unsigned url that worked only because the bucket granted
        anonymous PutObject to everyone -- which also let anyone overwrite or
        delete any object. Signed against the public host for the same reason
        as aget_signed_url.

        ponytail: max_size is not enforced here. The MinIO SDK's presigned PUT
        cannot bound the body length (that needs a POST policy). Callers still
        validate size server-side; upgrade to presigned_post_policy if
        client-side enforcement is ever required.
        """
        try:

            def _presign():
                return self._signing_client.presigned_put_object(
                    self.bucket_name,
                    file_path,
                    expires=timedelta(seconds=expiration),
                )

            return await asyncio.to_thread(_presign)
        except Exception as e:
            logger.error(f"Error generating MinIO presigned PUT url: {e}")
            return None

    async def adownload_file(self, source_path: str, local_path: str) -> bool:
        """Download a file from MinIO to local path."""
        try:

            def _fget():
                self.client.fget_object(self.bucket_name, source_path, local_path)

            await asyncio.to_thread(_fget)
            return True
        except S3Error:
            return False

    async def acopy_file(self, source_path: str, destination_path: str) -> bool:
        """Copy a file within MinIO (server-side copy)."""
        try:
            from minio.commonconfig import CopySource

            def _copy():
                self.client.copy_object(
                    self.bucket_name,
                    destination_path,
                    CopySource(self.bucket_name, source_path),
                )

            await asyncio.to_thread(_copy)
            return True
        except S3Error:
            return False
