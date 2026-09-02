import json
import math


def exp_sim(left, right, scale):
    return math.exp(-abs(left - right) / scale)


def number_scale(value):
    value = abs(value)
    if value < 1:
        return 0.05
    if value < 10:
        return 0.5
    return max(1.0, value * 0.02)


def dimension_sim(left, right):
    left_numbers = left.get("numbers") or []
    right_numbers = right.get("numbers") or []
    if left_numbers and right_numbers:
        scores = []
        for value in left_numbers:
            scores.append(max(
                exp_sim(value, candidate, number_scale(value))
                for candidate in right_numbers
            ))
        return sum(scores) / len(scores)
    return 1.0 if left.get("raw") == right.get("raw") else 0.0


def gear_sim(left, right):
    settings = {
        "chishu": (25, 3.0),
        "moshu": (25, 0.3),
        "yalijiao": (15, 1.5),
        "luoxuanjiao": (15, 2.0),
        "fenduyuanzhijing": (5, 3.0),
        "chikuan": (15, 5.0),
    }
    score = 0.0
    used_weight = 0
    for field, (weight, scale) in settings.items():
        a, b = left.get(field), right.get(field)
        if a is not None and b is not None:
            score += exp_sim(a, b, scale) * weight
            used_weight += weight
    if used_weight:
        return score / used_weight
    return 1.0 if left.get("raw") == right.get("raw") else 0.0


def text_sim(left, right):
    return 1.0 if left == right else 0.0


def main(user, parts):
    user = json.loads(user or "{}")
    parts = json.loads(parts or "[]")
    used_features = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]

    settings = {
        "zhouduan_zhoutoushifouyouduanmianzuantangkong": (4, text_sim),
        "zhouduan_duanmianxicao": (4, text_sim),
        "zhouduan_zhouchengwaiyuanchicun": (5, dimension_sim),
        "zhouduan_kahuangjiegouchicun": (5, dimension_sim),
        "zhouduan_dawaiyuanchicun": (5, dimension_sim),
        "chiquanduan_zhouchengwaiyuanchicun": (5, dimension_sim),
        "chiquanduan_chiquanduanmiandaotaijieduanmianzhouxiangzhangdu": (5, dimension_sim),
        "chiquanduan_zhoutoushifouchaneihuajian": (4, text_sim),
        "chiquanduan_zhoutoushifouxiquekou": (4, text_sim),
        "chiquanduan_daodangchiquan_chibucanshu": (20, gear_sim),
        "chiquanduan_yidangchiquan_chibucanshu": (20, gear_sim),
        "chiquanduan_liangchiquanjianzhoujing": (5, dimension_sim),
        "chiquanduan_kaidangchicun": (5, dimension_sim),
        "chiquanduan_kahuangcaoduantaijiezhoujing": (5, dimension_sim),
    }

    active_weight = sum(
        settings[field][0]
        for field in used_features
        if field in settings
    )
    results = []

    for part in parts:
        weighted_score = 0.0
        comparable_count = 0
        for field in used_features:
            if field not in settings:
                continue
            weight, comparator = settings[field]
            candidate = part.get(field)
            if candidate is None:
                continue
            weighted_score += comparator(user[field], candidate) * weight
            comparable_count += 1

        if comparable_count and active_weight:
            results.append({
                "lingjianbianhao": part["lingjianbianhao"],
                "score": round(weighted_score / active_weight * 100, 2),
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    top5 = results[:5]
    return {
        "used_features": ",".join(used_features),
        "candidate_count": str(len(results)),
        "id1": top5[0]["lingjianbianhao"] if len(top5) > 0 else "",
        "id2": top5[1]["lingjianbianhao"] if len(top5) > 1 else "",
        "id3": top5[2]["lingjianbianhao"] if len(top5) > 2 else "",
        "id4": top5[3]["lingjianbianhao"] if len(top5) > 3 else "",
        "id5": top5[4]["lingjianbianhao"] if len(top5) > 4 else "",
        "top5_scores": json.dumps(top5, ensure_ascii=False),
    }
