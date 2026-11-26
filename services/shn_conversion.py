"""Losslessly convert Shorten recordings with optional source archiving."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from services.verification import VerificationFailed, verify_shn, verify_show

CONVERSION_NOTE_PREFIX = "SHN-to-FLAC-"
SOURCE_ARCHIVE = "_shn_source"


def conversion_marker(folder, shnid):
    identifier = shnid if shnid is not None else "unknown-SHNID"
    return folder / f"{CONVERSION_NOTE_PREFIX}{identifier}.txt"


def _manifest_renames(folder):
    return [(path, path.with_suffix(".md5.shn-source")) for path in sorted(folder.glob("*.md5"))
            if path.is_file()]


def describe_conversion(folder, shnid, compression_level, paranoid):
    yield f"  Encode and verify FLAC at compression level {compression_level}"
    for source in sorted(folder.glob("*.shn")):
        yield f"  {source.name} -> {source.with_suffix('.flac').name}"
    if paranoid:
        yield f"  Keep original files and copy the original fileset to {SOURCE_ARCHIVE}"
    else:
        yield "  Remove source SHNs after successful verification"
        for source, destination in _manifest_renames(folder):
            yield f"  Rename {source.name} to {destination.name}"
    yield f"  Write {conversion_marker(folder, shnid).name}"


def _pcm_hash(ffmpeg, path, input_format):
    try:
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
             "-f", input_format, "-i", str(path), "-map", "0:a:0",
             "-c:a", "pcm_s32le", "-f", "hash", "-hash", "sha256", "-"],
            capture_output=True, timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationFailed(f"{path.name}: could not compare decoded audio") from exc
    if result.returncode or not result.stdout.startswith(b"SHA256="):
        raise VerificationFailed(f"{path.name}: could not hash decoded audio")
    return result.stdout.strip()


def _copy_verified(source, destination):
    shutil.copy2(source, destination)
    with open(source, "rb") as original, open(destination, "rb") as backup:
        if hashlib.file_digest(original, "sha256").digest() != hashlib.file_digest(backup, "sha256").digest():
            raise VerificationFailed(f"{source}: source archive copy differs from original")


def convert_shn(
    folder, ffmpeg, flac, shnid, *, compression_level=8, paranoid=False, generated_files=(), progress=None,
):
    def report(message):
        if progress:
            progress(message)

    marker = conversion_marker(folder, shnid)
    archive = folder / SOURCE_ARCHIVE
    manifest_renames = [] if paranoid else _manifest_renames(folder)
    for _, destination in manifest_renames:
        if destination.exists() or destination.is_symlink():
            raise VerificationFailed(f"{destination.name} already exists")
    if paranoid and (archive.exists() or archive.is_symlink()):
        raise VerificationFailed(f"{SOURCE_ARCHIVE} already exists")
    with TemporaryDirectory(prefix=".shn-conversion-", dir=folder) as directory:
        staging = Path(directory)
        staged_archive = staging / SOURCE_ARCHIVE
        if paranoid:
            report(f"Copying and checking the original fileset for {SOURCE_ARCHIVE}")
            def ignore_generated(path, names):
                return [name for name in names if Path(path) / name in {staging, *generated_files}]

            shutil.copytree(
                folder, staged_archive, ignore=ignore_generated, copy_function=_copy_verified,
            )
        source_folder = staged_archive if paranoid else folder
        notes = verify_shn(source_folder, progress=progress)
        sources = sorted(source_folder.glob("*.shn"))
        mappings = []
        for index, source in enumerate(sources, 1):
            report(f"Converting SHN {index}/{len(sources)} — {source.name}")
            destination = staging / source.with_suffix(".flac").name
            try:
                result = subprocess.run(
                    [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
                     "-n", "-f", "shn", "-i", str(source), "-map", "0:a:0", "-c:a", "flac",
                     "-compression_level", str(compression_level), str(destination)],
                    capture_output=True, timeout=300,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VerificationFailed(f"{source.name}: could not complete SHN conversion") from exc
            if result.returncode or not destination.is_file():
                diagnostic = result.stderr.decode(errors="replace").strip()
                raise VerificationFailed(f"{source.name}: FFmpeg conversion failed: {diagnostic}")
            if paranoid:
                if _pcm_hash(ffmpeg, source, "shn") != _pcm_hash(ffmpeg, destination, "flac"):
                    raise VerificationFailed(f"{source.name}: decoded SHN and FLAC audio differ")
            mappings.append(f"{source.name} -> {destination.name}")

        verification = verify_show(staging, flac, progress=progress)
        staged_marker = staging / marker.name
        staged_marker.write_text(
            "\n".join([
                f"Lossless SHN to FLAC re-encode for {folder.name}",
                f"SHNID: {shnid if shnid is not None else 'unknown'}",
                "Encoded with FFmpeg. Original MD5 manifests and companion files retained.",
                "Original SHNs retained." if paranoid else "Original SHNs removed after successful verification.",
                *(f"Renamed original checksum manifest {source.name} to {destination.name}."
                  for source, destination in manifest_renames),
                f"FLAC compression level: {compression_level}",
                *([f"Decoded audio matched. Verified source copies in {SOURCE_ARCHIVE}."] if paranoid else []),
                *notes, *verification, "", *mappings, "",
            ]),
            encoding="utf-8",
        )
        published = []
        retired = []
        renamed_manifests = []
        try:
            if paranoid:
                report(f"Saving the verified original fileset in {SOURCE_ARCHIVE}")
                staged_archive.rename(archive)
            for staged in [*sorted(staging.glob("*.flac")), staged_marker]:
                target = folder / staged.name
                if os.name == "nt":
                    staged.rename(target)
                else:
                    os.link(staged, target)
                published.append(target)
            if not paranoid:
                for source, destination in manifest_renames:
                    if os.name == "nt":
                        source.rename(destination)
                    else:
                        os.link(source, destination, follow_symlinks=False)
                        try:
                            source.unlink()
                        except (OSError, KeyboardInterrupt):
                            destination.unlink()
                            raise
                    renamed_manifests.append((source, destination))
                report(f"Removing {len(sources)} source SHN file(s) after FLAC verification")
                for source in sources:
                    retired_path = staging / source.name
                    source.rename(retired_path)
                    retired.append((source, retired_path))
        except (OSError, KeyboardInterrupt):
            for source, retired_path in reversed(retired):
                retired_path.rename(source)
            for source, destination in reversed(renamed_manifests):
                destination.rename(source)
            for target in reversed(published):
                target.unlink()
            if paranoid and not staged_archive.exists():
                archive.rename(staged_archive)
            raise
    return f"Re-encoded {len(sources)} SHN track(s) to FLAC. See {marker.name}."
