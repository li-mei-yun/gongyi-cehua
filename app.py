from __future__ import annotations

import getpass
import html
import json
import math
import threading
import webbrowser
from pathlib import Path
from typing import Any

import markdown as markdown_lib
import requests
from flask import Flask, jsonify, render_template, request


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

app = Flask(__name__)


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise AppError("缺少 config.json，请根据 config.example.json 创建配置文件。", 500)

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(f"读取 config.json 失败：{exc}", 500) from exc

    if not isinstance(config.get("scenes"), list):
        raise AppError("config.json 中缺少 scenes 列表。", 500)
    return config


def find_scene(config: dict[str, Any], scene_id: str) -> dict[str, Any]:
    for scene in config["scenes"]:
        if scene.get("id") == scene_id:
            return scene
    raise AppError("没有找到对应的推荐场景。", 404)


def find_module(config: dict[str, Any], module_id: str) -> dict[str, Any]:
    for module in config.get("modules") or []:
        if module.get("id") == module_id:
            return module
    raise AppError("没有找到对应的工艺策划模块。", 404)


def api_key_is_configured(scene: dict[str, Any]) -> bool:
    api_key = str(scene.get("api_key", "")).strip()
    return bool(api_key and "请填写" not in api_key and "your-" not in api_key.lower())


def get_dify_base_url(config: dict[str, Any]) -> str:
    url = str(config.get("dify_base_url", "http://127.0.0.1/v1")).strip().rstrip("/")
    if url.endswith("/apps"):
        url = url[:-5] + "/v1"
    return url


def public_scene(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": scene.get("id"),
        "name": scene.get("name", scene.get("id")),
        "description": scene.get("description", ""),
        "configured": api_key_is_configured(scene),
        "status": scene.get("status", "active"),
    }


def public_module(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": module.get("id"),
        "number": module.get("number", ""),
        "name": module.get("name", module.get("id")),
        "description": module.get("description", ""),
        "status": module.get("status", "planned"),
        "endpoint": module.get("endpoint", ""),
        "groups": module.get("groups") or [],
    }


