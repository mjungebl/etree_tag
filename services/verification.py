"""Read-only checks for FLAC audio and SHN file checksums."""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from mutagen import MutagenError
from mutagen.flac import FLAC

logger = logging.getLogger(__name__)
FLAC_DOWNLOADS = "https://xiph.org/flac/download.html"
MD5_ENTRY = re.compile(r"^([a-fA-F0-9]{32})\s+\*?(.+)$")
VERIFICATION_RECEIPT = ".etree-verified.json"


class VerificationFailed(Exception):
    """A show failed verification and must not be written."""


def _working_flac(candidate):
    if not candidate:
        return None
    candidate = Path(candidate).expanduser()
    if candidate.is_dir():
        candidate = candidate.resolve() / ("flac.exe" if os.name == "nt" else "flac")
    executable = shutil.which(str(candidate))
    if executable:
        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip().lower().startswith(b"flac "):
                return str(Path(executable).resolve())
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("Could not start FLAC at %s", executable, exc_info=True)
    return None


def choose_flac(configured_path, *, interactive, remember=None):
    command = "flac.exe" if os.name == "nt" else "flac"
    executable = _working_flac(configured_path) or _working_flac(command)
    if executable:
        return executable

    print(f"FLAC verification needs a working {command}.")
    if configured_path:
        print(f"Could not run the configured executable: {configured_path}")
    print(f"FLAC downloads: {FLAC_DOWNLOADS}")
    if interactive:
        try:
            while True:
                print("\n  1. Open the FLAC downloads page")
                print("  2. Enter the executable path or its folder")
                print("  3. Exit and try again later")
                choice = input("Choose [3]: ").strip()
                if choice in {"", "3"}:
                    break
                if choice == "1":
                    try:
                        opened = webbrowser.open(FLAC_DOWNLOADS)
                    except (OSError, webbrowser.Error):
                        opened = False
                    if not opened:
                        print(f"Open this address in your browser: {FLAC_DOWNLOADS}")
                elif choice == "2":
                    candidate = input(f"Path to {command} or its folder: ").strip().strip('"')
                    executable = _working_flac(candidate)
                    if executable:
                        if remember is None:
                            print(f"Using {executable} for this run.")
                            print("Set supportfiles.flac in your TOML or add the executable's folder to PATH to reuse it.")
                        else:
                            try:
                                remember(executable)
                            except (OSError, ValueError) as exc:
                                print(f"Could not save the FLAC path: {exc}")
                                print(f"Using {executable} for this run. Set supportfiles.flac or add its folder to PATH to reuse it.")
                            else:
                                print(f"Saved {executable} for future runs.")
                        return executable
                    print("That path did not run the FLAC command-line tool.")
                else:
                    print("Choose 1, 2, or 3.")
        except (EOFError, KeyboardInterrupt):
            print()
    print("Install FLAC on PATH or run again with --flac PATH.")
    return None


def verify_shn(folder, *, progress=None):
    if not progress or not any(folder.glob("*.shn")):
        return _verify_shn(folder)
    progress("Checking available SHN MD5s")
    try:
        notes = _verify_shn(folder)
    except (VerificationFailed, OSError) as exc:
        details = "\n".join(f"  - {reason}" for reason in str(exc).splitlines())
        progress(f"SHN MD5 check [Failed]\n{details}")
        raise
    unverified = sum(note.startswith("Unverified:") for note in notes)
    if unverified:
        progress(f"SHN MD5 check [Unverified] — {unverified} file(s) without an MD5 entry")
    elif notes:
        progress(f"SHN MD5 check [OK] — {notes[0]}")
    else:
        progress("SHN MD5 check [Unverified] — no SHN files found")
    return notes


def _shn_entries(folder, manifests):
    for manifest in manifests:
        for line in manifest.read_text(encoding="utf-8-sig", errors="surrogateescape").splitlines():
            match = MD5_ENTRY.fullmatch(line.strip())
            if not match:
                if line.strip().lower().endswith(".shn"):
                    raise VerificationFailed(f"{manifest.name}: invalid SHN checksum entry")
                continue
            expected, name = match.groups()
            if not name.lower().endswith(".shn"):
                continue
            path = (folder / name.replace("\\", "/")).resolve()
            if not path.is_relative_to(folder):
                raise VerificationFailed(f"{manifest.name}: SHN entry outside the show folder")
            yield manifest, expected, name, path


