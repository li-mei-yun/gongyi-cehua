import json


def display(value):
    if value is None or str(value).strip().lower() in {"", "null", "none"}:
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

    text = "副箱花键II Top5推荐\n\n"
    for index, item in enumerate(scores, 1):
        text += f"{index}. {item['lingjianbianhao']}（相似度：{item['score']}%）\n"

    fields = [
        ("lingjianbianhao", "零件编号"),
        ("huajian_II_chishu", "花键II齿数"),
        ("huajian_II_moshu", "花键II模数"),
        ("huajian_II_yalijiao", "花键II压力角"),
        ("huajian_II_luoxuanjiao", "花键II螺旋角"),
        ("huajian_II_gongyi", "花键II工艺"),
        ("huajian_II_rehouhuajianhuangui", "花键II热后花键环规"),
        ("huajian_II_gunhuajian_gundao", "花键II滚花键滚刀"),
        ("huajian_II_gunhuajian_gunchi_M_zhi_dp", "花键II滚花键滚齿M值/dp"),
        ("huajian_II_gunhuajian_gunchijiaju", "花键II滚花键滚齿夹具"),
    ]

    for index, item in enumerate(scores, 1):
        part = by_id.get(str(item["lingjianbianhao"]), {})
        text += f"\n{'=' * 36}\n【推荐零件{index}】\n"
        for field, label in fields:
            text += f"{label}：{display(part.get(field))}\n"

    return {"report": text}
