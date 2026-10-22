"""Собрать исходники Т4 без .git, окружений, секретов и node_modules."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "delo-staff-2026-10-22-v1"


def source_bytes(path):
    data = path.read_bytes()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(b"\r\n", b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                    cwd=ROOT).decode("utf-8").split("\0")
    files = sorted({n for n in names if n and (ROOT / n).is_file()})
    runtime = [n for n in files if (n.startswith(("backend/", "frontend/", "deploy/", "scripts/"))
                                    or n == "docker-compose.yml")]
    # Checkout на Windows меняет LF на CRLF. Исходники и их идентификатор
    # должны совпадать при передаче между Windows, Git и Linux.
    hashes = {name: hashlib.sha256(source_bytes(ROOT / name)).hexdigest() for name in runtime}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    manifest = {"version": VERSION, "date": "2026-10-22", "source_sha256": digest,
                "base_main": "ee2b3b5b1b6fa873a65fe37ddaba0e857c3e9ac1", "migration": "20261022_01",
                "ruleset_version": "RS-2026.10.1", "policy_version": "AP-2026.10.1",
                "normalization": "UTF-8 text line endings: LF", "files": hashes}
    (ROOT / "RELEASE.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w:gz") as tar:
        for name in sorted(set(files) | {"RELEASE.json"}):
            data = source_bytes(ROOT / name)
            info = tar.gettarinfo(str(ROOT / name), arcname=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    print(json.dumps({"version": VERSION, "source_sha256": digest,
                      "archive_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "files": len(files), "archive": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
