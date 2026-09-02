# Dify：副箱轴承孔工作流

## 工作流连线

```text
开始 → SQL候选查询 → 标准化 → 计算相似度 → SQL工艺查询
     → 特征格式整理 → LLM → 结束
```

## 1. 开始节点

建立2个文本输入，建议都设为必填：

| 显示名称 | 变量名 |
|---|---|
| 轴承孔孔径 | `zhouchengkong_kongjing` |
| 轴承孔孔深 | `zhouchengkong_kongshen` |

## 2. SQL候选查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  zhouchengkong_kongjing,
  zhouchengkong_kongshen
FROM fuxiang;
```

## 3. 标准化节点

新建Code / Python节点，粘贴 `01_standardize.py`。

输入变量：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `kongjing` | 开始 / `zhouchengkong_kongjing` | String |
| `kongshen` | 开始 / `zhouchengkong_kongshen` | String |
| `sql1` | SQL候选查询 / `json` | Array[Object] |

输出变量全部选择String：

```text
error
user
parts
count
valid_fields
```

孔径会被解析为公称值、上偏差、下偏差。例如`φ49.5（+0.047，+0.032）`解析为`49.5`、`+0.047`、`+0.032`；`/`会被视为空值。

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

总权重：孔径60、孔深40。孔径内部权重为公称值70%、上偏差15%、下偏差15%。缺失输入不参与分母。

## 5. SQL工艺查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  zhouchengkong_kongjing,
  zhouchengkong_kongshen,
  zhouchengkong_reqiantangkong_kongshen,
  zhouchengkong_reqiantangkong_saigui,
  zhouchengkong_reqiantangkong_tangkongjiaju,
  zhouchengkong_rehoutangkong_kongjing,
  zhouchengkong_rehoutangkong_kongshen,
  zhouchengkong_rehoutangkong_qidongliangyi,
  zhouchengkong_rehoutangkong_tangkongjiaju
FROM fuxiang
WHERE lingjianbianhao IN (
  '{{#计算相似度.id1#}}',
  '{{#计算相似度.id2#}}',
  '{{#计算相似度.id3#}}',
  '{{#计算相似度.id4#}}',
  '{{#计算相似度.id5#}}'
);
```

在Dify编辑器中必须通过变量选择器插入“计算相似度 / id1”至“id5”，不要手动输入节点标签。

## 6. 特征格式整理节点

新建Code / Python节点，粘贴 `03_format_report.py`。

输入：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `top5_report` | 计算相似度 / `top5_scores` | String |
| `sql2` | SQL工艺查询 / `json` | Array[Object] |

输出：`report`，类型String。

每个推荐零件固定输出零件编号、2个输入字段和7个工艺字段；数据库中的空值或`/`显示为“未填写”。

## 7. LLM节点

沿用之前工作流中的模型。System Prompt：

```text
你是一名资深齿轮工艺工程师。

下面是系统生成的副箱轴承孔相似零件推荐结果。

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

最后一行用变量选择器插入“特征格式整理 / report”。建议Temperature为`0.2`、Top P为`0.8`。

## 8. 结束节点

建立输出：`text` = LLM / `text`，类型String。

## 数据核对说明

《轴承孔.xlsx》共34条记录，其中前6条是有效工艺数据，其余28条全部为`/`占位。Excel没有`lingjianbianhao`列，但Top5二次反查要求数据库表`fuxiang`中存在该字段。
