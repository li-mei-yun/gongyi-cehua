import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const sources = {
  curve: 'D:/lmy/拧紧曲线/code/Tightening_curve_classification/SCU2020/data/TraceReportExport_Angle_Torque/3918223.xlsx',
  labels: 'D:/lmy/拧紧曲线/code/Tightening_curve_classification/SCU2020/data/label/label.xlsx',
};
const extracted = {};
for (const [key,path] of Object.entries(sources)) {
  const buffer = await fs.readFile(path);
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
  console.log(key, (await workbook.inspect({kind:'workbook,sheet,table', maxChars:4500, tableMaxRows:8, tableMaxCols:12})).ndjson);
  const sheets = JSON.parse('[' + (await workbook.inspect({kind:'sheet',include:'id,name',maxChars:10000})).ndjson.trim().split('\n').join(',') + ']');
  extracted[key] = {path, sha256:createHash('sha256').update(buffer).digest('hex'), sheets:[]};
  // Use the supplied sheet records to resolve each worksheet without guessing its name.
  for (const entry of sheets) {
    if (!entry.name) continue;
    const sheet = workbook.worksheets.getItem(entry.name);
    extracted[key].sheets.push({name:entry.name, values:sheet.getUsedRange().values});
  }
}
await fs.writeFile(new URL('./extracted.json', import.meta.url), JSON.stringify(extracted));
console.log('Extracted sheet shapes:', Object.fromEntries(Object.entries(extracted).map(([k,v]) => [k,v.sheets.map(s=>({name:s.name,rows:s.values.length,columns:s.values[0]?.length}))])));
