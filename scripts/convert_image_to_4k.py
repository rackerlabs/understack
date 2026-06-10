#!/usr/bin/env python3
"""convert.py - Convert a 512-byte-sector raw disk image to a 4096-byte-sector
(4Kn) layout, producing a new raw image.

The new image preserves the byte offset and size of every partition, so the
filesystems inside copy across unchanged. Only the partition table is rebuilt
for 4096-byte logical sectors. Works directly on image files: no loop devices,
no root.

Usage:
    convert.py <source.img> <output.img>

Requires: python3, sfdisk (util-linux 2.26+), dd (GNU coreutils).
This is a Python port of convert.sh; it shells out to sfdisk/dd for the table
write and the copy, and does the sizing and LBA rescaling in Python.
"""

import os
import re
import shutil
import subprocess
import sys

SRC_SECTOR = 512
DST_SECTOR = 4096
RATIO = DST_SECTOR // SRC_SECTOR  # 8
HEADROOM = 64 * 1024 * 1024  # tail room for the backup GPT + alignment


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f">>> {msg}")


def run(cmd, *, input=None, capture=False, what=None):
    """Run a command; die with context on failure. Returns stdout if captured."""
    res = subprocess.run(
        cmd,
        input=input.encode() if input is not None else None,
        stdout=subprocess.PIPE if capture else None,
    )
    if res.returncode != 0:
        die(f"{what or cmd[0]} failed (exit {res.returncode})")
    return res.stdout.decode() if capture else None


def rescale_value(match):
    """Divide a `start=`/`size=` LBA by RATIO, refusing non-4K-alignable values."""
    key, num = match.group(1), int(match.group(2))
    if num % RATIO != 0:
        die(
            f"{key}={num} is not divisible by {RATIO}: image is not "
            f"{DST_SECTOR}-byte-sector alignable"
        )
    return f"{key}={num // RATIO}"


def transform_table(dump):
    """Rebuild the sfdisk dump for 4096-byte sectors."""
    out = []
    for line in dump.splitlines():
        if re.match(r"^(first-lba|last-lba|device):", line):
            continue
        if line.startswith("sector-size:"):
            out.append(f"sector-size: {DST_SECTOR}")
            continue
        if "start=" in line:
            line = re.sub(r"(start|size)=\s*(\d+)", rescale_value, line)
        out.append(line)
    return "\n".join(out) + "\n"


def partition_ranges(dump):
    """Yield (offset_bytes, size_bytes) for each partition in the source dump.

    Byte offsets are identical on source and destination by construction.
    """
    for line in dump.splitlines():
        m_start = re.search(r"start=\s*(\d+)", line)
        m_size = re.search(r"size=\s*(\d+)", line)
        if m_start and m_size:
            yield int(m_start.group(1)) * SRC_SECTOR, int(m_size.group(1)) * SRC_SECTOR


# Known disk-image container formats, keyed by a magic signature at offset 0.
# A raw image has no such magic, so we only *reject* recognized containers and
# otherwise treat the input as raw (sfdisk validates the partition table later).
_CONTAINER_MAGICS = (
    (b"QFI\xfb", "qcow2/qcow"),
    (b"KDMV", "vmdk (monolithicSparse)"),
    (b"# Disk DescriptorFile", "vmdk (descriptor)"),
    (b"vhdxfile", "vhdx"),
    (b"connectix", "vhd"),
)


def detect_container_format(path):
    """Return the name of a recognized non-raw image format, or None if raw."""
    with open(path, "rb") as f:
        head = f.read(32)
    for magic, name in _CONTAINER_MAGICS:
        if head.startswith(magic):
            return name
    return None


