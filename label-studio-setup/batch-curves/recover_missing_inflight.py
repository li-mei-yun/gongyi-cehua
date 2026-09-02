"""Clear an uncertain import only after proving its whole batch is absent."""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from convert import atomic_write, encoded, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    args = parser.parse_args()

    journal_path = args.journal.resolve()
    package = journal_path.parent
    state = json.loads(journal_path.read_text(encoding='utf-8'))
    inflight = state.get('inflight')
    if not inflight:
        raise RuntimeError('Journal has no uncertain batch')
    project_id = state['identity']['project_id']

    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    entries = {entry['file']: entry for entry in manifest['batches']}
    entry = entries.get(inflight.get('file'))
    if not entry or entry['sha256'] != inflight.get('sha256') or entry['tasks'] != inflight.get('expected_tasks'):
        raise RuntimeError('Inflight record does not match the package manifest')
    batch_path = (package / entry['file']).resolve()
    raw = batch_path.read_bytes()
    if sha(raw) != entry['sha256']:
        raise RuntimeError('Inflight batch checksum mismatch')
    tasks = json.loads(raw)
    filenames = [task['data']['filename'].casefold() for task in tasks]
    if len(filenames) != len(set(filenames)) or len(filenames) != entry['tasks']:
        raise RuntimeError('Inflight batch filenames are invalid')

    db_uri = args.database.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(db_uri, uri=True) as db:
        rows = db.execute('SELECT data FROM task WHERE project_id=?', (project_id,)).fetchall()
    expected_completed = sum(item['tasks'] for item in state['completed'])
    if len(rows) != expected_completed:
        raise RuntimeError(f'Project has {len(rows)} tasks; journal confirms {expected_completed}')
    existing = set()
    for (raw_data,) in rows:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        name = data.get('filename')
        if name:
            existing.add(name.casefold())
    found = sorted(set(filenames) & existing)
    if found:
        raise RuntimeError(f'{len(found)} inflight filenames already exist; refusing recovery')

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = journal_path.with_name(journal_path.name + f'.before-missing-recovery-{stamp}.bak')
    shutil.copy2(journal_path, backup)
    state['inflight'] = None
    state['recovery'] = {
        'kind': 'confirmed_whole_batch_absent',
        'file': entry['file'],
        'tasks': entry['tasks'],
        'project_task_rows': len(rows),
        'backup': backup.name,
        'at': stamp,
    }
    atomic_write(journal_path, encoded(state))
    print(json.dumps(state['recovery'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
