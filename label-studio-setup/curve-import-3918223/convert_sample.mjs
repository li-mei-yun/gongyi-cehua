import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';

const root = new URL('./', import.meta.url);
const inputs = JSON.parse(await fs.readFile(new URL('extracted.json', root), 'utf8'));
const curveRows = inputs.curve.sheets[0].values;
const labelRows = inputs.labels.sheets[0].values;
assert.deepEqual(curveRows[0], ['ID', '结果 ID', '扭矩 (N·m)', '角度 (度)']);
assert.deepEqual(labelRows[0].slice(0,3), ['filename', 'labels', 'curve_type']);
const filename = inputs.curve.path.split('/').at(-1);
const records = labelRows.slice(1).filter(r => r.some(v => v !== null));
const names = new Set();
const counts = {};
for (const record of records) {
  assert(!names.has(record[0]), `Duplicate label filename: ${record[0]}`);
  names.add(record[0]);
  assert([0, 1].includes(record[1]), `Unknown labels code: ${record[1]}`);
  assert(['initial', 'retighten'].includes(record[2]), `Unknown curve_type: ${record[2]}`);
  const group = `${record[1]}|${record[2]}`;
  counts[group] = (counts[group] || 0) + 1;
}
const matches = records.filter(r => r[0] === filename);
assert.equal(matches.length, 1, 'Expected exactly one matching label');
const [,qualityCode,typeCode] = matches[0];
const quality = {0:'正常曲线', 1:'异常曲线'}[qualityCode];
const tighteningType = {initial:'正常拧紧', retighten:'复拧'}[typeCode];
const rows = curveRows.slice(1);
assert(rows.length > 0);
const curveID = Number(filename.replace(/\.xlsx$/i,''));
rows.forEach((r,i) => {
  assert.equal(r.length, 4);
  assert(r.every(Number.isFinite), `Non-numeric sample at row ${i+2}`);
  assert.equal(r[1], curveID, `Mismatched curve ID at row ${i+2}`);
  assert.equal(r[0], i + 1, 'Sample IDs must be sequential; do not silently reorder');
});
const tasks = [{
  data: {
    filename,
    curve_id: String(curveID),
    description: `曲线 ${curveID}｜${rows.length} 个采样点｜横轴为原始 ID（非秒）`,
    source_labels_code: qualityCode,
    source_curve_type: typeCode,
    series: {
      sample_id: rows.map(r=>r[0]),
      torque_nm: rows.map(r=>r[2]),
      angle_deg: rows.map(r=>r[3]),
    },
  },
  annotations: [{
    was_cancelled: false,
    result: [
      {from_name:'quality',to_name:'ts',type:'choices',value:{choices:[quality]}},
      {from_name:'tightening_type',to_name:'ts',type:'choices',value:{choices:[tighteningType]}},
    ],
  }],
  meta: {
    source_curve_file: filename,
    source_curve_sha256: inputs.curve.sha256,
    source_label_file: 'label.xlsx',
    source_label_sha256: inputs.labels.sha256,
    source_label_sheet: inputs.labels.sheets[0].name,
    source_label_excel_row: labelRows.findIndex(r=>r[0] === filename)+1,
    x_axis: 'original sample ID; elapsed time unavailable',
    transformation: 'No sorting, smoothing, filtering, resampling, or numeric rounding.',
  },
}];
for (const source of Object.values(inputs)) {
  const actual = createHash('sha256').update(await fs.readFile(source.path)).digest('hex');
  assert.equal(actual, source.sha256, 'Source changed since extraction');
}
await fs.writeFile(new URL('tasks_3918223.json',root), JSON.stringify(tasks,null,2)+'\n');
const restored = JSON.parse(await fs.readFile(new URL('tasks_3918223.json',root),'utf8'));
rows.forEach((r,i) => assert.deepEqual([
  restored[0].data.series.sample_id[i], Number(restored[0].data.curve_id),
  restored[0].data.series.torque_nm[i], restored[0].data.series.angle_deg[i],
], r));
const report = {
  filename, sample_count:rows.length, source_label_row:tasks[0].meta.source_label_excel_row,
  labels:qualityCode, curve_type:typeCode, quality, tightening_type:tighteningType,
  label_file_records:records.length, label_counts:counts,
  unique_label_filenames:names.size, source_hashes_unchanged:true,
  angle_decreases:rows.filter((r,i)=>i>0 && r[3]<rows[i-1][3]).length,
  angle_repeats:rows.filter((r,i)=>i>0 && r[3]===rows[i-1][3]).length,
  json_numeric_roundtrip:'all samples equal to extracted source',
  actual_label_studio_import:'not performed',
};
await fs.writeFile(new URL('validation.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