def _verify_shn(folder):
    files = set(folder.glob("*.shn"))
    if not files:
        return []
    checked = set()
    notes = []
    failed = []
    for manifest, expected, name, path in _shn_entries(folder, sorted(folder.glob("*.md5"))):
        if not path.is_file():
            failed.append(f"{manifest.name}: missing SHN file {name}")
            continue
        try:
            with path.open("rb") as source:
                actual = hashlib.file_digest(source, lambda: hashlib.md5(usedforsecurity=False)).hexdigest()
        except OSError as exc:
            failed.append(f"{name}: could not read SHN file ({exc})")
            continue
        if actual != expected.lower():
            failed.append(f"{name}: MD5 mismatch in {manifest.name}")
            continue
        checked.add(path)
    if failed:
        raise VerificationFailed("\n".join(failed))
    if checked:
        notes.append(f"Verified whole-file MD5 for {len(checked)} SHN file(s).")
    for path in sorted(files):
        if path.resolve() not in checked:
            notes.append(f"Unverified: {path.name} has no MD5 entry.")
    return notes


def _verification_inputs(folder):
    flacs = set(folder.glob("*.flac"))
    shns = set(folder.glob("*.shn"))
    inputs = flacs | shns
    if shns:
        manifests = sorted(folder.glob("*.md5"))
        inputs.update(manifests)
        inputs.update(path for _, _, _, path in _shn_entries(folder, manifests))
    state = {}
    for path in sorted(inputs):
        stat = path.stat()
        state[path.relative_to(folder).as_posix()] = [
            stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
        ]
    return state


def verify_show_with_receipt(folder, get_flac, *, progress=None):
    """Reuse verification for an unchanged show, or verify and save a receipt."""
    folder = folder.resolve()
    receipt = folder / VERIFICATION_RECEIPT
    try:
        inputs = _verification_inputs(folder)
    except (OSError, VerificationFailed):
        inputs = {}
    try:
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if inputs and saved["version"] == 1 and saved["inputs"] == inputs:
            checked_at = datetime.fromisoformat(saved["verified_at"])
            note = f"Reused verification from {checked_at.isoformat(sep=' ', timespec='seconds')}"
            if progress:
                progress(note)
            return [note]
    except (OSError, ValueError, TypeError, KeyError):
        pass

    flac = get_flac() if any(folder.glob("*.flac")) else None
    notes = verify_show(folder, flac, progress=progress)
    if not inputs or not notes or any(note.startswith("Unverified:") for note in notes):
        return notes
    temporary = None
    try:
        if inputs != _verification_inputs(folder):
            raise VerificationFailed("Verification inputs changed during the check")
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as output:
            temporary = Path(output.name)
            json.dump({
                "version": 1,
                "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "inputs": inputs,
            }, output, indent=2)
            output.write("\n")
        temporary.replace(receipt)
    except OSError as exc:
        if progress:
            progress(f"Could not save verification receipt — {exc}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return notes


def verify_show(folder, flac, *, progress=None):
    """Return readable verification results, or raise on an integrity failure."""
    folder = folder.resolve()
    tracks = sorted(folder.glob("*.flac"))
    if not tracks:
        return verify_shn(folder, progress=progress)
    try:
        notes = _verify_flacs_and_shns(folder, tracks, flac)
    except (VerificationFailed, OSError) as exc:
        if progress:
            details = "\n".join(f"  - {reason}" for reason in str(exc).splitlines())
            progress(f"Verification [Failed]\n{details}")
        raise
    if progress:
        status = "Unverified" if any(note.startswith("Unverified:") for note in notes) else "OK"
        progress(f"Verification [{status}] — {' '.join(notes)}")
    return notes


def _verify_flacs_and_shns(folder, tracks, flac):
    failed = []
    notes = []
    try:
        notes = verify_shn(folder)
    except (VerificationFailed, OSError) as exc:
        failed.append(str(exc))
    if not flac:
        raise VerificationFailed("\n".join([*failed, "FLAC verifier is unavailable"]))

    verified = 0
    for path in tracks:
        try:
            result = subprocess.run(
                [flac, "-t", "--silent", str(path)],
                capture_output=True, timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not verify %s: %s", path, exc)
            failed.append(f"{path.name}: could not complete FLAC verification")
            continue
        if result.returncode:
            diagnostic = result.stderr.decode(errors="replace").strip()
            logger.error("FLAC verification failed for %s: %s", path, diagnostic)
            reason = (
                "decoded audio does not match its stored MD5"
                if "md5 signature mismatch" in diagnostic.lower()
                else "FLAC audio test failed"
            )
            failed.append(f"{path.name}: {reason}")
            continue
        try:
            signature = FLAC(path).info.md5_signature
        except (MutagenError, OSError) as exc:
            logger.warning("Could not read FLAC metadata for %s: %s", path, exc)
            failed.append(f"{path.name}: could not read stored audio MD5")
            continue
        if signature:
            verified += 1
        else:
            notes.append(f"Unverified: {path.name} decoded but has no stored audio MD5.")
    if failed:
        raise VerificationFailed("\n".join(failed))
    if verified:
        notes.insert(0, f"Verified audio integrity for {verified} FLAC file(s).")
    return notes
