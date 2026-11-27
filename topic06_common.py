"""Shared release verification, PE layout and fixture helpers for Topic 06."""
import hashlib
import os
import random
import struct
import subprocess
from urllib.request import urlopen


RELEASE = "https://github.com/ip7z/7zip/releases/download/26.06/7z2606-extra.7z"
PACKAGE_SHA = "396c180f12d2247c24b0b1fcd482c6fc2a2700f61211ffede1061dd971f5e104"
ORIGINAL_SHA = "dd3757f31c97e33776f2590317d4fb12f2da075db3dbb1e3f94d0f2a01d84ffa"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def obtain_original(lab, package_path):
    if package_path:
        package = package_path
    else:
        package = lab / "7z2606-extra.7z"
        with urlopen(RELEASE, timeout=30) as source:
            package.write_bytes(source.read())
    require(sha256(package) == PACKAGE_SHA, "Unexpected Extra package SHA-256.")
    # Windows inbox bsdtar supports 7z containers. Extract just the named member.
    subprocess.run(["tar", "-xf", str(package), "x64/7za.exe"], cwd=lab, check=True)
    return lab / "x64" / "7za.exe"


def generate_input(path):
    rng = random.Random(2606)
    records = [
        (f"VNUK record {i:05d} region={rng.randrange(64):02d} "
         f"category={rng.randrange(15):02d} value={rng.randrange(1000000):06d}\r\n").encode("ascii")
        for i in range(10_000)
    ]
    remaining = 64 * 1024**2
    with path.open("wb") as stream:
        while remaining:
            block = b"".join(rng.choices(records, k=250))[:remaining]
            stream.write(block)
            remaining -= len(block)
    os.utime(path, (1700000000, 1700000000))


def pe_layout(binary):
    """Return (image_base, [(name, va, vsize, raw_ptr, raw_size), ...])."""
    pe = struct.unpack_from("<I", binary, 0x3C)[0]
    if binary[pe:pe + 4] != b"PE\0\0":
        raise RuntimeError("Not a PE file.")
    sections = struct.unpack_from("<H", binary, pe + 6)[0]
    opt_size = struct.unpack_from("<H", binary, pe + 20)[0]
    opt = pe + 24
    if struct.unpack_from("<H", binary, opt)[0] != 0x20B:
        raise RuntimeError("Expected a PE32+ (x64) image.")
    image_base = struct.unpack_from("<Q", binary, opt + 24)[0]
    table = opt + opt_size
    result = []
    for i in range(sections):
        entry = table + 40 * i
        name = binary[entry:entry + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", binary, entry + 8)
        result.append((name, va, vsize, raw_ptr, raw_size))
    return image_base, result


def rva_to_offset(layout, rva):
    for name, va, vsize, raw_ptr, raw_size in layout:
        if va <= rva < va + max(vsize, raw_size):
            return raw_ptr + (rva - va), name
    raise RuntimeError(f"RVA {rva:#x} is not inside any section.")
