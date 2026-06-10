#!/usr/bin/env python3
"""convert.py - Convert a 512-byte-sector disk image to a 4096-byte-sector (4Kn) layout.

Accepts a raw image or a qcow2 image; the output format mirrors the input. For
qcow2 input the image is decompressed to a temporary raw file, converted, and
re-encoded as qcow2 on output (the temporaries are removed afterwards).

The conversion preserves the byte offset and size of every partition, so the
filesystems inside copy across unchanged. The partition table is rebuilt for
4096-byte logical sectors, and the EFI System Partition's FAT is rebuilt at
4096-byte sectors too (its files preserved) -- a verbatim 512-sector FAT records
bytes/sector=512 in its BPB, which a 4Kn device can't mount (the Linux vfat
driver requires the FAT's sector size to match the device's logical block size;
UEFI firmware likewise won't read it). ext4 and the raw BIOS-boot partition are
sector-size-agnostic and copy verbatim. No loop devices, no root.

Usage:
    convert.py <source.img> <output.img>

Requires: python3, sfdisk (util-linux 2.26+), dd (GNU coreutils).
          mtools is required when the image contains an ESP (mformat/mcopy/...).
          qemu-img is additionally required only for qcow2 input.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

SRC_SECTOR = 512
DST_SECTOR = 4096
RATIO = DST_SECTOR // SRC_SECTOR  # 8
HEADROOM = 64 * 1024 * 1024  # tail room for the backup GPT + alignment

# GPT type GUID of an EFI System Partition (its FAT must be rebuilt for 4Kn).
ESP_TYPE_GUID = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f">>> {msg}")


def run(cmd, *, input=None, capture=False, what=None, env=None):
    """Run a command; die with context on failure. Returns stdout if captured."""
    res = subprocess.run(
        cmd,
        input=input.encode() if input is not None else None,
        stdout=subprocess.PIPE if capture else None,
        env=env,
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


def partitions(dump):
    """Yield (offset_bytes, size_bytes, type_guid) for each partition in the dump.

    Byte offsets are identical on source and destination by construction.
    """
    for line in dump.splitlines():
        m_start = re.search(r"start=\s*(\d+)", line)
        m_size = re.search(r"size=\s*(\d+)", line)
        if not (m_start and m_size):
            continue
        m_type = re.search(r"type=\s*([0-9A-Fa-f-]+)", line)
        type_guid = m_type.group(1).upper() if m_type else ""
        yield (
            int(m_start.group(1)) * SRC_SECTOR,
            int(m_size.group(1)) * SRC_SECTOR,
            type_guid,
        )


# Known disk-image container formats, keyed by a magic signature at offset 0.
# A raw image has no such magic, so we only *recognize* containers and otherwise
# treat the input as raw (sfdisk validates the partition table later).
_CONTAINER_MAGICS = (
    (b"QFI\xfb", "qcow2"),
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


def convert_raw(src, dst):
    """Rescale a RAW 512-byte-sector image into a RAW 4096-byte-sector image."""
    src_size = os.path.getsize(src)
    # Round the size up to a whole 4096-byte sector: a 4Kn device's total size
    # must be an exact multiple of its sector size. Adding (DST_SECTOR - 1)
    # before the floor-division turns the truncation into a round-up.
    dst_size = (src_size + HEADROOM + DST_SECTOR - 1) // DST_SECTOR * DST_SECTOR
    info(
        f"Raw image: {src_size} bytes ({SRC_SECTOR}-byte sectors) "
        f"-> {dst_size} bytes ({DST_SECTOR}-byte sectors)"
    )

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
    # Most partitions copy from their source byte range to the same destination
    # byte range; dd's *_bytes flags address by byte while using a large block.
    # The ESP is special-cased: its FAT is rebuilt at 4096-byte sectors instead
    # of copied verbatim (see rebuild_esp).
    info("Copying partition contents...")
    for off, sz, type_guid in partitions(dump):
        if type_guid == ESP_TYPE_GUID:
            info(
                f"  ESP offset={off}B size={sz}B -> rebuilding FAT at "
                f"{DST_SECTOR}-byte sectors"
            )
            rebuild_esp(src, dst, off, sz)
            continue
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


def rebuild_esp(src, dst, off, sz):
    """Rebuild the ESP's FAT at 4096-byte sectors, preserving its files.

    A verbatim-copied ESP keeps bytes/sector=512 in its FAT BPB, which a 4Kn
    device can't mount: the Linux vfat driver needs the FAT's sector size to
    match the device's logical block size (this is where the Ironic deploy agent
    fails when installing the bootloader; UEFI firmware likewise won't read it).
    We extract the source ESP's files, format a fresh FAT with 4096-byte logical
    sectors into a same-sized image, copy the files back, and write it into the
    destination ESP region. Pure file ops -- no mount, no root.
    """
    for cmd in ("mformat", "mcopy", "minfo", "mlabel"):
        if shutil.which(cmd) is None:
            die(f"Missing required command: {cmd} (install mtools to rebuild the ESP)")

    # MTOOLS_SKIP_CHECK relaxes mtools' geometry sanity checks, which otherwise
    # trip on plain partition images that have no CHS geometry.
    env = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}
    outdir = os.path.dirname(os.path.abspath(dst))
    src_esp = _mktemp(outdir, "esp-src-", ".raw")
    dst_esp = _mktemp(outdir, "esp-dst-", ".raw")
    files = tempfile.mkdtemp(dir=outdir, prefix="esp-files-")
    try:
        # Extract the source ESP region into a standalone FAT image.
        run(
            [
                "dd",
                f"if={src}",
                f"of={src_esp}",
                "bs=8M",
                "iflag=skip_bytes,count_bytes",
                f"skip={off}",
                f"count={sz}",
            ],
            what="dd (extract ESP)",
        )

        label = _fat_label(src_esp, env)
        fat32 = _fat_is_fat32(src_esp)
        info(
            f"  source ESP: label={label or '(none)'} "
            f"fat={'32' if fat32 else '12/16'}"
        )

        # Format an identically-sized image with 4096-byte logical sectors.
        # -S 5 => 128 << 5 = 4096-byte sectors; -c 1 keeps 4096-byte clusters
        # (matching the source's). mtools sizes the FS from the image length.
        with open(dst_esp, "wb") as f:
            f.truncate(sz)
        # -T (total sectors) is required: mformat otherwise derives the count by
        # dividing the file size by 512, ignoring -S, and overshoots 8x.
        mfmt = [
            "mformat",
            "-i",
            dst_esp,
            "-S",
            "5",
            "-c",
            "1",
            "-H",
            "0",
            "-T",
            str(sz // DST_SECTOR),
        ]
        if fat32:
            mfmt.append("-F")
        if label:
            mfmt += ["-v", label]
        mfmt.append("::")
        run(mfmt, what="mformat", env=env)
        _verify_esp_geometry(dst_esp, sz, env)

        # Move the file tree across: extract from source, repopulate the new FS.
        entries = _esp_extract(src_esp, files, env)
        if entries:
            run(
                ["mcopy", "-s", "-n", "-m", "-i", dst_esp, *entries, "::/"],
                what="mcopy (populate ESP)",
                env=env,
            )
        else:
            info("  source ESP has no files; new FAT left empty")

        # Write the rebuilt filesystem into the destination ESP region.
        run(
            [
                "dd",
                f"if={dst_esp}",
                f"of={dst}",
                "bs=8M",
                "conv=notrunc,fsync",
                "oflag=seek_bytes",
                f"seek={off}",
            ],
            what="dd (write rebuilt ESP)",
        )
    finally:
        for path in (src_esp, dst_esp):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        shutil.rmtree(files, ignore_errors=True)


def _fat_label(img, env):
    """Read a FAT image's volume label via mlabel, or "" if it has none."""
    out = run(["mlabel", "-i", img, "-s", "::"], capture=True, what="mlabel", env=env)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("Volume label is "):
            return line[len("Volume label is ") :].split(" (")[0].strip()
    return ""


