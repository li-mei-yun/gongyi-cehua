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


def main(top5_report, sql2):
    scores = json.loads(top5_report or "[]")
    rows = extract_rows(sql2)
    by_id = {str(row.get("lingjianbianhao")): row for row in rows}

    text = "副箱轴承孔 Top5推荐\n\n"
    for index, item in enumerate(scores, 1):
        text += f"{index}. {item['lingjianbianhao']}（相似度：{item['score']}%）\n"

    fields = [
        ("lingjianbianhao", "零件编号"),
        ("zhouchengkong_kongjing", "轴承孔孔径"),
        ("zhouchengkong_kongshen", "轴承孔孔深"),
        ("zhouchengkong_reqiantangkong_kongshen", "热前镗孔孔深"),
        ("zhouchengkong_reqiantangkong_saigui", "热前镗孔塞规"),
        ("zhouchengkong_reqiantangkong_tangkongjiaju", "热前镗孔夹具"),
        ("zhouchengkong_rehoutangkong_kongjing", "热后镗孔孔径"),
        ("zhouchengkong_rehoutangkong_kongshen", "热后镗孔孔深"),
        ("zhouchengkong_rehoutangkong_qidongliangyi", "热后镗孔气动量仪"),
        ("zhouchengkong_rehoutangkong_tangkongjiaju", "热后镗孔夹具"),
    ]

    for index, item in enumerate(scores, 1):
        part = by_id.get(str(item["lingjianbianhao"]), {})
        text += f"\n{'=' * 36}\n【推荐零件{index}】\n"
        for field, label in fields:
            text += f"{label}：{display(part.get(field))}\n"

    return {"report": text}