def normalize_dify_fields(user_input_form: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in user_input_form:
        if not isinstance(item, dict) or not item:
            continue

        field_type, metadata = next(iter(item.items()))
        if not isinstance(metadata, dict) or not metadata.get("variable"):
            continue

        fields.append(
            {
                "type": field_type,
                "variable": metadata["variable"],
                "label": str(metadata.get("label") or metadata["variable"]).strip(),
                "required": bool(metadata.get("required", False)),
                "default": metadata.get("default", ""),
                "options": metadata.get("options") or [],
                "max_length": metadata.get("max_length"),
                "placeholder": metadata.get("placeholder") or "",
            }
        )
    return fields


def normalize_local_fields(local_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in local_fields:
        if not item.get("variable"):
            continue
        fields.append(
            {
                "type": item.get("type", "text-input"),
                "variable": item["variable"],
                "label": str(item.get("label") or item["variable"]).strip(),
                "required": bool(item.get("required", False)),
                "default": item.get("default", ""),
                "options": item.get("options") or [],
                "max_length": item.get("max_length", 48),
                "placeholder": item.get("placeholder") or "",
            }
        )
    return fields


def fetch_scene_form(config: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    fallback = normalize_local_fields(scene.get("fields") or [])

    if not api_key_is_configured(scene):
        if fallback:
            return {
                "fields": fallback,
                "source": "local",
                "warning": "当前显示的是 DSL 备用表单。请在 config.json 中填写该 Workflow 的 API Key 后运行。",
            }
        raise AppError("该场景尚未配置 Dify API Key，也没有备用表单。", 400)

    try:
        response = requests.get(
            f"{get_dify_base_url(config)}/parameters",
            headers={"Authorization": f"Bearer {scene['api_key'].strip()}"},
            timeout=15,
        )
        response.raise_for_status()
        fields = normalize_dify_fields(response.json().get("user_input_form") or [])
        if not fields:
            raise ValueError("Dify 没有返回 user_input_form")
        return {"fields": fields, "source": "dify", "warning": ""}
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        if fallback:
            return {
                "fields": fallback,
                "source": "local",
                "warning": f"暂时无法读取 Dify 表单，已使用 DSL 备用表单。原因：{exc}",
            }
        raise AppError(f"读取 Dify 表单失败：{exc}", 502) from exc


def validate_inputs(fields: list[dict[str, Any]], raw_inputs: Any) -> dict[str, Any]:
    if not isinstance(raw_inputs, dict):
        raise AppError("提交的 inputs 格式不正确。")

    values: dict[str, Any] = {}
    for field in fields:
        variable = field["variable"]
        value = raw_inputs.get(variable, "")

        if isinstance(value, str):
            value = value.strip()

        if value in ("", None):
            if field["required"]:
                raise AppError(f"“{field['label']}”为必填项。")
            continue

        if field["type"] == "number":
            try:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError("non-finite number")
                value = int(number) if number.is_integer() else number
            except (TypeError, ValueError) as exc:
                raise AppError(f"“{field['label']}”必须是数字。") from exc

        values[variable] = value

    if not values:
        raise AppError("请至少填写一个零件特征后再开始推荐。")
    return values


def output_to_text(outputs: dict[str, Any]) -> str:
    for preferred_key in ("text", "result", "answer", "report"):
        value = outputs.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value

    for value in outputs.values():
        if isinstance(value, str) and value.strip():
            return value

    return json.dumps(outputs, ensure_ascii=False, indent=2)


def markdown_to_safe_html(text: str) -> str:
    escaped = html.escape(text)
    return markdown_lib.markdown(
        escaped,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )


@app.errorhandler(AppError)
def handle_app_error(error: AppError):
    return jsonify({"ok": False, "error": error.message}), error.status_code


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    app.logger.exception("未处理的异常")
    return jsonify({"ok": False, "error": f"程序运行异常：{error}"}), 500


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/scenes")
def list_scenes():
    config = load_config()
    scenes = [public_scene(scene) for scene in config["scenes"] if scene.get("id")]
    return jsonify(
        {
            "ok": True,
            "scenes": scenes,
            "dify_base_url": get_dify_base_url(config),
        }
    )


@app.get("/api/catalog")
def get_catalog():
    config = load_config()
    return jsonify(
        {
            "ok": True,
            "product_name": "工艺策划助手",
            "dify_base_url": get_dify_base_url(config),
            "modules": [public_module(module) for module in config.get("modules") or []],
            "scenes": [public_scene(scene) for scene in config["scenes"] if scene.get("id")],
        }
    )


@app.get("/api/modules/<module_id>")
def get_module(module_id: str):
    config = load_config()
    module = find_module(config, module_id)
    return jsonify({"ok": True, "module": public_module(module)})


@app.post("/api/modules/<module_id>/run")
def run_module(module_id: str):
    config = load_config()
    module = find_module(config, module_id)
    if module.get("status") != "active":
        raise AppError(f"“{module.get('name', module_id)}”接口已预留，当前尚未接入 Dify Workflow。", 501)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise AppError("请提交JSON对象。")
    allowed = [sid for group in module.get("groups", []) for sid in group.get("scene_ids", [])]
    scene_id = body.get("scene_id") or (allowed[0] if len(allowed) == 1 else None)
    if scene_id not in allowed:
        raise AppError("请指定该模块下有效的 scene_id。")
    return run_scene(scene_id)


@app.get("/api/scenes/<scene_id>/form")
def get_scene_form(scene_id: str):
    config = load_config()
    scene = find_scene(config, scene_id)
    if scene.get("status") == "planned":
        raise AppError(f"“{scene.get('name', scene_id)}”表单接口已预留，当前尚未接入 Dify Workflow。", 501)
    form = fetch_scene_form(config, scene)
    return jsonify({"ok": True, **form})


@app.post("/api/scenes/<scene_id>/run")
def run_scene(scene_id: str):
    config = load_config()
    scene = find_scene(config, scene_id)
    if scene.get("status") == "planned":
        raise AppError(f"“{scene.get('name', scene_id)}”接口已预留，当前尚未接入 Dify Workflow。", 501)
    if not api_key_is_configured(scene):
        raise AppError("请先在 config.json 中填写该 Workflow 的 API Key。")

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise AppError("请提交JSON对象。")
    form = fetch_scene_form(config, scene)
    inputs = validate_inputs(form["fields"], body.get("inputs"))

    user = str(body.get("user") or request.remote_addr or getpass.getuser()).strip()
    user = user[:128] or "intranet-user"

    try:
        response = requests.post(
            f"{get_dify_base_url(config)}/workflows/run",
            headers={
                "Authorization": f"Bearer {scene['api_key'].strip()}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": inputs,
                "response_mode": "blocking",
                "user": user,
            },
            timeout=int(config.get("workflow_timeout_seconds", 300)),
        )
    except requests.RequestException as exc:
        raise AppError(f"无法连接 Dify：{exc}", 502) from exc

    try:
        result = response.json()
    except json.JSONDecodeError as exc:
        raise AppError(f"Dify 返回了无法解析的内容（HTTP {response.status_code}）。", 502) from exc

    if not response.ok:
        message = result.get("message") or result.get("error") or json.dumps(result, ensure_ascii=False)
        raise AppError(f"Dify 调用失败（HTTP {response.status_code}）：{message}", 502)

    data = result.get("data") or {}
    if data.get("status") == "failed":
        raise AppError(f"Workflow 执行失败：{data.get('error') or '未知错误'}", 502)

    outputs = data.get("outputs") or {}
    output_text = output_to_text(outputs)
    return jsonify(
        {
            "ok": True,
            "scene": scene.get("name", scene_id),
            "task_id": result.get("task_id"),
            "workflow_run_id": result.get("workflow_run_id"),
            "status": data.get("status", "succeeded"),
            "elapsed_time": data.get("elapsed_time"),
            "outputs": outputs,
            "output_text": output_text,
            "output_html": markdown_to_safe_html(output_text),
        }
    )


def open_local_browser(port: int) -> None:
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    settings = load_config()
    host = str(settings.get("listen_host", "127.0.0.1"))
    port = int(settings.get("listen_port", 8501))

    if settings.get("open_browser", True):
        threading.Timer(1.0, open_local_browser, args=(port,)).start()

    print(f"工艺策划助手已启动：http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print("当前允许内网访问，请使用本机局域网 IP 加端口访问。")
    app.run(host=host, port=port, debug=False, threaded=True)
