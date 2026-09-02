import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "D:/lmy/中间轴齿轮/最终数据/副箱/花键II.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 12,
  tableMaxCols: 20,
  tableMaxCellChars: 120,
});
console.log(overview.ndjson);

await fs.mkdir("fuxiang_huajian2_workflow/inspection", { recursive: true });
const sheets = (await workbook.inspect({ kind: "sheet", include: "id,name" })).ndjson
  .trim()
  .split(/\r?\n/)
  .map((line) => JSON.parse(line).name)
  .filter(Boolean);

for (const sheetName of sheets) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const safeName = sheetName.replace(/[\\/:*?"<>|]/g, "_");
  await fs.writeFile(
    `fuxiang_huajian2_workflow/inspection/${safeName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}
