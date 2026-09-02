# 工艺策划助手

这是一个在 Windows 本机运行的 Python 内网页面，统一调用多个 Dify Workflow。

## 当前模块

### 1. 相似零件特征推荐

- 二轴：已建立页面和 DSL 备用表单
- 光孔：已接入并保留原有 API Key
- 副箱：包含花键 I、花键 II、轴承孔、外圆尺寸四个子工作流
- 中间轴：已接入“S档及AMT”子场景，后续可继续增加其他子场景

### 2. 机床快换夹具推荐

已增加“滚齿机床 → 夹具推荐”子场景，包含7个必填数值字段。
在 `config.json` 的 `hobbing_fixture` 场景中填写该Dify应用自己的API Key。
不需要修改现有其他场景密钥。

支持 `POST /api/scenes/hobbing_fixture/run`，请求体为 `{"inputs": {...}}`。
也支持 `POST /api/modules/quick_change_fixture/run`；当前只有一个子场景时自动选择它，
以后有多个子场景时，请在请求体同时传入 `scene_id`。
结果沿用Markdown展示与下载，不强制改成Top5格式。

### 3. 刀具推荐

页面和接口 `POST /api/modules/tool_recommendation/run` 已预留。

## 启动方法

双击 `启动.bat`，保持黑色窗口开启，然后访问：

```text
http://127.0.0.1:8501
```

如果提示缺少 Python 包，在当前文件夹的 PowerShell 中执行：

```powershell
python -m pip install -r requirements.txt
```

## 配置各 Workflow API Key

每个 Dify Workflow 都需要自己的应用 API Key。打开 `config.json`，分别替换以下占位内容：

- `请填写二轴Workflow的API Key`
- `请填写副箱花键I Workflow的API Key`
- `请填写副箱花键II Workflow的API Key`
- `请填写副箱轴承孔Workflow的API Key`
- `请填写副箱外圆尺寸Workflow的API Key`
- `请填写中间轴S档及AMT Workflow的API Key`

光孔现有 API Key 已保留。API Key 不要发送给无关人员，也不要提交到 Git；`config.json` 已被 `.gitignore` 排除。

Dify 控制台如果是 `http://127.0.0.1/apps`，服务 API 地址保持为：

```json
"dify_base_url": "http://127.0.0.1/v1"
```

没有填写 API Key 时，页面仍会根据 DSL 备用配置显示输入表单，但不会执行推荐。

## 添加后续 Workflow

1. 在 Dify 中发布 Workflow 并创建应用 API Key。
2. 在 `config.json` 的 `scenes` 中增加场景、Key 和备用字段。
3. 将场景 ID 放入对应模块的 `scene_ids`。
4. 页面会自动读取 Dify `/parameters` 并生成表单，主体代码不需要修改。

## 允许其他内网电脑访问

本机测试完成后，把 `config.json` 中的监听地址修改为：

```json
"listen_host": "0.0.0.0"
```

重启后，其他电脑可通过 `http://运行程序的电脑IP:8501` 访问。Windows 防火墙询问时，只允许“专用网络”。
