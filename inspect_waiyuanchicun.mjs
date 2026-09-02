import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "D:/lmy/中间轴齿轮/最终数据/副箱/外圆尺寸.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 20000,
  tableMaxRows: 50,
  tableMaxCols: 15,
  tableMaxCellChars: 180,
});
console.log(overview.ndjson);

await fs.mkdir("waiyuanchicun_workflow/inspection", { recursive: true });
const sheets = (await workbook.inspect({ kind: "sheet", include: "id,name" })).ndjson
  .trim()
  .split(/\r?\n/)
  .map((line) => JSON.parse(line).name)
  .filter(Boolean);

for (const sheetName of sheets) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const safeName = sheetName.replace(/[\\/:*?"<>|]/g, "_");
  await fs.writeFile(
    `waiyuanchicun_workflow/inspection/${safeName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}
