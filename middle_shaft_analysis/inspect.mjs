import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "D:/lmy/中间轴齿轮/初始表格/中间轴产品信息梳理 分类 分系列-V2.2-整理.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 });
console.log(sheets.ndjson);

const region = await workbook.inspect({
  kind: "table",
  sheetId: "8,,9,10,11,12档S及AMT中间轴",
  range: "A1:W15",
  tableMaxRows: 15,
  tableMaxCols: 23,
  tableMaxCellChars: 500,
  maxChars: 40000,
});
console.log(region.ndjson);