def _fat_is_fat32(img):
    """Return True if the FAT image is FAT32 (per its BPB)."""
    with open(img, "rb") as f:
        bpb = f.read(512)
    root_entries = int.from_bytes(bpb[17:19], "little")
    fatsz16 = int.from_bytes(bpb[22:24], "little")
    return root_entries == 0 and fatsz16 == 0


def _verify_esp_geometry(img, sz, env):
    """Confirm mformat produced a 4096-byte-sector FS spanning the whole image."""
    out = run(["minfo", "-i", img, "::"], capture=True, what="minfo", env=env) or ""
    m_ss = re.search(r"sector size:\s*(\d+)", out)
    if not m_ss or int(m_ss.group(1)) != DST_SECTOR:
        die(f"rebuilt ESP has wrong sector size; minfo said:\n{out}")
    m_big = re.search(r"big size:\s*(\d+)", out)
    m_small = re.search(r"small size:\s*(\d+)", out)
    total = (
        int(m_big.group(1))
        if m_big and int(m_big.group(1))
        else (int(m_small.group(1)) if m_small else 0)
    )
    expected = sz // DST_SECTOR
    if total != expected:
        die(
            f"rebuilt ESP spans {total} sectors, expected {expected} "
            f"(mformat did not size to the partition); minfo:\n{out}"
        )


