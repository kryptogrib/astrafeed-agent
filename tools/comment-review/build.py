"""Build an offline annotation page from a read-only snapshot of the local corpus."""
import hashlib
import json
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
con = sqlite3.connect(f'file:{ROOT / "astrafeed.db"}?mode=ro', uri=True)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute('SELECT * FROM comment ORDER BY comment_key')]
posts = {(r['source_id'], r['external_id']): json.loads(r['payload']) for r in con.execute('SELECT * FROM raw_item')}
parents = {(r['source_id'], r['post_id'], r['comment_id']): r for r in rows}
rng = random.Random(20260923)
# Explicit challenge threads from the inspected corpus; random sample is drawn independently.
random_rows = rng.sample(rows, min(60, len(rows)))
used = {r['comment_key'] for r in random_rows}
selected = [(r, 'random') for r in random_rows]
for source, post, group in [(21, '21055', 'eth'), (5, '3263', 'giveaway')]:
    pool = [r for r in rows if r['source_id'] == source and r['post_id'] == post and r['comment_key'] not in used]
    extra = rng.sample(pool, min(20, len(pool)))
    selected.extend((r, group) for r in extra)
    used.update(r['comment_key'] for r in extra)
items = []
for row, group in selected:
    post = posts.get((row['source_id'], row['post_id']), {})
    parent = parents.get((row['source_id'], row['post_id'], row['parent_comment_id']))
    items.append({
        'id': row['comment_key'], 'group': group, 'text': row['text'],
        'timestamp': row['ts'], 'link': row['link'], 'channel': post.get('channel_ref', str(row['source_id'])),
        'post': post.get('text', ''), 'parent': parent['text'] if parent else None,
        'parent_missing': bool(row['parent_comment_id'] and not parent), 'has_media': bool(row['has_media']),
        'prediction': None,
    })
annotations_path = ROOT / 'artifacts/comment-review/predictions.json'
if annotations_path.exists():
    annotations = {x['id']: x for x in json.loads(annotations_path.read_text())['items']}
    for item in items:
        label = annotations.get(item['id'])
        if label:
            checksum = hashlib.sha256(json.dumps([item['text'], item['post'], item['parent']], ensure_ascii=False).encode()).hexdigest()
            if checksum != label['source_sha256']:
                raise ValueError(f"Source changed for {item['id']}; review annotation before rebuilding")
            item['prediction'] = label['prediction']
            item['annotation'] = label['annotation']
encoded = json.dumps(items, ensure_ascii=False)
data = {'id': hashlib.sha256(encoded.encode()).hexdigest()[:16], 'created_at': datetime.now(timezone.utc).isoformat(), 'items': items}
template = Path(__file__).with_name('template.html').read_text()
out = ROOT / 'artifacts/comment-review/comment-review.html'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(template.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')))
print(f'{out}: {len(items)} comments')
