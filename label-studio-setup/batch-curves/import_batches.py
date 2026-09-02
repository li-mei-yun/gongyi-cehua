"""Import verified packages into a NEW, empty local Label Studio CE project.

Dry run by default. Real imports require --apply and an interactive confirmation.
No automatic retry after an uncertain POST. Tokens are never saved in the journal.
"""
import argparse
from contextlib import contextmanager
import getpass
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import xml.etree.ElementTree as ET
from convert import atomic_write, encoded, sha


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Redirect refused; verify the local Label Studio URL')


class Client:
    def __init__(self, url, token, token_type):
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/')):
            raise ValueError('This tool only sends data/tokens to a local loopback Label Studio URL')
        self.url, self.token = url.rstrip('/'), token
        self.token_type = ('pat' if token.count('.') == 2 else 'legacy') if token_type == 'auto' else token_type
        self.authorization = None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def raw_request(self, method, path, payload=None, authenticated=True):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if authenticated:
            headers['Authorization'] = self.authorization
        request = Request(self.url + path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=300) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(f'HTTP {exc.code}; verify service, account permissions, and token. Response body withheld.') from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError('Connection failed or timed out; import outcome may be uncertain') from None

    def authorize(self):
        if self.token_type == 'pat':
            response = self.raw_request('POST', '/api/token/refresh', encoded({'refresh': self.token}), False)
            access = response.get('access')
            if not isinstance(access, str) or not access:
                raise RuntimeError('Token refresh did not return an access token')
            self.authorization = 'Bearer ' + access
        else:
            self.authorization = 'Token ' + self.token

    def project(self, project_id):
        return self.raw_request('GET', f'/api/projects/{project_id}/')

    def import_batch(self, project_id, payload):
        return self.raw_request('POST', f'/api/projects/{project_id}/import?return_task_ids=true', payload)


def config_signature(xml):
    def signature(node):
        return (node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(),
                tuple(signature(child) for child in node))
    return signature(ET.fromstring(xml))


def validate_package(folder):
    raw_manifest = (folder / 'manifest.json').read_bytes()
    manifest = json.loads(raw_manifest)
    config = (folder / 'project_config.xml').read_bytes()
    if sha(config) != manifest['config_sha256']:
        raise ValueError('Template changed after conversion')
    total, names = 0, set()
    filenames = set()
    for batch in manifest['batches']:
        path = (folder / batch['file']).resolve()
        if folder.resolve() not in path.parents or path in names:
            raise ValueError('Invalid or repeated batch path')
        names.add(path)
        raw = path.read_bytes()
        if sha(raw) != batch['sha256'] or len(raw) != batch['bytes']:
            raise ValueError(f"Batch checksum mismatch: {batch['file']}")
        tasks = json.loads(raw)
        if len(tasks) != batch['tasks']:
            raise ValueError('Task count mismatch')
        for task in tasks:
            name = task['data']['filename']
            if name.casefold() in filenames:
                raise ValueError(f'Duplicate task: {name}')
            filenames.add(name.casefold())
            if len(task.get('annotations', [])) != 1 or len(task['annotations'][0]['result']) != 2:
                raise ValueError('Expected two human classification results per curve')
        total += len(tasks)
    if total != manifest['task_count']:
        raise ValueError('Package total mismatch')
    return manifest, sha(raw_manifest), config.decode('utf-8-sig')


