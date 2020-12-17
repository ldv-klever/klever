DECISION_SAFE_TAGS_STATISTIC_SQL = """
SELECT MT.tag_id AS tag_id, COUNT(DISTINCT R0.id) AS repnum
    FROM cache_mark_safe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_safe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_safe AS M0
            INNER JOIN mark_safe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    WHERE R0.decision_id = %s GROUP BY tag_id;"""

DECISION_UNSAFE_TAGS_STATISTIC_SQL = """
SELECT MT.tag_id AS tag_id, COUNT(DISTINCT R0.id) AS repnum
    FROM cache_mark_unsafe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_unsafe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_unsafe AS M0
            INNER JOIN mark_unsafe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    WHERE R0.decision_id = %s GROUP BY tag_id;"""

REPORT_SAFE_TAGS_STATISTIC_SQL = """
SELECT MT.tag_id AS tag_id, COUNT(DISTINCT R0.id) AS repnum
    FROM cache_mark_safe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_safe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_safe AS M0
            INNER JOIN mark_safe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    WHERE RL.report_id = %s GROUP BY tag_id;"""

REPORT_UNSAFE_TAGS_STATISTIC_SQL = """
SELECT MT.tag_id AS tag_id, COUNT(DISTINCT R0.id) AS repnum
    FROM cache_mark_unsafe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_unsafe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_unsafe AS M0
            INNER JOIN mark_unsafe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    WHERE RL.report_id = %s GROUP BY tag_id;"""


SAFE_REPORTS_WITH_TAG_ID = """
SELECT DISTINCT R0.id AS report_id
    FROM cache_mark_safe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_safe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_safe AS M0
            INNER JOIN mark_safe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    WHERE RL.report_id = %s AND MT.tag_id = %s;
"""

UNSAFE_REPORTS_WITH_TAG_ID = """
SELECT DISTINCT R0.id AS report_id
    FROM cache_mark_unsafe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_unsafe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_unsafe AS M0
            INNER JOIN mark_unsafe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    WHERE RL.report_id = %s AND MT.tag_id = %s;
"""


SAFE_REPORT_TAGS = """
SELECT R0.id AS report_id, ARRAY_AGG(T0.name ORDER BY T0.level) AS tags
    FROM cache_mark_safe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_safe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_safe AS M0
            INNER JOIN mark_safe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    INNER JOIN mark_tag AS T0 ON T0.id = MT.tag_id
    WHERE RL.report_id = %s GROUP BY R0.id;
"""

UNSAFE_REPORT_TAGS = """
SELECT R0.id AS report_id, ARRAY_AGG(T0.name ORDER BY T0.level) AS tags
    FROM cache_mark_unsafe_report AS MR
    INNER JOIN report AS R0 ON R0.id = MR.report_id
    INNER JOIN (
        SELECT DISTINCT MM.mark_id AS mark_id, MT.tag_id AS tag_id FROM cache_mark_unsafe_tag AS MT
        INNER JOIN (
            SELECT M0.id AS mark_id, MH.id as mark_version_id FROM mark_unsafe AS M0
            INNER JOIN mark_unsafe_history AS MH ON MH.mark_id = M0.id AND MH.version = M0.version
        ) AS MM ON MM.mark_version_id = MT.mark_version_id
    ) AS MT ON MT.mark_id = MR.mark_id
    INNER JOIN cache_report_component_leaf AS RL ON R0.id = RL.object_id AND RL.content_type_id = %s
    INNER JOIN mark_tag AS T0 ON T0.id = MT.tag_id
    WHERE RL.report_id = %s GROUP BY R0.id;
"""
