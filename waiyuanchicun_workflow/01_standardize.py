import json
import re


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text in {"", "/"} or text.lower() in {"null", "none"} else text


def parse_dimension(value):
    text = clean_text(value)
    if text is None:
        return None
    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    return {
        "nominal": float(numbers[0]),
        "upper": float(numbers[1]) if len(numbers) > 1 else None,
        "lower": float(numbers[2]) if len(numbers) > 2 else None,
    }


def normalize(row):
    return {
        "lingjianbianhao": clean_text(row.get("lingjianbianhao")),
        "waiyuanzhijing1": parse_dimension(row.get("waiyuanzhijing1")),
        "waiyuanzhijing2": parse_dimension(row.get("waiyuanzhijing2")),
        "waiyuanzhijing3": parse_dimension(row.get("waiyuanzhijing3")),
        "huajian_I_duan_zhongxinkong": parse_dimension(row.get("huajian_I_duan_zhongxinkong")),
        "neiwailuowenduan_zhongxinkong": parse_dimension(row.get("neiwailuowenduan_zhongxinkong")),
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


def main(
    waiyuanzhijing1,
    waiyuanzhijing2,
    waiyuanzhijing3,
    huajian_I_duan_zhongxinkong,
    neiwailuowenduan_zhongxinkong,
    sql1,
):
    user = normalize({
        "lingjianbianhao": "USER",
        "waiyuanzhijing1": waiyuanzhijing1,
        "waiyuanzhijing2": waiyuanzhijing2,
        "waiyuanzhijing3": waiyuanzhijing3,
        "huajian_I_duan_zhongxinkong": huajian_I_duan_zhongxinkong,
        "neiwailuowenduan_zhongxinkong": neiwailuowenduan_zhongxinkong,
    })

    valid_fields = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]

    if not valid_fields:
        return {
            "error": "请至少输入一个外圆尺寸特征",
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
