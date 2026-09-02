"""Create the lightweight live-chart package from the verified original package."""
import json
from pathlib import Path
from convert import atomic_write, encoded, pack_batches, sha
from import_batches import validate_package

BASE=Path(__file__).resolve().parent
source=BASE/'package-scu2020'; output=BASE/'package-scu2020-live'
original, source_sha, _=validate_package(source)
config=(BASE/'project_config_live.xml').read_bytes()
output.mkdir(exist_ok=True);(output/'batches').mkdir(exist_ok=True)
batches=[]; total=0
for old_index,old_batch in enumerate(original['batches'],1):
    tasks=json.loads((source/old_batch['file']).read_bytes())
    payloads=[]
    for task in tasks:
        before=json.loads(json.dumps(task))
        task['data']['plot_url']='http://127.0.0.1:8091/plot/'+task['data']['curve_id']
        check=dict(task['data']);check.pop('plot_url')
        assert check==before['data'] and task['annotations']==before['annotations']
        payloads.append(encoded(task));total+=1
    for sub,(raw,count) in enumerate(pack_batches(payloads,500,8*1024**2),1):
        filename=f'batches/batch_{old_index:04d}_{sub:02d}.json';atomic_write(output/filename,raw)
        batches.append({'file':filename,'tasks':count,'bytes':len(raw),'sha256':sha(raw),'source_batch':old_batch['file']})
manifest={k:v for k,v in original.items() if k not in ('batches','config_sha256','dataset_id')}
manifest.update(config_sha256=sha(config),dataset_id=sha(config+source_sha.encode()),source_manifest_sha256=source_sha,presentation='live_torque_vs_angle_v1',batches=batches)
atomic_write(output/'project_config.xml',config);atomic_write(output/'manifest.json',encoded(manifest));validate_package(output)
summary={'tasks':total,'batches':len(batches),'bytes':sum(b['bytes'] for b in batches),'images':0,'original_data_and_annotations_preserved':True,'requires_plot_server':'127.0.0.1:8091'}
atomic_write(output/'summary.json',encoded(summary));print(json.dumps(summary,indent=2))
