# Dify：副箱花键II工作流

节点顺序：

```text
开始 → SQL候选查询 → 标准化 → 计算相似度 → SQL工艺查询
     → 特征格式整理 → LLM → 结束
```

## 1. 开始节点

建立4个文本输入，建议全部设为必填：

| 显示名称 | 变量名 |
|---|---|
| 花键II齿数 | `huajian_II_chishu` |
| 花键II模数 | `huajian_II_moshu` |
| 花键II压力角 | `huajian_II_yalijiao` |
| 花键II螺旋角 | `huajian_II_luoxuanjiao` |

## 2. SQL候选查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  huajian_II_chishu,
  huajian_II_moshu,
  huajian_II_yalijiao,
  huajian_II_luoxuanjiao
FROM fuxiang;
```

## 3. 标准化节点

新建Code / Python节点，粘贴 `01_standardize.py`。

输入变量：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `chishu` | 开始 / `huajian_II_chishu` | String |
| `moshu` | 开始 / `huajian_II_moshu` | String |
| `yalijiao` | 开始 / `huajian_II_yalijiao` | String |
| `luoxuanjiao` | 开始 / `huajian_II_luoxuanjiao` | String |
| `sql1` | SQL候选查询 / `json` | Array[Object] |

输出变量全部选择String：

```text
error
user
parts
count
valid_fields
```

该代码支持模数纯数字（`1.5`、`2.5`）和斜杠双值（`10/20`、`20/40`），角度中的`°`会自动处理。

## 4. 计算相似度节点

新建Code / Python节点，粘贴 `02_similarity.py`。

输入：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `user` | 标准化 / `user` | String |
| `parts` | 标准化 / `parts` | String |

输出变量必须逐项手动建立，全部选择String：

```text
used_features
candidate_count
id1
id2
id3
id4
id5
top5_scores
```

权重：齿数30、模数30、压力角20、螺旋角20。缺失输入不参与分母。

## 5. SQL工艺查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  huajian_II_chishu,
  huajian_II_moshu,
  huajian_II_yalijiao,
  huajian_II_luoxuanjiao,
  huajian_II_gongyi,
  huajian_II_rehouhuajianhuangui,
  huajian_II_gunhuajian_gundao,
  huajian_II_gunhuajian_gunchi_M_zhi_dp,
  huajian_II_gunhuajian_gunchijiaju
FROM fuxiang
WHERE lingjianbianhao IN (
  '{{#计算相似度.id1#}}',
  '{{#计算相似度.id2#}}',
  '{{#计算相似度.id3#}}',
  '{{#计算相似度.id4#}}',
  '{{#计算相似度.id5#}}'
);
```

`{{#...#}}`仅表示变量位置。在Dify编辑器中应使用变量选择器依次插入“计算相似度 / id1”至“id5”，不要手敲节点名称。

## 6. 特征格式整理节点

新建Code / Python节点，粘贴 `03_format_report.py`。

输入：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `top5_report` | 计算相似度 / `top5_scores` | String |
| `sql2` | SQL工艺查询 / `json` | Array[Object] |

输出：`report`，类型String。

该节点为每个推荐零件固定输出零件编号、4个输入字段和5个工艺字段；数据库空值显示为“未填写”。

## 7. LLM节点

沿用花键I使用的模型。System Prompt：

```text
你是一名资深齿轮工艺工程师。

下面是系统生成的副箱花键II相似零件推荐结果。

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

最后一行通过变量选择器插入“特征格式整理 / report”。建议Temperature为`0.2`、Top P为`0.8`。

## 8. 结束节点

建立输出：`text` = LLM / `text`，类型String。

## 数据说明

已检查《花键II.xlsx》：共34条数据，4个输入字段和5个工艺字段均存在。该Excel不包含`lingjianbianhao`，但Top5二次反查必须依赖数据库中`fuxiang.lingjianbianhao`列。
