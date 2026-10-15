"""Install a pinned official CloudGuard binary; Python standard library only."""
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import urllib.error
import zipfile

REPOSITORY = "mjraraujo/cloudguard-action"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_BINARY = 128 * 1024 * 1024


def release_identity(version, repository=REPOSITORY):
    if repository != REPOSITORY:
        raise ValueError("release repository must be mjraraujo/cloudguard-action")
    if not TAG.fullmatch(version):
        raise ValueError("version must be an exact stable tag such as v1.2.3")
    return repository, version[1:]


def target(os_name=None, architecture=None):
    os_name = os_name or os.environ.get("RUNNER_OS") or platform.system()
    architecture = architecture or os.environ.get("RUNNER_ARCH") or platform.machine()
    system = {"linux": "linux", "macos": "darwin", "darwin": "darwin", "windows": "windows"}.get(os_name.lower())
    arch = {"x64": "amd64", "x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(architecture.lower())
    if not system or not arch:
        raise ValueError("supported runners are Linux/macOS/Windows on x64/arm64")
    return system, arch


def archive_name(version, system, arch):
    _, number = release_identity(version)
    system, arch = target(system, arch)
    extension = "zip" if system == "windows" else "tar.gz"
    return "cloudguard-finops_{}_{}_{}.{}".format(number, system, arch, extension)


def download(url, destination, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "CloudGuard-Action/1"})
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise ValueError("release download returned HTTP {}".format(status)) from None
    with response, open(destination, "wb") as output:
        if response.status != 200:
            raise ValueError("release download returned HTTP {}".format(response.status))
        count = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            if count > limit:
                raise ValueError("release asset exceeds size limit")
            output.write(block)


def checksum_for(manifest, filename):
    records = {}
    for line in manifest.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or not SHA256.fullmatch(fields[0]):
            raise ValueError("invalid release checksum manifest")
        name = fields[1].removeprefix("*")
        if name in records:
            raise ValueError("duplicate filename in release checksum manifest")
        records[name] = fields[0].lower()
    if filename not in records:
        raise ValueError("archive is absent from release checksum manifest")
    return records[filename]


def safe_member(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe path in release archive")
    return path


def extract_binary(archive, destination, system):
    expected = "cloudguard.exe" if system == "windows" else "cloudguard"
    candidates = []
    if system == "windows":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                path = safe_member(member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode) or member.flag_bits & 1:
                    raise ValueError("links and encrypted files are forbidden in release archives")
                if member.file_size > MAX_BINARY:
                    raise ValueError("archive member exceeds size limit")
                if path.as_posix() == expected and not member.is_dir():
                    candidates.append(member)
            if len(candidates) != 1:
                raise ValueError("archive must contain exactly one top-level CloudGuard binary")
            with bundle.open(candidates[0]) as source, open(destination, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                path = safe_member(member.name)
                if not (member.isfile() or member.isdir()):
                    raise ValueError("links and special files are forbidden in release archives")
                if member.size > MAX_BINARY:
                    raise ValueError("archive member exceeds size limit")
                if path.as_posix() == expected and member.isfile():
                    candidates.append(member)
            if len(candidates) != 1:
                raise ValueError("archive must contain exactly one top-level CloudGuard binary")
            with bundle.extractfile(candidates[0]) as source, open(destination, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
    if not destination.stat().st_size:
        raise ValueError("CloudGuard binary is empty")
    destination.chmod(0o755)


def install(version, directory, system=None, arch=None, expected_sha256="", fetch=download):
    repository, _ = release_identity(version)
    system, arch = target(system, arch)
    filename = archive_name(version, system, arch)
    if expected_sha256 and not SHA256.fullmatch(expected_sha256):
        raise ValueError("archive-sha256 must contain exactly 64 hexadecimal characters")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cloudguard-install-", dir=directory) as temporary:
        staging = Path(temporary)
        root = "https://github.com/{}/releases/download/{}".format(repository, version)
        manifest = staging / "checksums.txt"
        archive = staging / filename
        fetch(root + "/checksums.txt", manifest, 2 * 1024 * 1024)
        expected = checksum_for(manifest.read_text(encoding="utf-8"), filename)
        if expected_sha256 and not hmac.compare_digest(expected, expected_sha256.lower()):
            raise ValueError("release checksum differs from independently pinned archive-sha256")
        fetch(root + "/" + filename, archive, MAX_ARCHIVE)
        digest = hashlib.sha256()
        with archive.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if not hmac.compare_digest(digest.hexdigest(), expected):
            raise ValueError("release archive SHA256 mismatch")
        binary = staging / ("cloudguard.exe" if system == "windows" else "cloudguard")
        extract_binary(archive, binary, system)
        final = directory / binary.name
        os.replace(binary, final)
        return final.resolve()


def main():
    version = os.environ.get("CLOUDGUARD_VERSION", "")
    system, arch = target()
    release_identity(version)
    root = Path(os.environ["RUNNER_TEMP"]) / "cloudguard" / version / (system + "_" + arch)
    executable = install(version, root, system, arch, os.environ.get("CLOUDGUARD_ARCHIVE_SHA256", ""))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("executable={}\n".format(executable))
    print("Installed CloudGuard {} for {}/{} after SHA256 verification".format(version, system, arch))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print("CloudGuard installation failed: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
