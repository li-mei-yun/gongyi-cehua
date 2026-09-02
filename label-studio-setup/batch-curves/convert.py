"""Read SCU2020 XLSX files; create resumable, bounded Label Studio JSON batches.

Python 3.10+ standard library only. Does not edit Excel or contact Label Studio.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
import posixpath
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
BASE = Path(__file__).resolve().parent
DEFAULT_DATA = Path('D:/lmy/拧紧曲线/code/Tightening_curve_classification/SCU2020/data')
QUALITY = {0: '正常曲线', 1: '异常曲线'}
TYPE = {'initial': '正常拧紧', 'retighten': '复拧'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def atomic_write(path, content):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_bytes(content)
    temp.replace(path)


def read_rows(raw, width, sheet_name='Sheet1'):
    """Narrow, audited OOXML reader: no formulas or unsupported cell types."""
    with ZipFile(BytesIO(raw)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 256 * 1024 * 1024:
            raise ValueError('Workbook expands beyond 256 MiB safety limit')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(t.text or '' for t in item.findall('.//s:t', NS))
                       for item in shared.findall('s:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        matches = [s for s in workbook.findall('s:sheets/s:sheet', NS) if s.get('name') == sheet_name]
        if len(matches) != 1:
            raise ValueError(f'Expected sheet {sheet_name!r}')
        relation_id = matches[0].get('{' + NS['r'] + '}id')
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        relation = next(r for r in rels if r.get('Id') == relation_id)
        if relation.get('TargetMode') == 'External':
            raise ValueError('External worksheet is unsupported')
        target = relation.get('Target')
        member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        sheet = ET.fromstring(archive.read(member))
        output = []
        for row in sheet.findall('s:sheetData/s:row', NS):
            values = [None] * width
            for cell in row.findall('s:c', NS):
                ref = cell.get('r', '')
                match = re.fullmatch(r'([A-Z]+)([0-9]+)', ref)
                if not match:
                    raise ValueError(f'Bad cell address {ref!r}')
                col = 0
                for letter in match[1]:
                    col = col * 26 + ord(letter) - 64
                if cell.find('s:f', NS) is not None:
                    raise ValueError(f'Formula at {ref}; export numeric values before conversion')
                value_node = cell.find('s:v', NS)
                kind = cell.get('t', 'n')
                if kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                elif value_node is None or value_node.text is None:
                    value = None
                elif kind == 's':
                    value = strings[int(value_node.text)]
                elif kind == 'n':
                    value = float(value_node.text)
                    if not math.isfinite(value):
                        raise ValueError(f'Nonfinite number at {ref}')
                    if value.is_integer():
                        value = int(value)
                elif kind == 'str':
                    value = value_node.text
                else:
                    raise ValueError(f'Unsupported cell type {kind} at {ref}')
                if col > width:
                    if value not in (None, ''):
                        raise ValueError(f'Unexpected nonempty column {ref}')
                else:
                    values[col - 1] = value
            if any(v not in (None, '') for v in values):
                output.append((int(row.get('r')), values))
        return output


def read_labels(raw):
    rows = read_rows(raw, 3)
    if not rows or rows[0][1] != ['filename', 'labels', 'curve_type']:
        raise ValueError('Label headers must be filename, labels, curve_type')
    labels = {}
    for row_number, (name, quality, kind) in rows[1:]:
        if (not isinstance(name, str) or '/' in name or '\\' in name
                or not re.fullmatch(r'[0-9]+\.xlsx', name, re.I)):
            raise ValueError(f'Invalid label filename at row {row_number}')
        if quality not in QUALITY or kind not in TYPE:
            raise ValueError(f'Unknown label at row {row_number}: {quality!r}, {kind!r}')
        key = name.casefold()
        if key in labels:
            raise ValueError(f'Duplicate label filename {name}')
        labels[key] = {'quality': quality, 'type': kind, 'row': row_number}
    return labels


def make_task(filename, raw, label, label_sha):
    table = read_rows(raw, 4)
    if not table or table[0][1] != ['ID', '结果 ID', '扭矩 (N·m)', '角度 (度)']:
        raise ValueError('Curve headers differ from the 3918223 sample')
    curve_id = int(PurePosixPath(filename).stem)
    values = [r for _, r in table[1:]]
    if len(values) < 2:
        raise ValueError('Curve has fewer than two points')
    for index, row in enumerate(values):
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in row):
            raise ValueError(f'Missing/nonnumeric value at Excel row {table[index+1][0]}')
        if row[0] != index + 1 or row[1] != curve_id:
            raise ValueError(f'Nonsequential sample ID or mismatched result ID at sample {index+1}')
    task = {
        'data': {
            'filename': filename, 'curve_id': str(curve_id),
            'description': f'曲线 {curve_id}｜{len(values)} 个采样点｜横轴为原始 ID（非秒）',
            'source_labels_code': label['quality'], 'source_curve_type': label['type'],
            'series': {'sample_id': [r[0] for r in values], 'torque_nm': [r[2] for r in values],
                       'angle_deg': [r[3] for r in values]},
        },
        'annotations': [{'was_cancelled': False, 'result': [
            {'from_name': 'quality', 'to_name': 'ts', 'type': 'choices',
             'value': {'choices': [QUALITY[label['quality']]]}},
            {'from_name': 'tightening_type', 'to_name': 'ts', 'type': 'choices',
             'value': {'choices': [TYPE[label['type']]]}},
        ]}],
        'meta': {'source_curve_file': filename, 'source_curve_sha256': sha(raw),
                 'source_label_sha256': label_sha, 'source_label_excel_row': label['row'],
                 'x_axis': 'original sample ID; not seconds'},
    }
    restored = json.loads(encoded(task))['data']['series']
    if any([restored['sample_id'][i], curve_id, restored['torque_nm'][i], restored['angle_deg'][i]] != r
           for i, r in enumerate(values)):
        raise ValueError('JSON numeric roundtrip mismatch')
    return task, len(values)


def pack_batches(tasks, count_limit, byte_limit):
    batch, size = [], 2
    for task_bytes in tasks:
        if len(task_bytes) + 2 > byte_limit:
            raise ValueError('One curve exceeds batch byte limit')
        delta = len(task_bytes) + bool(batch)
        if batch and (len(batch) >= count_limit or size + delta > byte_limit):
            yield b'[' + b','.join(batch) + b']', len(batch)
            batch, size = [], 2
        size += len(task_bytes) + bool(batch)
        batch.append(task_bytes)
    if batch:
        yield b'[' + b','.join(batch) + b']', len(batch)


def run(args):
    source = args.curves.resolve()
    output = args.output.resolve()
    if output == source or source in output.parents:
        raise ValueError('Output must be outside the original curve directory')
    if args.batch_size < 1 or args.max_mb <= 0 or (args.limit is not None and args.limit < 1):
        raise ValueError('Batch limits must be positive')
    all_files = sorted((p for p in source.glob('*.xlsx') if not p.name.startswith('~$')), key=lambda p: p.name)
    if not all_files:
        raise ValueError('No XLSX curves found')
    names = [p.name.casefold() for p in all_files]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate case-insensitive filenames')
    label_raw = args.labels.read_bytes()
    label_sha = sha(label_raw)
    labels = read_labels(label_raw)
    missing_labels = sorted(set(names) - set(labels))
    missing_files = sorted(set(labels) - set(names))
    output.mkdir(parents=True, exist_ok=True)
    if missing_labels or missing_files:
        atomic_write(output / 'mismatch_report.json', encoded({
            'files_without_labels': missing_labels, 'labels_without_files': missing_files}))
        raise ValueError('File/label mismatch: see mismatch_report.json; no import package created')
    files = all_files[:args.limit] if args.limit else all_files
    config = (BASE.parent / 'curve-import-3918223' / 'project_config.xml').read_bytes()
    snapshot = {'version': 1, 'source': str(source), 'labels': str(args.labels.resolve()),
                'label_sha256': label_sha, 'config_sha256': sha(config),
                'batch_size': args.batch_size, 'max_mb': args.max_mb, 'limit': args.limit,
                'files': [[p.name, p.stat().st_size, p.stat().st_mtime_ns] for p in files]}
    snapshot_bytes = encoded(snapshot)
    snapshot_path = output / 'snapshot.json'
    if snapshot_path.exists() and snapshot_path.read_bytes() != snapshot_bytes:
        raise ValueError('Inputs/options changed. Use a NEW output directory, preserving the old import manifest.')
    atomic_write(snapshot_path, snapshot_bytes)
    dataset_id = sha(snapshot_bytes)
    atomic_write(output / 'project_config.xml', config)
    errors, converted, cached, total_samples = [], 0, 0, 0
    groups = Counter()
    with closing(sqlite3.connect(output / 'conversion_cache.sqlite3')) as db:
        db.execute('CREATE TABLE IF NOT EXISTS tasks (filename TEXT PRIMARY KEY, source_sha TEXT NOT NULL, payload BLOB NOT NULL, samples INTEGER NOT NULL)')
        for i, path in enumerate(files, 1):
            try:
                raw = path.read_bytes()
                digest = sha(raw)
                previous = db.execute('SELECT source_sha,samples FROM tasks WHERE filename=?', (path.name,)).fetchone()
                if previous:
                    if previous[0] != digest:
                        raise ValueError('File content changed after conversion; use a new output directory')
                    count = previous[1]
                    cached += 1
                else:
                    task, count = make_task(path.name, raw, labels[path.name.casefold()], label_sha)
                    task['meta']['migration_dataset_id'] = dataset_id
                    db.execute('INSERT INTO tasks VALUES (?,?,?,?)', (path.name, digest, encoded(task), count))
                    converted += 1
                total_samples += count
                label = labels[path.name.casefold()]
                groups[f"{label['quality']}|{label['type']}"] += 1
            except Exception as exc:
                errors.append({'filename': path.name, 'error': str(exc)})
            if i % 250 == 0 or i == len(files):
                db.commit()
                print(f'Checked {i}/{len(files)}; converted={converted}, cached={cached}, errors={len(errors)}', flush=True)
        db.commit()
        if errors:
            atomic_write(output / 'errors.json', encoded(errors))
            raise ValueError(f'{len(errors)} curve errors; package NOT finalized. See errors.json')
        batches_dir = output / 'batches'
        batches_dir.mkdir(exist_ok=True)
        def cached_payloads():
            for path in files:
                yield db.execute('SELECT payload FROM tasks WHERE filename=?', (path.name,)).fetchone()[0]
        batches = []
        for index, (payload, count) in enumerate(pack_batches(cached_payloads(), args.batch_size, int(args.max_mb * 1024**2)), 1):
            filename = f'batch_{index:04d}.json'
            target = batches_dir / filename
            if target.exists() and target.read_bytes() != payload:
                raise ValueError('Existing batch differs; use a new output directory')
            if not target.exists():
                atomic_write(target, payload)
            batches.append({'file': 'batches/' + filename, 'tasks': count, 'bytes': len(payload), 'sha256': sha(payload)})
        manifest = {'version': 1, 'dataset_id': dataset_id, 'config_sha256': sha(config),
                    'task_count': len(files), 'sample_count': total_samples, 'label_counts': dict(groups),
                    'label_sha256': label_sha, 'batches': batches}
        atomic_write(output / 'manifest.json', encoded(manifest))
    summary = {k:v for k,v in manifest.items() if k != 'batches'}
    summary.update(batch_count=len(batches), total_json_bytes=sum(b['bytes'] for b in batches),
                   max_batch_bytes=max(b['bytes'] for b in batches), curve_errors=0,
                   original_files_modified=False, actual_label_studio_import=False)
    atomic_write(output / 'summary.json', json.dumps(summary, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--curves', type=Path, default=DEFAULT_DATA / 'TraceReportExport_Angle_Torque')
    p.add_argument('--labels', type=Path, default=DEFAULT_DATA / 'label/label.xlsx')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--batch-size', type=int, default=500)
    p.add_argument('--max-mb', type=float, default=8)
    p.add_argument('--limit', type=int, help='Pilot conversion only; use its own output directory')
    args = p.parse_args()
    try:
        run(args)
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc or "Interrupted; rerun the same command to resume conversion"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
