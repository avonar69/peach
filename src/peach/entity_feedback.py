"""实体名下视频的个人评分和偏好汇总，按视频去除重复来源关系。"""
from .web_activity import DEFAULT_PROFILE_ID

EMPTY = dict(average_stars=None, rated_count=0, thumbs_up=0, thumbs_down=0)


def summaries(connection, kind, ids):
    from .web_entity import scope_predicate
    ids = list(dict.fromkeys(ids))
    if kind not in ('performer', 'studio') or not ids:
        return {}
    marks = ','.join('?' for _ in ids)
    scope = scope_predicate(kind, 'ae.entity_id', 'root.id')
    rows = connection.execute(
        "WITH selected AS (SELECT DISTINCT root.id owner,a.id,a.rating,a.feedback,"
        "EXISTS(SELECT 1 FROM asset_preference p WHERE p.asset_id=a.id AND p.profile_id=? AND p.liked=1) liked "
        "FROM entity root CROSS JOIN asset_entity ae ON " + scope +
        " CROSS JOIN asset a ON a.id=ae.asset_id WHERE root.kind=? AND root.id IN (" + marks + ") "
        "AND a.medium='video' AND a.disposal IS NULL) "
        "SELECT owner,AVG(CASE WHEN rating>0 AND rating<=100 THEN rating END)/20.0 average_stars,"
        "COUNT(CASE WHEN rating>0 AND rating<=100 THEN 1 END) rated_count,"
        "SUM(liked) thumbs_up,SUM(CASE WHEN feedback='dislike' THEN 1 ELSE 0 END) thumbs_down "
        "FROM selected GROUP BY owner", [DEFAULT_PROFILE_ID, kind, *ids])
    result = {identity: dict(EMPTY) for identity in ids}
    result.update((row['owner'], {key: row[key] for key in EMPTY}) for row in rows)
    return result


def attach(connection, kind, rows):
    stats = summaries(connection, kind, [row['entity_id'] for row in rows])
    for row in rows:
        if row['entity_id'] in stats:
            row['scene_feedback'] = stats[row['entity_id']]