def main(argv):
    if len(argv) != 2:
        die(f"Usage: {os.path.basename(sys.argv[0])} <source.img> <output.img>")
    src, dst = argv
    if not os.path.isfile(src):
        die(f"Source image not found: {src}")
    if os.path.abspath(src) == os.path.abspath(dst):
        die("Source and destination must differ")
    for cmd in ("sfdisk", "dd"):
        if shutil.which(cmd) is None:
            die(f"Missing required command: {cmd}")

    # We operate on raw images, whose partitions sit at literal byte offsets.
    # A qcow2/vmdk/etc. container would make sfdisk read container metadata as a
    # (bogus) partition table and os.path.getsize report the compressed size.
    fmt = detect_container_format(src)
    if fmt:
        prog = os.path.basename(sys.argv[0])
        die(
            f"Input looks like a {fmt} image, not raw. Convert it first:\n"
            f"    qemu-img convert -O raw '{src}' '{src}.raw'\n"
            f"  then re-run:\n"
            f"    {prog} '{src}.raw' '{dst}'"
        )

    src_size = os.path.getsize(src)
    # Round the size up to a whole 4096-byte sector: a 4Kn device's total size
    # must be an exact multiple of its sector size. Adding (DST_SECTOR - 1)
    # before the floor-division turns the truncation into a round-up.
    dst_size = (src_size + HEADROOM + DST_SECTOR - 1) // DST_SECTOR * DST_SECTOR
    info(f"Source:      {src} ({src_size} bytes, {SRC_SECTOR}-byte sectors)")
    info(f"Destination: {dst} ({dst_size} bytes, {DST_SECTOR}-byte sectors)")

    # -- Rebuild the partition table for 4096-byte sectors --------------------
    # `sfdisk -d` dumps start=/size= in source-sector (512) units. Dividing each
    # by RATIO keeps every partition at the same *byte* offset on a 4096-byte
    # device. first-lba/last-lba and the source device: line are dropped so
    # sfdisk recomputes them for the destination geometry.
    info(f"Rescaling partition table ({SRC_SECTOR} -> {DST_SECTOR} byte sectors)...")
    dump = run(["sfdisk", "-d", src], capture=True, what="sfdisk -d")
    table = transform_table(dump)

    # -- Create the destination image (only once the table parses cleanly) ----
    if os.path.exists(dst):
        os.remove(dst)
    with open(dst, "wb") as f:  # sparse allocation
        f.truncate(dst_size)

    run(
        ["sfdisk", "--sector-size", str(DST_SECTOR), dst],
        input=table,
        capture=True,
        what="sfdisk (write table)",
    )
    info("New partition table:")
    for line in table.splitlines():
        print(f"    {line}")

    # -- Copy partition contents ----------------------------------------------
    # Each partition copies from its source byte range to the same destination
    # byte range; dd's *_bytes flags address by byte while using a large block.
    info("Copying partition contents...")
    for off, sz in partition_ranges(dump):
        info(f"  offset={off}B size={sz}B")
        run(
            [
                "dd",
                f"if={src}",
                f"of={dst}",
                "bs=8M",
                "conv=notrunc,fsync",
                "iflag=skip_bytes,count_bytes",
                "oflag=seek_bytes",
                f"skip={off}",
                f"seek={off}",
                f"count={sz}",
                "status=progress",
            ],
            what="dd (copy partition)",
        )

    # -- Verify ---------------------------------------------------------------
    info("Verifying destination GPT...")
    run(
        ["sfdisk", "--sector-size", str(DST_SECTOR), "--verify", dst],
        what="sfdisk --verify",
    )

    info("")
    info(f"Done: {dst}")
    info("")
    info(
        f"Write to the 4Kn device with:  dd if='{dst}' of=/dev/<disk> bs=8M conv=fsync"
    )
    info("")
    info("Partition contents are copied verbatim; filesystems and boot code are not")
    info("modified beyond rewriting the partition table. Two things to know:")
    info(" - UEFI boot: no bootloader changes needed. The ESP is preserved and GRUB")
    info("   finds its config/modules by partition number + path, both unchanged.")
    info(
        "   But the ESP's FAT was made with 512-byte logical sectors (BPB bytes/sector"
    )
    info("   = 512); some 4Kn firmware refuses that. If the ESP won't mount after")
    info(
        "   deploy, rebuild it for 4096-byte sectors (mkfs.vfat -F32 -S 4096) + restore."
    )
    info(" - Legacy BIOS boot: reinstall the bootloader. The MBR boot code is not")
    info("   carried over and GRUB's embedded core.img sector is a 512-byte LBA:")
    info(
        f"     virt-customize -a '{dst}' --run-command 'grub-install --target=i386-pc /dev/sda'"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
