import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import convert
import import_batches as importer
import upgrade_xy

BASE = Path(__file__).resolve().parent
CONFIG = (BASE.parent / 'curve-import-3918223/project_config.xml').read_text(encoding='utf-8')


class FakeClient:
    url = 'http://localhost:8080'

    def __init__(self, count=0, fail=False, bad_counts=False):
        self.count, self.fail, self.bad_counts = count, fail, bad_counts
        self.posts = 0

    def authorize(self):
        pass

    def project(self, project_id):
        return {'task_number': self.count, 'label_config': CONFIG}

    def import_batch(self, project_id, payload):
        self.posts += 1
        count = len(json.loads(payload))
        self.count += count
        if self.fail:
            raise TimeoutError('simulated lost response AFTER server write')
        return {'task_count': count, 'annotation_count': 0 if self.bad_counts else count}


class Tests(unittest.TestCase):
    def setup_package(self, root):
        source = json.loads((BASE.parent / 'curve-import-3918223/tasks_3918223.json').read_text(encoding='utf-8'))[0]
        (root / 'batches').mkdir()
        batches = []
        for i in range(2):
            task = json.loads(json.dumps(source))
            task['data']['filename'] = f'{i}.xlsx'
            raw = convert.encoded([task])
            filename = f'batches/batch_{i+1:04d}.json'
            (root / filename).write_bytes(raw)
            batches.append({'file': filename, 'tasks': 1, 'bytes': len(raw), 'sha256': convert.sha(raw)})
        (root / 'project_config.xml').write_bytes(CONFIG.encode())
        (root / 'manifest.json').write_bytes(convert.encoded({'config_sha256': convert.sha(CONFIG.encode()), 'task_count': 2, 'batches': batches}))
        return importer.validate_package(root)

    def test_sample_matches_independent_artifact_extraction(self):
        old = json.loads((BASE.parent / 'curve-import-3918223/extracted.json').read_text(encoding='utf-8'))
        raw = Path(old['curve']['path']).read_bytes()
        labels = convert.read_labels(Path(old['labels']['path']).read_bytes())
        self.assertEqual(len(labels), 12981)
        for row in old['labels']['sheets'][0]['values'][1:]:
            if row[0] is not None:
                self.assertEqual((labels[row[0]]['quality'], labels[row[0]]['type']), tuple(row[1:3]))
        task, count = convert.make_task('3918223.xlsx', raw, labels['3918223.xlsx'], old['labels']['sha256'])
        original = json.loads((BASE.parent / 'curve-import-3918223/tasks_3918223.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(count, 615)
        self.assertEqual(task['data'], original['data'])
        self.assertEqual(task['annotations'], original['annotations'])

    def test_both_batch_limits(self):
        payloads = [b'{"a":1}'] * 7
        batches = list(convert.pack_batches(payloads, 3, 18))
        self.assertEqual(sum(c for _, c in batches), 7)
        self.assertTrue(all(len(b) <= 18 and c <= 3 for b, c in batches))
        with self.assertRaises(ValueError):
            list(convert.pack_batches([b'{}'], 1, 3))

    def test_reject_bad_label_and_bad_sample(self):
        header = (1, ['filename', 'labels', 'curve_type'])
        for data in [[header, (2, ['1.xlsx', 2, 'initial'])],
                     [header, (2, ['1.xlsx', 0, 'initial']), (3, ['1.xlsx', 0, 'retighten'])]]:
            with patch.object(convert, 'read_rows', return_value=data):
                with self.assertRaises(ValueError):
                    convert.read_labels(b'')
        header = (1, ['ID', '结果 ID', '扭矩 (N·m)', '角度 (度)'])
        for second in [[3, 1, 2, 3], [2, 99, 2, 3], [2, 1, None, 3]]:
            with patch.object(convert, 'read_rows', return_value=[header, (2, [1, 1, 2, 3]), (3, second)]):
                with self.assertRaises(ValueError):
                    convert.make_task('1.xlsx', b'', {'quality': 0, 'type': 'initial', 'row': 2}, '')

    def test_pilot_resume_and_completed_rerun(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest, digest, config = self.setup_package(root)
            client, journal = FakeClient(), root / 'journal.json'
            importer.execute_import(client, 1, root, manifest, digest, config, journal, 0, 1)
            self.assertEqual(client.posts, 1)
            importer.execute_import(client, 1, root, manifest, digest, config, journal, 0)
            importer.execute_import(client, 1, root, manifest, digest, config, journal, 0)
            self.assertEqual((client.posts, client.count), (2, 2))
            self.assertIsNone(json.loads(journal.read_text())['inflight'])

    def test_lost_response_is_not_retried(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest, digest, config = self.setup_package(root)
            client, journal = FakeClient(fail=True), root / 'journal.json'
            with self.assertRaises(TimeoutError):
                importer.execute_import(client, 1, root, manifest, digest, config, journal, 0)
            with self.assertRaisesRegex(RuntimeError, 'UNCERTAIN'):
                importer.execute_import(client, 1, root, manifest, digest, config, journal, 0)
            self.assertEqual(client.posts, 1)

    def test_wrong_counts_nonempty_project_and_tamper(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest, digest, config = self.setup_package(root)
            client = FakeClient(count=1)
            with self.assertRaises(RuntimeError):
                importer.execute_import(client, 1, root, manifest, digest, config, root/'journal.json', 0)
            self.assertEqual(client.posts, 0)
            client = FakeClient(bad_counts=True)
            with self.assertRaises(RuntimeError):
                importer.execute_import(client, 1, root, manifest, digest, config, root/'journal.json', 0)
            self.assertIsNotNone(json.loads((root/'journal.json').read_text())['inflight'])
            (root/'batches/batch_0001.json').write_bytes(b'[]')
            with self.assertRaises(ValueError):
                importer.validate_package(root)

    def test_remote_token_destination_is_rejected(self):
        for url in ['http://example.com', 'http://localhost.evil.test', 'http://user@localhost:8080', 'http://localhost:8080/path']:
            with self.assertRaises(ValueError):
                importer.Client(url, 'test', 'legacy')

    def test_xy_plot_preserves_nonmonotonic_pair_order(self):
        from xy_plot import figure_for, render_svg
        task = {'data':{'curve_id':'test','series':{'angle_deg':[0, 3, 3, -1, 2], 'torque_nm':[1, 2, 5, 4, 3]}}}
        fig = figure_for(task)
        line = fig.axes[0].lines[0]
        self.assertEqual(list(line.get_xdata()), [0, 3, 3, -1, 2])
        self.assertEqual(list(line.get_ydata()), [1, 2, 5, 4, 3])
        fig.clear()
        self.assertIn(b'<svg', render_svg(task))

    def test_xy_upgrade_preserves_edited_labels_and_resumes_after_lost_patch_reply(self):
        import copy
        original = json.loads((BASE.parent/'curve-import-3918223/tasks_3918223.json').read_text(encoding='utf-8'))[0]
        desired = copy.deepcopy(original)
        desired['data']['angle_torque_plot'] = 'data:image/svg+xml;base64,TEST'
        xy_config = (BASE/'project_config_xy.xml').read_text(encoding='utf-8')
        class UpgradeClient:
            url = 'http://localhost:8080'
            def __init__(self):
                self.task = copy.deepcopy(original)
                self.task.update(id=5, project=3)
                self.task['annotations'][0]['id'] = 27
                self.task['annotations'][0]['result'][0]['value']['choices'] = ['异常曲线']
                self.config = CONFIG
                self.lose_reply = True
                self.patches = 0
            def authorize(self): pass
            def project(self, project_id):
                return {'task_number':1, 'label_config':self.config}
            def raw_request(self, method, path, payload=None):
                if method == 'GET': return copy.deepcopy(self.task)
                body = json.loads(payload)
                if path.startswith('/api/tasks/'):
                    if set(body) != {'data'}: raise AssertionError('Must never PATCH annotations')
                    self.task['data'] = body['data']
                    self.patches += 1
                    if self.lose_reply:
                        self.lose_reply = False
                        raise TimeoutError('simulated lost PATCH reply')
                    return copy.deepcopy(self.task)
                if set(body) != {'label_config'}: raise AssertionError('Unexpected project mutation')
                self.config = body['label_config']
                return self.project(3)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root/'batch.json').write_bytes(convert.encoded([desired]))
            (root/'old-journal.json').write_bytes(b'old')
            plan = {'originals':{'3918223.xlsx':original},'new_tasks':{'3918223.xlsx':desired},
                    'task_ids':[5], 'batches':[{'file':'batch.json','tasks':1,'sha256':'test'}],
                    'old_config':CONFIG,'new_config':xy_config, 'manifest_sha':'test',
                    'journal_path':root/'new-journal.json','old_journal_path':root/'old-journal.json',
                    'old_journal_sha':convert.sha(b'old')}
            client = UpgradeClient()
            labels = copy.deepcopy(client.task['annotations'])
            with self.assertRaises(TimeoutError):
                upgrade_xy.upgrade(client, 3, plan, root/'backup')
            self.assertFalse(plan['journal_path'].exists())
            upgrade_xy.upgrade(client, 3, plan, root/'backup')
            self.assertEqual(client.patches, 1)
            self.assertEqual(client.task['annotations'], labels)
            self.assertEqual(client.config, xy_config)
            self.assertEqual(json.loads(plan['journal_path'].read_bytes())['completed'][0]['task_ids'], [5])
            with self.assertRaises(ValueError):
                upgrade_xy.upgrade(client, 3, plan, root/'backup')


if __name__ == '__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main(verbosity=2)
