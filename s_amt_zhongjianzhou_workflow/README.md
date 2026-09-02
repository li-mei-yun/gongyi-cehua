# Dify：S及AMT中间轴工作流

数据库表：`s_amt_zhongjianzhou`

## 工作流连线

```text
开始 → SQL候选查询 → 标准化 → 计算相似度 → SQL工艺查询
     → 特征格式整理 → LLM → 结束
```

所有开始节点输入都设置为“非必填”，用户至少填写一个有效条件即可。

## 1. 开始节点

建立以下14个文本输入：

| 显示名称 | 变量名 |
|---|---|
| 轴段轴头是否有端面钻镗孔 | `zd_duanmianzuantangkong` |
| 轴段端面铣槽 | `zd_duanmianxicao` |
| 轴段轴承外圆尺寸 | `zd_zhouchengwaiyuan` |
| 轴段卡簧结构尺寸 | `zd_kahuangjiegou` |
| 轴段大外圆尺寸 | `zd_dawaiyuan` |
| 齿圈段轴承外圆尺寸 | `cq_zhouchengwaiyuan` |
| 齿圈段面到台阶端面轴向长度 | `cq_zhouxiangchangdu` |
| 齿圈段轴头是否铲内花键 | `cq_chaneihuajian` |
| 齿圈段轴头是否铣缺口 | `cq_xiquekou` |
| 倒挡齿圈齿部参数 | `cq_daodang_chibu` |
| 一挡齿圈齿部参数 | `cq_yidang_chibu` |
| 两齿圈间轴径 | `cq_chiquanjianzhoujing` |
| 开档尺寸 | `cq_kaidangchicun` |
| 卡簧槽端台阶轴径 | `cq_kahuangtaijiezhoujing` |

以上短变量名仅用于Dify开始节点和Code节点，均不超过30个字符。数据库字段名不改，SQL中仍使用原来的完整字段名；`01_standardize.py`会自动完成短变量名到数据库字段名的映射。

## 2. SQL候选查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  zhouduan_zhoutoushifouyouduanmianzuantangkong,
  zhouduan_duanmianxicao,
  zhouduan_zhouchengwaiyuanchicun,
  zhouduan_kahuangjiegouchicun,
  zhouduan_dawaiyuanchicun,
  chiquanduan_zhouchengwaiyuanchicun,
  chiquanduan_chiquanduanmiandaotaijieduanmianzhouxiangzhangdu,
  chiquanduan_zhoutoushifouchaneihuajian,
  chiquanduan_zhoutoushifouxiquekou,
  chiquanduan_daodangchiquan_chibucanshu,
  chiquanduan_yidangchiquan_chibucanshu,
  chiquanduan_liangchiquanjianzhoujing,
  chiquanduan_kaidangchicun,
  chiquanduan_kahuangcaoduantaijiezhoujing
FROM s_amt_zhongjianzhou;
```

## 3. 标准化节点

新建Code / Python节点，粘贴`01_standardize.py`。

输入变量与开始节点的14个同名变量逐一连接，全部为String；另增加：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `sql1` | SQL候选查询 / `json` | Array[Object] |

输出变量全部选择String：

```text
error
user
parts
count
valid_fields
```

标准化规则：

- `/`、`-`、空字符串视为未输入；`否`和`无`是有效分类值。
- 尺寸字段自动提取全部尺寸、公差和多行数值。
- 两组齿部参数自动提取齿数、模数、压力角、螺旋角、分度圆直径和齿宽。
- 支持只填写部分输入条件。

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

相对权重：

| 特征 | 权重 |
|---|---:|
| 4个是否/文字特征 | 各4 |
| 8个尺寸特征 | 各5 |
| 倒挡齿圈齿部参数 | 20 |
| 一挡齿圈齿部参数 | 20 |

齿部参数内部权重：齿数25、模数25、压力角15、螺旋角15、分度圆直径5、齿宽15。只有用户实际填写的字段进入总权重；用户填写但候选零件缺失的字段按0分处理。

## 5. SQL工艺查询节点

Database / SQL Execute，输出格式选择JSON：

```sql
SELECT
  lingjianbianhao,
  chanpinmingcheng,
  chiquanduan_daodangchiquan_guanjiangongxujiagongfangshi,
  chiquanduan_daodangchiquan_mochishebeixinghao,
  chiquanduan_daodangchiquan_mochijiaju,
  chiquanduan_yidangchiquan_guanjiangongxujiagongfangshi,
  chiquanduan_yidangchiquan_mochishebeixinghao,
  chiquanduan_yidangchiquan_mochijiaju
FROM s_amt_zhongjianzhou
WHERE lingjianbianhao IN (
  '{{#计算相似度.id1#}}',
  '{{#计算相似度.id2#}}',
  '{{#计算相似度.id3#}}',
  '{{#计算相似度.id4#}}',
  '{{#计算相似度.id5#}}'
);
```

在Dify中必须通过变量选择器插入“计算相似度 / id1”至“id5”，不要手动输入蓝色变量标签。

如果数据库中的`lingjianbianhao`是纯数字类型，建议把WHERE部分改成不带单引号的变量：

```sql
WHERE lingjianbianhao IN (
  {{#计算相似度.id1#}},
  {{#计算相似度.id2#}},
  {{#计算相似度.id3#}},
  {{#计算相似度.id4#}},
  {{#计算相似度.id5#}}
)
```

## 6. 特征格式整理节点

新建Code / Python节点，粘贴`03_format_report.py`。

输入：

| 代码变量 | 上游变量 | 类型 |
|---|---|---|
| `top5_scores` | 计算相似度 / `top5_scores` | String |
| `sql2` | SQL工艺查询 / `json` | Array[Object] |

输出：`report`，类型String。

报告按“基本信息、倒挡齿圈、一挡齿圈”分组，用短中文标签展示；数据库空值显示为“未填写”。

## 7. LLM节点

System Prompt：

```text
你是一名资深齿轮工艺工程师。

下面是系统生成的S及AMT中间轴相似零件工艺推荐结果。

要求：
1. 保留所有数据内容。
2. 不允许修改任何数值、零件编号、设备型号或夹具编号。
3. 不允许新增不存在的数据。
4. 不允许删除任何推荐零件。
5. 不允许改变Top5排序。
6. 按“基本信息、倒挡齿圈、一挡齿圈”进行专业化排版。
7. 不允许修改参数名称。
8. 开头必须列出Top5零件编号和相似度。

推荐结果如下：
{{#特征格式整理.report#}}
```

最后一行通过变量选择器插入“特征格式整理 / report”。建议Temperature为`0.2`、Top P为`0.8`。

## 8. 结束节点

建立输出：

| 输出变量 | 上游变量 | 类型 |
|---|---|---|
| `text` | LLM / `text` | String |

## 字段核对

工作流按改表后的字段设计：2个基本输出、3个倒挡齿圈输出、3个一挡齿圈输出，14列作为可选输入。用户请求中的`ingjianbianhao`按表中实际字段`lingjianbianhao`处理。
