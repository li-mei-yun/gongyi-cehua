"""Create a separate XY presentation package; preserve every original data/annotation field."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import time
from convert import atomic_write, encoded, pack_batches, sha
from import_batches import validate_package
from xy_plot import data_uri

BASE = Path(__file__).resolve().parent


def enrich_task(task):
    task['data']['angle_torque_plot'] = data_uri(task)
    return task


def prepare(source, output, workers):
    original, source_manifest_sha, _ = validate_package(source)
    config = (BASE / 'project_config_xy.xml').read_bytes()
    output.mkdir(exist_ok=True)
    (output / 'batches').mkdir(exist_ok=True)
    (output / 'source-checkpoints').mkdir(exist_ok=True)
    identity = {'source_manifest_sha256': source_manifest_sha, 'config_sha256': sha(config),
                'plotter_sha256': sha((BASE / 'xy_plot.py').read_bytes())}
    snapshot = output / 'xy-source.json'
    if snapshot.exists() and json.loads(snapshot.read_bytes()) != identity:
        raise ValueError('XY inputs/renderer changed; use a new output directory')
    atomic_write(snapshot, encoded(identity))
    atomic_write(output / 'project_config.xml', config)
    batches, point_count = [], 0
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for old_index, old_batch in enumerate(original['batches'], 1):
            checkpoint = output / 'source-checkpoints' / f'{old_index:04d}.json'
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_bytes())
                for b in saved:
                    if sha((output / b['file']).read_bytes()) != b['sha256']:
                        raise ValueError('XY batch checksum mismatch')
                batches.extend(saved)
                print(f'Resumed source batch {old_index}/{len(original["batches"])}', flush=True)
                continue
            tasks = json.loads((source / old_batch['file']).read_bytes())
            # Keep the original batch boundary so an already-imported prefix can be adopted safely.
            rendered = executor.map(enrich_task, tasks, chunksize=8)
            group = []
            def payloads():
                nonlocal point_count
                for old_task, new_task in zip(tasks, rendered):
                    check = dict(new_task['data'])
                    check.pop('angle_torque_plot')
                    if check != old_task['data'] or new_task['annotations'] != old_task['annotations']:
                        raise ValueError('A source data/annotation field changed')
                    point_count += len(new_task['data']['series']['sample_id'])
                    yield encoded(new_task)
            for sub_index, (raw, count) in enumerate(pack_batches(payloads(), 500, 8*1024**2), 1):
                filename = f'batches/batch_{old_index:04d}_{sub_index:02d}.json'
                atomic_write(output / filename, raw)
                entry = {'file': filename, 'tasks': count, 'bytes': len(raw), 'sha256': sha(raw),
                         'source_batch': old_batch['file']}
                group.append(entry)
            batches.extend(group)
            atomic_write(checkpoint, encoded(group))
            print(f'XY rendered source batch {old_index}/{len(original["batches"])}; elapsed={time.monotonic()-started:.0f}s', flush=True)
    manifest = {k:v for k,v in original.items() if k not in ('batches','config_sha256','dataset_id')}
    manifest.update(config_sha256=sha(config), dataset_id=sha(encoded(identity)),
                    source_manifest_sha256=source_manifest_sha, presentation='torque_vs_angle_svg_v1', batches=batches)
    atomic_write(output / 'manifest.json', encoded(manifest))
    validate_package(output)
    summary = {'tasks':manifest['task_count'], 'points':manifest['sample_count'], 'batches':len(batches),
               'bytes':sum(b['bytes'] for b in batches), 'original_data_and_annotations_preserved': True,
               'uploaded':False}
    atomic_write(output / 'summary.json', encoded(summary))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=BASE/'package-scu2020')
    parser.add_argument('--output', type=Path, default=BASE/'package-scu2020-xy')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    prepare(args.source, args.output, args.workers)
