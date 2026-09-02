"""Read-only reconciliation of an uncertain Label Studio SQLite import batch."""
import argparse
import json
import sqlite3
from pathlib import Path


def table_columns(db, table):
    return [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--project', type=int, required=True)
    parser.add_argument('--batch', type=Path, required=True)
    args = parser.parse_args()

    uri = args.database.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        candidates = []
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            columns = table_columns(db, name)
            if 'project_id' in columns and 'data' in columns:
                candidates.append((name, columns))
        matches = [(name, columns) for name, columns in candidates if name == 'task']
        if len(matches) != 1:
            raise RuntimeError(f'Expected the Label Studio task table; found {[name for name, _ in candidates]}')
        table, columns = matches[0]
        tasks = json.loads(args.batch.read_text(encoding='utf-8'))
        filenames = [task['data']['filename'] for task in tasks]
        rows = db.execute(
            f'SELECT id, data FROM "{table}" WHERE project_id=?', (args.project,)
        ).fetchall()
        project_filenames = {}
        malformed = 0
        for task_id, raw_data in rows:
            try:
                data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                filename = data.get('filename')
            except Exception:
                malformed += 1
                continue
            if filename:
                project_filenames.setdefault(filename.casefold(), []).append(task_id)
        present = {name: project_filenames.get(name.casefold(), []) for name in filenames}
        result = {
            'database': str(args.database.resolve()),
            'task_table': table,
            'project': args.project,
            'project_task_rows': len(rows),
            'project_rows_without_readable_filename': malformed,
            'batch_tasks': len(filenames),
            'batch_present_once': sum(len(ids) == 1 for ids in present.values()),
            'batch_missing': [name for name, ids in present.items() if not ids],
            'batch_duplicates': {name: ids for name, ids in present.items() if len(ids) > 1},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
