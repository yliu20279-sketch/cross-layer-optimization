"""Collect this round's 113 experiment records into verified archives."""

import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


SECRET = re.compile(
    rb"github_pat_[0-9A-Za-z_]{25,}|gh[pousr]_[0-9A-Za-z]{30,}|"
    rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|"
    rb"AKIA[0-9A-Z]{16}|xox[baprs]-[0-9A-Za-z-]{24,}|"
    rb"https?://[^\s/@:]+:[^\s/@]+@"
)


def excluded(path):
    parts = path.parts
    return (
        any(part in {'.git', '__pycache__', 'vl'} for part in parts)
        or path.suffix in {'.o', '.a', '.pyc', '.gz', '.zip', '.deb'}
        or path.name in {'coupled_backend', 'Vunified_tb'}
    )


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(root, out):
    out.mkdir(exist_ok=False)
    groups = {
        '01-hiband-reference': [],
        '02-rtl-and-thermal-inputs': [],
        '03-opp-and-joint-thermal': [],
        '04-noc-only': [],
        '05-native-pair': [],
    }
    skipped = []
    for source in sorted(root.rglob('*')):
        relative = source.relative_to(root)
        if source.is_symlink() or (source.is_file() and excluded(relative)):
            skipped.append(relative.as_posix())
            continue
        if not source.is_file():
            continue
        if source.suffix != '.npz' and SECRET.search(source.read_bytes()):
            raise ValueError(f'Credential-like content in {relative}')
        first = relative.parts[0]
        if first == 'joint':
            group = '03-opp-and-joint-thermal' if relative.parts[1].startswith('opp_') else '02-rtl-and-thermal-inputs'
        elif first.startswith('noc_only_'):
            group = '04-noc-only'
        elif first.startswith('paired_native_'):
            group = '05-native-pair'
        else:
            group = '01-hiband-reference'
        groups[group].append(relative)

    records = []
    volumes = []
    for group, files in groups.items():
        if not files:
            raise ValueError(f'Missing experiment records for {group}')
        archive = out / f'{group}.tar.gz'
        with tarfile.open(archive, 'w:gz', compresslevel=2) as bundle:
            for relative in files:
                source = root / relative
                info = bundle.gettarinfo(str(source), relative.as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                with source.open('rb') as stream:
                    bundle.addfile(info, stream)
                records.append(dict(path=relative.as_posix(), archive=archive.name,
                                    bytes=info.size, sha256=sha(source)))

        volume_names = [archive.name]
        if archive.stat().st_size > 45 * 1024 * 1024:
            volume_names = []
            with archive.open('rb') as stream:
                for number, data in enumerate(iter(lambda: stream.read(40 * 1024 * 1024), b''), 1):
                    name = f'{archive.name}.part{number:02}'
                    (out / name).write_bytes(data)
                    volume_names.append(name)
        volumes.append(dict(archive=archive.name, sha256=sha(archive),
                            bytes=archive.stat().st_size, volumes=volume_names, members=len(files)))
    manifest = dict(archives=volumes, members=records, omitted=skipped)
    (out/'MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
    artifacts = [out/name for row in volumes for name in row['volumes']] + [out/'MANIFEST.json']
    (out/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in artifacts))
    print(json.dumps(dict(members=len(records), omitted=len(skipped), archives=volumes)))


if __name__ == '__main__':
    main(*(Path(s).resolve() for s in sys.argv[1:]))