def _esp_extract(img, dest_dir, env):
    """Extract all top-level entries of a FAT image into dest_dir.

    Returns the list of extracted local paths. An empty ESP yields []."""
    res = subprocess.run(
        ["mcopy", "-s", "-n", "-m", "-i", img, "::/*", dest_dir + "/"],
        stderr=subprocess.PIPE,
        env=env,
    )
    entries = [os.path.join(dest_dir, e) for e in sorted(os.listdir(dest_dir))]
    if res.returncode != 0 and not entries:
        return []  # empty ESP: the glob matched nothing
    if res.returncode != 0:
        die(f"mcopy (extract ESP) failed: {res.stderr.decode().strip()}")
    return entries


def convert_qcow2(src, dst):
    """Convert a qcow2 image: decompress to raw, rescale, re-encode as qcow2."""
    if shutil.which("qemu-img") is None:
        die("Missing required command: qemu-img (needed to handle qcow2 input)")

    outdir = os.path.dirname(os.path.abspath(dst))
    base = os.path.basename(dst)
    tmp_in = _mktemp(outdir, base + ".in-", ".raw")
    tmp_out = _mktemp(outdir, base + ".out-", ".raw")
    try:
        info("Decompressing qcow2 input to a temporary raw image...")
        run(
            ["qemu-img", "convert", "-O", "raw", src, tmp_in],
            what="qemu-img convert (qcow2 -> raw)",
        )
        convert_raw(tmp_in, tmp_out)
        info(f"Re-encoding the 4Kn raw result as qcow2: {dst}")
        if os.path.exists(dst):
            os.remove(dst)
        run(
            ["qemu-img", "convert", "-O", "qcow2", tmp_out, dst],
            what="qemu-img convert (raw -> qcow2)",
        )
    finally:
        for tmp in (tmp_in, tmp_out):
            try:
                os.remove(tmp)
            except FileNotFoundError:
                pass


def _mktemp(directory, prefix, suffix):
    """Create an empty temp file in `directory` and return its path."""
    fd, path = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=suffix)
    os.close(fd)
    return path


def print_notes(dst, out_fmt):
    info("")
    info(f"Done: {dst}")
    info("")
    if out_fmt == "qcow2":
        info(
            f"Write to a 4Kn device with:  qemu-img convert -O raw '{dst}' /dev/<disk>"
        )
    else:
        info(
            f"Write to the 4Kn device with:  dd if='{dst}' of=/dev/<disk> bs=8M conv=fsync"
        )
    info("")
    info("The ESP was rebuilt as a 4096-byte-sector FAT (its files preserved); other")
    info(
        "partitions were copied verbatim. UEFI boot needs no bootloader changes -- GRUB"
    )
    info(
        "finds its config/modules by partition number + path, both unchanged. One note:"
    )
    info(" - Legacy BIOS boot: reinstall the bootloader. The MBR boot code is not")
    info("   carried over and GRUB's embedded core.img sector is a 512-byte LBA:")
    info(
        f"     virt-customize -a '{dst}' --run-command 'grub-install --target=i386-pc /dev/sda'"
    )


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

    fmt = detect_container_format(src)

    if fmt is None:  # raw in -> raw out
        info(f"Source:      {src} (raw, {SRC_SECTOR}-byte sectors)")
        info(f"Destination: {dst} (raw, {DST_SECTOR}-byte sectors)")
        convert_raw(src, dst)
        print_notes(dst, "raw")
    elif fmt == "qcow2":  # qcow2 in -> qcow2 out
        info(f"Source:      {src} (qcow2)")
        info(f"Destination: {dst} (qcow2, 4Kn)")
        convert_qcow2(src, dst)
        print_notes(dst, "qcow2")
    else:
        prog = os.path.basename(sys.argv[0])
        die(
            f"Input is a {fmt} image; automatic handling covers raw and qcow2 "
            f"only. Convert it to raw first:\n"
            f"    qemu-img convert -O raw '{src}' '{src}.raw'\n"
            f"  then re-run:  {prog} '{src}.raw' '{dst}'"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
