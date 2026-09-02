"""Upgrade already-imported curves to XY display, without creating tasks or editing labels.

Default is local dry-run. --apply requires confirmation and a local access token.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
from convert import atomic_write, encoded, sha
from import_batches import Client, config_signature, exclusive_lock, validate_package

BASE = Path(__file__).resolve().parent


def annotation_signature(task):
    return sorted((json.dumps({k:a.get(k) for k in ('id','result','was_cancelled','ground_truth')},
                             sort_keys=True, ensure_ascii=False) for a in task.get('annotations', [])))


def load_plan(old, new, url, project_id):
    original, old_sha, old_config = validate_package(old)
    updated, new_sha, new_config = validate_package(new)
    if updated.get('source_manifest_sha256') != old_sha:
        raise ValueError('XY package does not match original package')
    journal_name = f'import-{sha(url.rstrip("/").encode())[:12]}-project-{project_id}.json'
    old_journal_path = old / journal_name
    if old_journal_path.with_suffix('.lock').exists():
        raise ValueError('Original import may still be running. Finish/stop it and inspect its journal first.')
    state = json.loads(old_journal_path.read_bytes())
    if state['identity'] != {'url':url.rstrip('/'), 'project_id':project_id, 'manifest_sha256':old_sha}:
        raise ValueError('Original import journal identity mismatch')
    if state.get('inflight'):
        raise ValueError('Original import has an uncertain batch; reconcile before changing presentation')
    done = state['completed']
    if not done:
        raise ValueError('No imported tasks to upgrade. Use the XY package for a new empty project.')
    if [b['file'] for b in done] != [b['file'] for b in original['batches'][:len(done)]]:
        raise ValueError('Original journal is not a completed prefix')
    originals, task_ids, completed_files = {}, [], set()
    for batch in done:
        tasks = json.loads((old / batch['file']).read_bytes())
        ids = batch.get('task_ids')
        if not ids or len(ids) != len(tasks):
            raise ValueError('Task IDs missing from original journal; no guessed IDs will be used')
        task_ids.extend(ids)
        completed_files.add(batch['file'])
        originals.update({t['data']['filename']:t for t in tasks})
    if len(set(task_ids)) != len(task_ids) or len(originals) != len(task_ids):
        raise ValueError('Duplicate tasks in journal')
    adopted, new_tasks = [], {}
    for batch in updated['batches']:
        if batch['source_batch'] not in completed_files:
            break
        adopted.append(batch)
        tasks = json.loads((new / batch['file']).read_bytes())
        new_tasks.update({t['data']['filename']:t for t in tasks})
    if set(new_tasks) != set(originals):
        raise ValueError('XY package prefix does not match imported tasks')
    for name, task in new_tasks.items():
        data = dict(task['data'])
        data.pop('angle_torque_plot')
        if data != originals[name]['data'] or task['annotations'] != originals[name]['annotations']:
            raise ValueError('XY package changed original data or annotation')
    return {'originals':originals, 'new_tasks':new_tasks, 'task_ids':task_ids, 'batches':adopted,
            'old_config':old_config, 'new_config':new_config, 'manifest_sha':new_sha,
            'journal_path':new/journal_name, 'old_journal_sha':sha(old_journal_path.read_bytes()),
            'old_journal_path':old_journal_path}


def upgrade(client, project_id, plan, backup_dir):
    journal_path = plan['journal_path']
    if journal_path.exists():
        # Never overwrite progress after the regular importer has continued the XY package.
        raise ValueError('XY import journal already exists; upgrade already completed or needs inspection. Do not overwrite it.')
    client.authorize()
    project = client.project(project_id)
    if project.get('task_number') != len(plan['task_ids']):
        raise ValueError('Remote task count differs from original journal; no writes performed')
    if config_signature(project['label_config']) not in (config_signature(plan['old_config']), config_signature(plan['new_config'])):
        raise ValueError('Project template was independently changed; stop instead of overwriting it')
    backup_dir.mkdir(parents=True, exist_ok=True)
    before_project = backup_dir / 'project-before.json'
    if not before_project.exists():
        atomic_write(before_project, encoded(project))
    name_to_id, signatures = {}, {}
    # Preflight every target before the first PATCH; do not assume task-ID ordering.
    for task_id in plan['task_ids']:
        task = client.raw_request('GET', f'/api/tasks/{task_id}/')
        name = task.get('data', {}).get('filename')
        if task.get('project') != project_id or name not in plan['originals'] or name in name_to_id:
            raise ValueError(f'Task {task_id} does not uniquely match the requested project/package')
        original = plan['originals'][name]['data']
        for key in ('series', 'curve_id', 'filename'):
            if task['data'].get(key) != original[key]:
                raise ValueError(f'Task {task_id} source data changed; refusing to overwrite')
        name_to_id[name] = task_id
        signatures[task_id] = annotation_signature(task)
    for index, (name, task_id) in enumerate(name_to_id.items(), 1):
        if index % 50 == 1:
            client.authorize()
        before = client.raw_request('GET', f'/api/tasks/{task_id}/')
        if annotation_signature(before) != signatures[task_id]:
            raise ValueError('Annotations changed during upgrade. Stop other editing and recheck.')
        desired = plan['new_tasks'][name]['data']['angle_torque_plot']
        data = dict(before['data'])
        for key in ('series','curve_id','filename'):
            if data.get(key) != plan['originals'][name]['data'][key]:
                raise ValueError('Source data changed during upgrade; stopping')
        backup = backup_dir / f'task-{task_id}-before.json'
        if not backup.exists():
            atomic_write(backup, encoded(before))
        if data.get('angle_torque_plot') != desired:
            data['angle_torque_plot'] = desired
            # This PATCH is repeatable. Never send annotations, predictions, IDs, or source labels.
            client.raw_request('PATCH', f'/api/tasks/{task_id}/', encoded({'data':data}))
        after = client.raw_request('GET', f'/api/tasks/{task_id}/')
        if after['data'] != data or annotation_signature(after) != signatures[task_id]:
            raise ValueError('Task verification failed; backups retained, no new import journal written')
        if index % 25 == 0 or index == len(name_to_id):
            print(f'XY data verified {index}/{len(name_to_id)}; labels preserved', flush=True)
    # Only reveal the new image after every existing task has its image data.
    client.authorize()
    current = client.project(project_id)
    if current.get('task_number') != len(name_to_id) or sha(plan['old_journal_path'].read_bytes()) != plan['old_journal_sha']:
        raise ValueError('Import state changed during upgrade; template not changed')
    if config_signature(current['label_config']) not in (config_signature(plan['old_config']), config_signature(plan['new_config'])):
        raise ValueError('Template changed during upgrade')
    if config_signature(current['label_config']) != config_signature(plan['new_config']):
        client.raw_request('PATCH', f'/api/projects/{project_id}/', encoded({'label_config':plan['new_config']}))
    after_project = client.project(project_id)
    if (config_signature(after_project['label_config']) != config_signature(plan['new_config'])
            or after_project.get('task_number') != len(name_to_id)):
        raise ValueError('Project template verification failed')
    # Check labels after the template update as well, not just after task PATCH.
    for task_id in plan['task_ids']:
        task = client.raw_request('GET', f'/api/tasks/{task_id}/')
        if annotation_signature(task) != signatures[task_id]:
            raise ValueError('Annotations differ after template update; inspect the backup')
    completed = []
    for batch in plan['batches']:
        names = [t['data']['filename'] for t in json.loads((journal_path.parent / batch['file']).read_bytes())]
        completed.append({'file':batch['file'], 'tasks':batch['tasks'], 'sha256':batch['sha256'],
                          'task_ids':[name_to_id[n] for n in names]})
    state = {'identity':{'url':client.url, 'project_id':project_id, 'manifest_sha256':plan['manifest_sha']},
             'completed':completed, 'inflight':None}
    atomic_write(journal_path, encoded(state))
    print(f'UPGRADE DONE: {len(name_to_id)} existing tasks verified. No tasks created; labels preserved. Refresh Label Studio.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=int, default=3)
    parser.add_argument('--url', default='http://localhost:8080')
    parser.add_argument('--old-package', type=Path, default=BASE/'package-scu2020')
    parser.add_argument('--new-package', type=Path, default=BASE/'package-scu2020-xy')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        plan = load_plan(args.old_package, args.new_package, args.url, args.project)
        print(f'Plan: add XY images to {len(plan["task_ids"])} existing tasks; preserve labels; update project {args.project} template.')
        if not args.apply:
            print('DRY RUN: no network requests or project changes. Add --apply to perform the upgrade.')
            return 0
        if input(f'Type UPGRADE {args.project} to confirm: ').strip() != f'UPGRADE {args.project}':
            print('Cancelled')
            return 0
        token = os.environ.get('LABEL_STUDIO_API_KEY') or getpass.getpass('Label Studio access token (hidden; not saved): ')
        if not token:
            raise ValueError('Access token required')
        client = Client(args.url, token.strip(), 'auto')
        with exclusive_lock(plan['old_journal_path'].with_suffix('.lock')):
            with exclusive_lock(plan['journal_path'].with_suffix('.lock')):
                upgrade(client, args.project, plan, args.new_package/f'upgrade-backup-project-{args.project}')
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc or "Interrupted. Rerun the upgrade after checking the project; existing task PATCHes are repeatable."}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
