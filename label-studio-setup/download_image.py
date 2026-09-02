"""Download the public official Label Studio image into a Docker-load archive.

Uses standard HTTPS with certificate validation and TLS 1.2 for this process only.
No Docker configuration changes and no local files are uploaded.
Registry credentials are anonymous, scoped, held in memory, and never logged.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import ssl
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "heartexlabs/label-studio"
REGISTRY = "https://registry-1.docker.io"
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def log(message):
    print(message, flush=True)


def error_hint(error):
    reason = getattr(error, "reason", error)
    parts = [type(error).__name__, type(reason).__name__]
    if isinstance(error, urllib.error.HTTPError):
        parts.append(f"HTTP {error.code}")
    if isinstance(reason, ssl.SSLError):
        parts.append(str(reason.reason))
    return "/".join(parts)


def verify(data, digest):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Unsupported or malformed digest")
    if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Content digest mismatch")


def file_digest(path):
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    last_host = "registry-1.docker.io"

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("Refusing a non-HTTPS redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        self.last_host = urllib.parse.urlsplit(newurl).hostname
        return redirected


class RegistryClient:
    def __init__(self, proxy):
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        self.redirect = SafeRedirect()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
            urllib.request.HTTPSHandler(context=context), self.redirect)
        self.token = None
        self.token_time = 0

    def authorize(self):
        url = "https://auth.docker.io/token?" + urllib.parse.urlencode({
            "service": "registry.docker.io",
            "scope": f"repository:{REPOSITORY}:pull",
        })
        with self.opener.open(url, timeout=30) as response:
            result = json.load(response)
        self.token = result["token"]
        self.token_time = time.monotonic()

    def open(self, path, extra_headers=None):
        if not self.token or time.monotonic() - self.token_time > 180:
            self.authorize()
        headers = {"Authorization": "Bearer " + self.token, "Accept": ACCEPT}
        headers.update(extra_headers or {})
        self.redirect.last_host = "registry-1.docker.io"
        request = urllib.request.Request(REGISTRY + path, headers=headers)
        try:
            return self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                self.token = None
            raise

    def fetch(self, path, expected=None):
        for attempt in range(1, 6):
            try:
                with self.open(path) as response:
                    data = response.read()
                    declared = response.headers.get("Docker-Content-Digest")
                if declared:
                    verify(data, declared)
                if expected:
                    verify(data, expected)
                return data
            except (OSError, ValueError) as error:
                log(f"Metadata retry {attempt}/5 ({error_hint(error)} at {self.redirect.last_host})")
                if attempt == 5:
                    raise RuntimeError("Official registry metadata download failed") from None
                time.sleep(attempt * 2)

    def blob(self, descriptor, folder, number, total):
        digest, size = descriptor["digest"], descriptor["size"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid layer digest")
        target = folder / digest.split(":")[1]
        if target.exists() and target.stat().st_size == size and file_digest(target) == digest:
            log(f"Layer {number}/{total}: cached and verified")
            return target
        partial = target.with_suffix(".part")
        for attempt in range(1, 6):
            try:
                offset = partial.stat().st_size if partial.exists() else 0
                if offset == size and file_digest(partial) == digest:
                    partial.replace(target)
                    return target
                if offset >= size:
                    with partial.open("wb"):
                        pass
                    offset = 0
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with self.open(f"/v2/{REPOSITORY}/blobs/{digest}", headers) as response:
                    if offset and response.status == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise ValueError("Unexpected resumed download range")
                        mode = "ab"
                    else:
                        offset, mode = 0, "wb"
                    last_report = time.monotonic()
                    with partial.open(mode) as stream:
                        while chunk := response.read(1024 * 1024):
                            stream.write(chunk)
                            offset += len(chunk)
                            if offset > size:
                                raise ValueError("Downloaded layer exceeds declared size")
                            if time.monotonic() - last_report >= 10:
                                log(f"Layer {number}/{total}: {offset/1048576:.1f}/{size/1048576:.1f} MiB")
                                last_report = time.monotonic()
                if offset != size or file_digest(partial) != digest:
                    raise ValueError("Layer size or SHA-256 mismatch")
                partial.replace(target)
                log(f"Layer {number}/{total}: {size/1048576:.1f} MiB verified")
                return target
            except (OSError, ValueError) as error:
                log(f"Layer {number}/{total}: retry {attempt}/5 ({error_hint(error)} at {self.redirect.last_host})")
                if attempt == 5:
                    raise RuntimeError(f"Layer {number} download failed; partial cache retained") from None
                time.sleep(attempt * 2)


def add_bytes(archive, name, content):
    item = tarfile.TarInfo(name)
    item.size = len(content)
    item.mode = 0o644
    archive.addfile(item, io.BytesIO(content))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    cache = root / "image-cache"
    cache.mkdir(exist_ok=True)
    client = RegistryClient(args.proxy)
    metadata_file = root / "image-source.json"
    if metadata_file.exists():
        saved = json.loads(metadata_file.read_text("utf-8"))
        digest = saved["manifest_digest"]
        manifest_data = client.fetch(f"/v2/{REPOSITORY}/manifests/{digest}", digest)
    else:
        index_data = client.fetch(f"/v2/{REPOSITORY}/manifests/latest")
        index = json.loads(index_data)
        if "manifests" in index:
            candidates = [item for item in index["manifests"]
                          if item.get("platform", {}).get("os") == "linux"
                          and item.get("platform", {}).get("architecture") == "amd64"]
            if len(candidates) != 1:
                raise ValueError("Expected one Linux AMD64 image")
            digest = candidates[0]["digest"]
            manifest_data = client.fetch(f"/v2/{REPOSITORY}/manifests/{digest}", digest)
        else:
            manifest_data = index_data
            digest = "sha256:" + hashlib.sha256(manifest_data).hexdigest()
        (root / "official-index.json").write_bytes(index_data)
    manifest = json.loads(manifest_data)
    config_descriptor = manifest["config"]
    config_data = client.fetch(f"/v2/{REPOSITORY}/blobs/{config_descriptor['digest']}", config_descriptor["digest"])
    config = json.loads(config_data)
    if config["os"] != "linux" or config["architecture"] != "amd64":
        raise ValueError("Wrong image platform")
    layers = manifest["layers"]
    if len(layers) != len(config["rootfs"]["diff_ids"]):
        raise ValueError("Layer count mismatch")
    size = sum(layer["size"] for layer in layers)
    metadata = {"repository": REPOSITORY, "tag": "latest", "platform": "linux/amd64",
                "manifest_digest": digest, "config_digest": config_descriptor["digest"],
                "compressed_bytes": size, "layers": len(layers), "tls": "TLS1.2 with certificate verification"}
    metadata_file.write_text(json.dumps(metadata, indent=2), "utf-8")
    (root / "official-manifest.json").write_bytes(manifest_data)
    (root / "official-config.json").write_bytes(config_data)
    log(json.dumps(metadata, indent=2))
    if args.describe:
        return
    if shutil.disk_usage(root).free < max(size * 12, 10 * 1024**3):
        raise RuntimeError("Insufficient free space for download and unpacking")
    downloaded = [client.blob(layer, cache, i, len(layers)) for i, layer in enumerate(layers, 1)]
    archive_path = root / "label-studio-linux-amd64.tar"
    temporary_archive = archive_path.with_suffix(".tar.part")
    config_name = config_descriptor["digest"].split(":")[1] + ".json"
    archive_layers = []
    with tarfile.open(temporary_archive, "w", format=tarfile.PAX_FORMAT) as archive:
        add_bytes(archive, config_name, config_data)
        for i, (layer, compressed, expected_diff) in enumerate(zip(layers, downloaded, config["rootfs"]["diff_ids"]), 1):
            unpacked = compressed.with_suffix(".layer.tar")
            if not unpacked.exists() or file_digest(unpacked) != expected_diff:
                media_type = layer["mediaType"]
                if media_type.endswith("+gzip") or media_type.endswith(".gzip"):
                    source = gzip.open(compressed, "rb")
                elif media_type.endswith(".tar"):
                    source = compressed.open("rb")
                else:
                    raise ValueError("Unsupported layer compression")
                with source, unpacked.open("wb") as dest:
                    shutil.copyfileobj(source, dest, 1024 * 1024)
                if file_digest(unpacked) != expected_diff:
                    raise ValueError("Uncompressed layer digest mismatch")
            arcname = compressed.name + "/layer.tar"
            archive.add(unpacked, arcname=arcname, recursive=False)
            archive_layers.append(arcname)
            log(f"Archive layer {i}/{len(layers)} verified and added")
        add_bytes(archive, "manifest.json", json.dumps([{
            "Config": config_name, "RepoTags": [REPOSITORY + ":latest"], "Layers": archive_layers
        }]).encode())
    temporary_archive.replace(archive_path)
    metadata["archive_sha256"] = file_digest(archive_path)
    metadata["archive_bytes"] = archive_path.stat().st_size
    metadata_file.write_text(json.dumps(metadata, indent=2), "utf-8")
    log(f"READY: {archive_path}")
    log(f"Archive SHA-256: {metadata['archive_sha256']}")


if __name__ == "__main__":
    main()
