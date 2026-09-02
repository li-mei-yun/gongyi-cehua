# Dify：副箱花键1工作流

沿用“光孔”工作流的核心：全表候选召回 → 特征标准化 → Top5 相似度 → 按零件编号查询工艺 → 格式化 → LLM。
因为本场景只有 `fuxiang` 一张表，所以删除了原流程中“12档/S档”的重复查询及合并节点。

## 节点1：开始

建立 5 个 `文本输入`（建议全部设为必填）：

| 显示名称 | 变量名 |
|---|---|
| 齿数 | `chishu` |
| 模数 | `moshu` |
| 压力角 | `yalijiao` |
| 螺旋角 | `luoxuanjiao` |
| 标准 | `biaozhun` |

## 节点2：SQL 候选查询

使用 Database / SQL Execute，输出格式选择 JSON。

推荐 SQL（齿数必须查询出来才能参与相似度）：

```sql
SELECT
  lingjianbianhao,
  huajian_I_chishu,
  huajian_I_moshu,
  huajian_I_yalijiao,
  huajian_I_luoxuanjiao,
  huajian_I_biaozhun
FROM fuxiang;
```

如果数据库的齿数字段并非 `huajian_I_chishu`，只需将上面列名及后续 SQL 中该列名换成实际字段名。严格使用用户所给 SQL 也能运行，但齿数不会参与匹配。

## 节点3：标准化（Code / Python）

代码见 `01_standardize.py`。

输入变量映射：

| 代码变量 | Dify 上游变量 | 类型 |
|---|---|---|
| `chishu` | 开始 / `chishu` | string |
| `moshu` | 开始 / `moshu` | string |
| `yalijiao` | 开始 / `yalijiao` | string |
| `luoxuanjiao` | 开始 / `luoxuanjiao` | string |
| `biaozhun` | 开始 / `biaozhun` | string |
| `sql1` | SQL候选查询 / `json` | array[object] |

输出全部为 string：`error`、`user`、`parts`、`count`、`valid_fields`。

## 节点4：计算相似度（Code / Python）

代码见 `02_similarity.py`。

输入：

- `user` = 标准化 / `user`，string
- `parts` = 标准化 / `parts`，string

输出全部为 string：`used_features`、`candidate_count`、`id1`、`id2`、`id3`、`id4`、`id5`、`top5_scores`。

权重：齿数 25、模数 25、压力角 15、螺旋角 15、标准 20。缺失字段不计入分母；标准采用完全匹配。

模数同时支持纯数字（如 `4.233`）和斜杠双值（如 `6.4/12.8`）。双值与双值按顺序分别比较后取平均；双值与单值比较时取最接近的一个分量。

标准支持 `非标`、`TESS-EX0603018-1`、`EXT 20Z×4m×30P×6f GB/T 3478.1` 等任意文本。匹配前会忽略大小写和空格，并将 `×/x/X` 及常见连字符写法统一；不同标准之间仍按不匹配处理。

## 节点5：SQL 工艺查询

使用 Database / SQL Execute，输出格式选择 JSON：

```sql
SELECT
  lingjianbianhao,
  huajian_I_chishu,
  huajian_I_moshu,
  huajian_I_yalijiao,
  huajian_I_luoxuanjiao,
  huajian_I_biaozhun,
  huajian_I_gongyi,
  huajian_I_rehouhuajianhuangui,
  huajian_I_gunhuajian_gundao,
  huajian_I_gunhuajian_gunchi_M_zhi,
  huajian_I_gunhuajian_gunchijiaju
FROM fuxiang
WHERE lingjianbianhao IN (
  '{{#计算相似度.id1#}}',
  '{{#计算相似度.id2#}}',
  '{{#计算相似度.id3#}}',
  '{{#计算相似度.id4#}}',
  '{{#计算相似度.id5#}}'
);
```

在 Dify 编辑器中不要手敲 `计算相似度` 这几个引用；用变量选择器依次插入节点4的 `id1` 至 `id5`。Dify 保存后会自动变成带节点 ID 的 `{{#...#}}`。

## 节点6：特征格式整理（Code / Python）

代码见 `03_format_report.py`。

输入：

- `top5_report` = 计算相似度 / `top5_scores`，string
- `sql2` = SQL工艺查询 / `json`，array[object]

输出：`report`，string。

该节点会为每个推荐零件固定输出全部 11 个字段；数据库中的空值显示为“未填写”，不会省略字段。

## 节点7：LLM

可继续使用原“光孔”流程中的模型。System Prompt：

```text
你是一名资深齿轮工艺工程师。

下面是系统已经生成的副箱花键1相似零件推荐结果。

要求：
1. 保留所有数据内容。
2. 不允许修改任何数值。
3. 不允许新增不存在的数据。
4. 不允许删除任何零件。
5. 不允许改变Top5排序。
6. 对内容进行专业化排版，并增加适当标题和分段。
7. 不允许修改参数名称。
8. 开头必须列出Top5零件编号和相似度。

推荐结果如下：
{{#特征格式整理.report#}}
```

最后一行同样应使用 Dify 变量选择器插入节点6的 `report`。

建议参数：Temperature `0.2`、Top P `0.8`；其余保持模型默认值。

## 节点8：结束

输出变量：

- `text` = LLM / `text`

## 连线顺序

```text
开始 → SQL候选查询 → 标准化 → 计算相似度 → SQL工艺查询
     → 特征格式整理 → LLM → 结束
```
