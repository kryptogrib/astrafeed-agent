WITH miss AS (
  SELECT c.source_id, c.post_id, count(*) n FROM comment c
  WHERE c.parent_comment_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM comment p WHERE p.source_id=c.source_id AND p.post_id=c.post_id AND p.comment_id=c.parent_comment_id)
  GROUP BY 1,2),
nt AS (SELECT DISTINCT source_id, post_id FROM comment WHERE trim(text)='' AND has_media)
SELECT 'fetched', count(*) FROM thread_state WHERE status='fetched'
UNION ALL SELECT 'flagged', sum(context_incomplete) FROM thread_state WHERE status='fetched'
UNION ALL SELECT 'flagged_and_nontext', count(*) FROM thread_state t JOIN nt USING(source_id, post_id) WHERE t.context_incomplete
UNION ALL SELECT 'flagged_without_nontext', count(*) FROM thread_state t WHERE t.context_incomplete AND NOT EXISTS (SELECT 1 FROM nt WHERE nt.source_id=t.source_id AND nt.post_id=t.post_id)
UNION ALL SELECT 'replies_with_parent', count(*) FROM comment WHERE parent_comment_id IS NOT NULL
UNION ALL SELECT 'replies_parent_not_stored', sum(n) FROM miss
UNION ALL SELECT 'threads_parent_not_stored', count(*) FROM miss
UNION ALL SELECT 'of_them_unflagged', count(*) FROM miss JOIN thread_state t USING(source_id, post_id) WHERE NOT t.context_incomplete;