@contextmanager
def exclusive_lock(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise RuntimeError('Import lock exists. Do not run concurrently; after a crash, inspect the journal before removing the stale lock.') from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def execute_import(client, project_id, folder, manifest, manifest_sha, config, journal_path,
                   interval=30, max_batches=None):
    identity = {'url': client.url, 'project_id': project_id, 'manifest_sha256': manifest_sha}
    if journal_path.exists():
        state = json.loads(journal_path.read_text(encoding='utf-8'))
        if state['identity'] != identity:
            raise RuntimeError('Journal belongs to another package/project; do not reuse it')
    else:
        state = {'identity': identity, 'completed': [], 'inflight': None}
    if state['inflight'] is not None:
        raise RuntimeError('Previous batch outcome is UNCERTAIN. Stopped to prevent duplicates. Inspect the project and journal; do not delete state and retry.')
    client.authorize()
    project = client.project(project_id)
    if config_signature(project.get('label_config', '')) != config_signature(config):
        raise RuntimeError('Project template does not match project_config.xml. No tasks sent.')
    completed = state['completed']
    expected_prefix = [b['file'] for b in manifest['batches'][:len(completed)]]
    if [b['file'] for b in completed] != expected_prefix:
        raise RuntimeError('Journal is not a contiguous prefix of this package')
    expected_count = sum(b['tasks'] for b in completed)
    if project.get('task_number') != expected_count:
        raise RuntimeError(f'Project has {project.get("task_number")} tasks; expected {expected_count}. Start with an EMPTY new project; do not mix manual imports.')
    atomic_write(journal_path, encoded(state))
    pending = manifest['batches'][len(completed):]
    if max_batches:
        pending = pending[:max_batches]
    for position, batch in enumerate(pending):
        if position or completed:
            wait_until = state.get('last_completed_at', 0) + interval
            while time.time() < wait_until:
                time.sleep(min(1, wait_until - time.time()))
        client.authorize()  # Obtain a fresh PAT access token BEFORE the non-idempotent POST.
        payload = (folder / batch['file']).read_bytes()
        if sha(payload) != batch['sha256']:
            raise RuntimeError('Batch changed since verification')
        state['inflight'] = {'file': batch['file'], 'sha256': batch['sha256'], 'expected_tasks': batch['tasks']}
        atomic_write(journal_path, encoded(state))  # Durable intent before sending.
        print(f"Importing {batch['file']} ({batch['tasks']} tasks)...", flush=True)
        reply = client.import_batch(project_id, payload)
        if reply.get('task_count') != batch['tasks'] or reply.get('annotation_count') != batch['tasks']:
            raise RuntimeError('Server did not confirm synchronous task/annotation counts. State retained as uncertain; do not resend (async editions need a different workflow).')
        task_ids = reply.get('task_ids')
        if task_ids is not None and len(task_ids) != batch['tasks']:
            raise RuntimeError('Server task-ID count mismatch; inspect the project before continuing')
        completed.append({'file': batch['file'], 'tasks': batch['tasks'], 'sha256': batch['sha256'], 'task_ids': task_ids})
        state['inflight'] = None
        state['last_completed_at'] = time.time()
        atomic_write(journal_path, encoded(state))
        print(f"Confirmed {sum(b['tasks'] for b in completed)}/{manifest['task_count']} tasks", flush=True)
    client.authorize()
    final_project = client.project(project_id)
    expected_count = sum(b['tasks'] for b in completed)
    if final_project.get('task_number') != expected_count:
        raise RuntimeError('Final project count differs from the import journal; inspect before proceeding')
    if len(completed) == len(manifest['batches']):
        print(f'DONE: server and journal confirm {expected_count} tasks. Spot-check curves and both labels in the UI.')
    else:
        print(f'PILOT DONE: {expected_count} tasks. Verify in UI; rerun without --max-batches to continue.')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parent / 'package-scu2020')
    parser.add_argument('--url', default='http://localhost:8080')
    parser.add_argument('--project', type=int)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--token-type', choices=['auto', 'pat', 'legacy'], default='auto')
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--max-batches', type=int)
    args = parser.parse_args()
    try:
        if args.interval < 30 or (args.max_batches is not None and args.max_batches < 1):
            raise ValueError('Use interval >=30 seconds and positive max-batches')
        manifest, manifest_sha, config = validate_package(args.package)
        print(f"Verified package: {manifest['task_count']} tasks in {len(manifest['batches'])} batches")
        if not args.apply:
            print('DRY RUN ONLY: no network request, no project changes. Use --project ID --apply to import.')
            return 0
        if args.project is None or args.project < 1:
            raise ValueError('--project must be a positive project ID')
        expected = f'IMPORT {args.project}'
        print(f'Target: {args.url}, project {args.project}. Only a NEW empty project or this package\'s existing journal is accepted.')
        if input(f'Type {expected} to confirm: ').strip() != expected:
            print('Cancelled. No network request sent.')
            return 0
        token = os.environ.get('LABEL_STUDIO_API_KEY') or getpass.getpass('Label Studio access token (hidden; not saved): ')
        if not token:
            raise ValueError('An access token is required')
        client = Client(args.url, token.strip(), args.token_type)
        journal_path = args.package / f'import-{sha(client.url.encode())[:12]}-project-{args.project}.json'
        with exclusive_lock(journal_path.with_suffix('.lock')):
            execute_import(client, args.project, args.package, manifest, manifest_sha, config,
                           journal_path, args.interval, args.max_batches)
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc or "Interrupted; inspect the journal before resuming"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
