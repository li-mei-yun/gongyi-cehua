# Dify：副箱外圆尺寸工作流

## 连线顺序

```text
开始 → SQL候选查询 → 标准化 → 计算相似度 → SQL工艺查询
     → 特征格式整理 → LLM → 结束
```

## 1. 开始节点

建立5个文本输入。外圆直径2、外圆直径3允许为空，其余建议按业务需要设置必填：

| 显示名称 | 变量名 |
|---|---|
| 外圆直径1 | `waiyuanzhijing1` |
| 外圆直径2 | `waiyuanzhijing2` |
| 外圆直径3 | `waiyuanzhijing3` |
| 花键I端中心孔 | `huajian_I_duan_zhongxinkong` |
| 内外螺纹端中心孔 | `neiwailuowenduan_zhongxinkong` |

## 2. SQL候选查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  waiyuanzhijing1,
  waiyuanzhijing2,
  waiyuanzhijing3,
  huajian_I_duan_zhongxinkong,
  neiwailuowenduan_zhongxinkong
FROM fuxiang;
```

## 3. 标准化节点

新建Code / Python节点，粘贴`01_standardize.py`。

输入变量：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `waiyuanzhijing1` | 开始 / `waiyuanzhijing1` | String |
| `waiyuanzhijing2` | 开始 / `waiyuanzhijing2` | String |
| `waiyuanzhijing3` | 开始 / `waiyuanzhijing3` | String |
| `huajian_I_duan_zhongxinkong` | 开始 / 同名变量 | String |
| `neiwailuowenduan_zhongxinkong` | 开始 / 同名变量 | String |
| `sql1` | SQL候选查询 / `json` | Array[Object] |

输出变量全部选择String：

```text
error
user
parts
count
valid_fields
```

代码支持`φ76（+0.025，+0.013）`、`φ75.8（0，-0.05）`、`φ4.8`以及`/`。带公差尺寸会拆成公称值、上偏差、下偏差分别比较。

## 4. 计算相似度节点

新建Code / Python节点，粘贴`02_similarity.py`。

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

权重：外圆直径1为25、外圆直径2为20、外圆直径3为15、两个中心孔各20。缺失输入不参与分母。

## 5. SQL工艺查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  waiyuanzhijing1,
  waiyuanzhijing2,
  waiyuanzhijing3,
  huajian_I_duan_zhongxinkong,
  neiwailuowenduan_zhongxinkong,
  huajian_I_duan_zhongxinzuan_jianju,
  neiwailuowenduan_zhongxinzuan_jianju
FROM fuxiang
WHERE lingjianbianhao IN (
  '{{#计算相似度.id1#}}',
  '{{#计算相似度.id2#}}',
  '{{#计算相似度.id3#}}',
  '{{#计算相似度.id4#}}',
  '{{#计算相似度.id5#}}'
);
```

在Dify中通过变量选择器插入“计算相似度 / id1”至“id5”，不要手动输入节点标签。

## 6. 特征格式整理节点

新建Code / Python节点，粘贴`03_format_report.py`。

输入：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `top5_report` | 计算相似度 / `top5_scores` | String |
| `sql2` | SQL工艺查询 / `json` | Array[Object] |

输出：`report`，类型String。

每个推荐零件固定输出零件编号、5个输入字段和2个检具字段；空值或`/`显示为“未填写”。

## 7. LLM节点

System Prompt：

```text
你是一名资深齿轮工艺工程师。

下面是系统生成的副箱外圆尺寸相似零件推荐结果。

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

## 数据核对说明

《外圆尺寸.xlsx》包含34条数据。Excel最后两列表头误重复为两个中心孔输入字段，但列内内容实际是检具数据；本工作流使用用户指定的正确数据库字段名。Excel没有`lingjianbianhao`，Top5二次反查要求数据库表`fuxiang`中存在该字段。
