import json


def display(value):
    if value is None or str(value).strip().lower() in {"", "/", "null", "none"}:
        return "未填写"
    return str(value).strip()


def extract_rows(data):
    if isinstance(data, dict):
        return data.get("result", []) if isinstance(data.get("result"), list) else []
    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("result"), list):
                rows.extend(item["result"])
            elif isinstance(item, dict):
                rows.append(item)
        return rows
    return []


def main(top5_scores, sql2):
    scores = json.loads(top5_scores or "[]")
    rows = extract_rows(sql2)
    by_id = {str(row.get("lingjianbianhao")): row for row in rows}

    text = "S及AMT中间轴 Top5推荐\n\n"
    for index, item in enumerate(scores, 1):
        text += f"{index}. {item['lingjianbianhao']}（相似度：{item['score']}%）\n"

    groups = [
        ("基本信息", [
            ("lingjianbianhao", "零件编号"),
            ("chanpinmingcheng", "产品名称"),
        ]),
        ("倒挡齿圈", [
            ("chiquanduan_daodangchiquan_guanjiangongxujiagongfangshi", "关键工序加工方式"),
            ("chiquanduan_daodangchiquan_mochishebeixinghao", "设备型号"),
            ("chiquanduan_daodangchiquan_mochijiaju", "磨齿夹具"),
        ]),
        ("一挡齿圈", [
            ("chiquanduan_yidangchiquan_guanjiangongxujiagongfangshi", "关键工序加工方式"),
            ("chiquanduan_yidangchiquan_mochishebeixinghao", "设备型号"),
            ("chiquanduan_yidangchiquan_mochijiaju", "磨齿夹具"),
        ]),
    ]

    for index, item in enumerate(scores, 1):
        part = by_id.get(str(item["lingjianbianhao"]), {})
        text += f"\n{'=' * 40}\n【推荐零件{index}】\n"
        for title, fields in groups:
            text += f"\n{title}\n"
            for field, label in fields:
                text += f"{label}：{display(part.get(field))}\n"

    return {"report": text}
