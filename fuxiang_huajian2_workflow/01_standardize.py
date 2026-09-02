import json
import re


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text == "" or text.lower() in {"null", "none"} else text


def to_float(value):
    text = clean_text(value)
    if text is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def parse_moshu(value):
    text = clean_text(value)
    if text is None:
        return None
    values = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    return [float(item) for item in values] or None


def normalize(row):
    return {
        "lingjianbianhao": clean_text(row.get("lingjianbianhao")),
        "chishu": to_float(row.get("huajian_II_chishu")),
        "moshu": parse_moshu(row.get("huajian_II_moshu")),
        "yalijiao": to_float(row.get("huajian_II_yalijiao")),
        "luoxuanjiao": to_float(row.get("huajian_II_luoxuanjiao")),
    }


def extract_rows(data):
    if isinstance(data, dict):
        if isinstance(data.get("result"), list):
            return data["result"]
        if isinstance(data.get("json"), list):
            return extract_rows(data["json"])
        return []

    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict) and "result" in item:
                rows.extend(extract_rows(item))
            elif isinstance(item, dict):
                rows.append(item)
        return rows

    return []


def main(chishu, moshu, yalijiao, luoxuanjiao, sql1):
    user = normalize({
        "lingjianbianhao": "USER",
        "huajian_II_chishu": chishu,
        "huajian_II_moshu": moshu,
        "huajian_II_yalijiao": yalijiao,
        "huajian_II_luoxuanjiao": luoxuanjiao,
    })

    valid_fields = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]

    if not valid_fields:
        return {
            "error": "请至少输入一个零件特征",
            "user": "{}",
            "parts": "[]",
            "count": "0",
            "valid_fields": "[]",
        }

    parts = []
    seen = set()
    for row in extract_rows(sql1):
        part = normalize(row)
        part_id = part["lingjianbianhao"]
        if part_id and part_id not in seen:
            seen.add(part_id)
            parts.append(part)

    return {
        "error": "",
        "user": json.dumps(user, ensure_ascii=False),
        "parts": json.dumps(parts, ensure_ascii=False),
        "count": str(len(parts)),
        "valid_fields": json.dumps(valid_fields, ensure_ascii=False),
    }
