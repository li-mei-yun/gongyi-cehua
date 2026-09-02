import json
import math


def exp_sim(left, right, scale):
    return math.exp(-abs(left - right) / scale)


def dimension_sim(left, right, nominal_scale):
    weights = {"nominal": 0.7, "upper": 0.15, "lower": 0.15}
    scales = {"nominal": nominal_scale, "upper": 0.05, "lower": 0.05}
    score = 0.0
    used_weight = 0.0

    for field, weight in weights.items():
        a, b = left.get(field), right.get(field)
        if a is not None and b is not None:
            score += exp_sim(a, b, scales[field]) * weight
            used_weight += weight

    return score / used_weight if used_weight else None


def main(user, parts):
    user = json.loads(user or "{}")
    parts = json.loads(parts or "[]")
    used_features = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]

    settings = {
        "waiyuanzhijing1": (25, 2.0),
        "waiyuanzhijing2": (20, 2.0),
        "waiyuanzhijing3": (15, 2.0),
        "huajian_I_duan_zhongxinkong": (20, 1.0),
        "neiwailuowenduan_zhongxinkong": (20, 1.0),
    }
    results = []

    for part in parts:
        weighted_score = 0.0
        used_weight = 0

        for field, (weight, scale) in settings.items():
            left, right = user.get(field), part.get(field)
            if left is None or right is None:
                continue
            score = dimension_sim(left, right, scale)
            if score is not None:
                weighted_score += score * weight
                used_weight += weight

        if used_weight:
            results.append({
                "lingjianbianhao": part["lingjianbianhao"],
                "score": round(weighted_score / used_weight * 100, 2),
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
