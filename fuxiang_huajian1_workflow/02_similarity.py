import json
import math


def exp_sim(a, b, scale):
    return math.exp(-abs(a - b) / scale)


def moshu_sim(left, right):
    if len(left) == len(right):
        return sum(exp_sim(a, b, 0.5) for a, b in zip(left, right)) / len(left)
    return max(exp_sim(a, b, 0.5) for a in left for b in right)


def main(user, parts):
    user = json.loads(user or "{}")
    parts = json.loads(parts or "[]")

    used_features = [
        key for key, value in user.items()
        if key != "lingjianbianhao" and value is not None
    ]

    numeric = {
        "chishu": (25, 5),
        "yalijiao": (15, 2),
        "luoxuanjiao": (15, 5),
    }
    results = []

    for part in parts:
        weighted_score = 0.0
        used_weight = 0

        for field, (weight, scale) in numeric.items():
            left, right = user.get(field), part.get(field)
            if left is not None and right is not None:
                weighted_score += exp_sim(left, right, scale) * weight
                used_weight += weight

        left_moshu, right_moshu = user.get("moshu"), part.get("moshu")
        if left_moshu is not None and right_moshu is not None:
            weighted_score += moshu_sim(left_moshu, right_moshu) * 25
            used_weight += 25

        if user.get("biaozhun") is not None and part.get("biaozhun") is not None:
            weighted_score += (
                1.0 if user["biaozhun"] == part["biaozhun"]
                else 0.0
            ) * 20
            used_weight += 20

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
