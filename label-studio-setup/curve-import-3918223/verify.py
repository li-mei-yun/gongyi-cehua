"""Independent, read-only OOXML check; no spreadsheet authoring."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

root = Path(__file__).resolve().parent
extracted = json.loads((root / 'extracted.json').read_text(encoding='utf-8'))
tasks = json.loads((root / 'tasks_3918223.json').read_text(encoding='utf-8'))
ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
source_path = Path(extracted['curve']['path'])
with ZipFile(source_path) as archive:
    sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    source_rows = sheet.findall('s:sheetData/s:row', ns)[1:]
    for i, row in enumerate(source_rows):
        cells = {cell.attrib['r']:cell for cell in row.findall('s:c', ns)}
        rownum = row.attrib['r']
        assert all(cell.find('s:f',ns) is None for cell in cells.values())
        values = [float(cells[f'{col}{rownum}'].find('s:v',ns).text) for col in 'ABCD']
        series = tasks[0]['data']['series']
        actual = [series['sample_id'][i], int(tasks[0]['data']['curve_id']), series['torque_nm'][i], series['angle_deg'][i]]
        assert actual == values, (i,actual,values)
    assert len(source_rows) == len(tasks[0]['data']['series']['sample_id']) == 615

config = ET.parse(root / 'project_config.xml').getroot()
named = {node.attrib['name']:node for node in config.iter() if 'name' in node.attrib}
for result in tasks[0]['annotations'][0]['result']:
    control = named[result['from_name']]
    assert control.tag.lower() == result['type']
    assert control.attrib['toName'] == result['to_name']
    assert result['to_name'] in named
    allowed = {choice.attrib['value'] for choice in control.findall('Choice')}
    assert set(result['value']['choices']) <= allowed
ts = named['ts']
assert ts.attrib['valueType'] == 'json'
series = tasks[0]['data'][ts.attrib['value'][1:]]
assert all(b > a for a,b in zip(series[ts.attrib['timeColumn']], series[ts.attrib['timeColumn']][1:]))
assert all(channel.attrib['column'] in series for channel in ts.findall('Channel'))
assert len({len(v) for v in series.values()}) == 1
for source in extracted.values():
    assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
print('PASS: 615 samples equal original OOXML values; XML/annotation/data fields match; sources unchanged.')
