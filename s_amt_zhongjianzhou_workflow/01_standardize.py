import json
import re
import unicodedata


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "/", "-"} or text.lower() in {"null", "none"}:
        return None
    return text


def normalize_text(value):
    text = clean_text(value)
    if text is None:
        return None
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("×", "x")
    return re.sub(r"\s+", "", text)


def number_list(value):
    text = clean_text(value)
    if text is None:
        return []
    return [
        float(item)
        for item in re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    ]


def parse_dimension(value):
    text = clean_text(value)
    if text is None:
        return None
    return {
        "raw": normalize_text(text),
        "numbers": number_list(text),
    }


def find_value(text, pattern):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def parse_gear(value):
    text = clean_text(value)
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    return {
        "raw": normalize_text(normalized),
        "chishu": find_value(normalized, r"(?:^|[\s/;,，；])z\s*[=:：]\s*([-+]?\d+(?:\.\d+)?)"),
        "moshu": find_value(normalized, r"(?:^|[\s/;,，；])m\s*[=:：]\s*([-+]?\d+(?:\.\d+)?)"),
        "yalijiao": find_value(normalized, r"(?:^|[\s/;,，；])[aα]\s*[=:：]\s*([-+]?\d+(?:\.\d+)?)"),
        "luoxuanjiao": find_value(normalized, r"(?:^|[\s/;,，；])[bβ]\s*[=:：]\s*([-+]?\d+(?:\.\d+)?)"),
        "fenduyuanzhijing": find_value(normalized, r"分度圆直径\s*[=:：]?\s*([-+]?\d+(?:\.\d+)?)"),
        "chikuan": find_value(normalized, r"齿宽\s*[=:：]?\s*([-+]?\d+(?:\.\d+)?)"),
    }


def normalize(row):
    return {
        "lingjianbianhao": clean_text(row.get("lingjianbianhao")),
        "zhouduan_zhoutoushifouyouduanmianzuantangkong": normalize_text(row.get("zhouduan_zhoutoushifouyouduanmianzuantangkong")),
        "zhouduan_duanmianxicao": normalize_text(row.get("zhouduan_duanmianxicao")),
        "zhouduan_zhouchengwaiyuanchicun": parse_dimension(row.get("zhouduan_zhouchengwaiyuanchicun")),
        "zhouduan_kahuangjiegouchicun": parse_dimension(row.get("zhouduan_kahuangjiegouchicun")),
        "zhouduan_dawaiyuanchicun": parse_dimension(row.get("zhouduan_dawaiyuanchicun")),
        "chiquanduan_zhouchengwaiyuanchicun": parse_dimension(row.get("chiquanduan_zhouchengwaiyuanchicun")),
        "chiquanduan_chiquanduanmiandaotaijieduanmianzhouxiangzhangdu": parse_dimension(row.get("chiquanduan_chiquanduanmiandaotaijieduanmianzhouxiangzhangdu")),
        "chiquanduan_zhoutoushifouchaneihuajian": normalize_text(row.get("chiquanduan_zhoutoushifouchaneihuajian")),
        "chiquanduan_zhoutoushifouxiquekou": normalize_text(row.get("chiquanduan_zhoutoushifouxiquekou")),
        "chiquanduan_daodangchiquan_chibucanshu": parse_gear(row.get("chiquanduan_daodangchiquan_chibucanshu")),
        "chiquanduan_yidangchiquan_chibucanshu": parse_gear(row.get("chiquanduan_yidangchiquan_chibucanshu")),
        "chiquanduan_liangchiquanjianzhoujing": parse_dimension(row.get("chiquanduan_liangchiquanjianzhoujing")),
        "chiquanduan_kaidangchicun": parse_dimension(row.get("chiquanduan_kaidangchicun")),
        "chiquanduan_kahuangcaoduantaijiezhoujing": parse_dimension(row.get("chiquanduan_kahuangcaoduantaijiezhoujing")),
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
    zd_duanmianzuantangkong,
    zd_duanmianxicao,
    zd_zhouchengwaiyuan,
    zd_kahuangjiegou,
    zd_dawaiyuan,
    cq_zhouchengwaiyuan,
    cq_zhouxiangchangdu,
    cq_chaneihuajian,
    cq_xiquekou,
    cq_daodang_chibu,
    cq_yidang_chibu,
    cq_chiquanjianzhoujing,
    cq_kaidangchicun,
    cq_kahuangtaijiezhoujing,
    sql1,
):
    user = normalize({
        "lingjianbianhao": "USER",
        "zhouduan_zhoutoushifouyouduanmianzuantangkong": zd_duanmianzuantangkong,
        "zhouduan_duanmianxicao": zd_duanmianxicao,
        "zhouduan_zhouchengwaiyuanchicun": zd_zhouchengwaiyuan,
        "zhouduan_kahuangjiegouchicun": zd_kahuangjiegou,
        "zhouduan_dawaiyuanchicun": zd_dawaiyuan,
        "chiquanduan_zhouchengwaiyuanchicun": cq_zhouchengwaiyuan,
        "chiquanduan_chiquanduanmiandaotaijieduanmianzhouxiangzhangdu": cq_zhouxiangchangdu,
        "chiquanduan_zhoutoushifouchaneihuajian": cq_chaneihuajian,
        "chiquanduan_zhoutoushifouxiquekou": cq_xiquekou,
        "chiquanduan_daodangchiquan_chibucanshu": cq_daodang_chibu,
        "chiquanduan_yidangchiquan_chibucanshu": cq_yidang_chibu,
        "chiquanduan_liangchiquanjianzhoujing": cq_chiquanjianzhoujing,
        "chiquanduan_kaidangchicun": cq_kaidangchicun,
        "chiquanduan_kahuangcaoduantaijiezhoujing": cq_kahuangtaijiezhoujing,
    })

    valid_fields = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]
    if not valid_fields:
        return {
            "error": "请至少输入一个中间轴特征",
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
