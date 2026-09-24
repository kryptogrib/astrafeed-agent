#!/usr/bin/env python3
"""Воспроизведение предварительной агентской разметки D2; только stdlib и SQLite mode=ro."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# Это фиксированные ручные решения по прочитанным текстам, не правила классификации.
LABELS = {}

def label(ids, topic, event, reason, spans, origin='retelling', role='editorial', relevant=True, secondary=()):
    for ident in ids:
        LABELS[ident] = dict(topics=[topic], relevant_news=relevant, origin=origin,
                            source_role=role, event_id=event,
                            event_ids=([event] if event else []) + list(secondary),
                            reason=reason, spans=spans)

# Дневные потоки: дата — предмет отчёта, а не дата публикации.
for ids, date, amount in [([4217,13894],'2026-09-16','отток 224,1 млн (224 млн после округления)'),
                         ([4239,13902],'2026-09-17','отток 39,3 млн (39 млн после округления)'),
                         ([4263,13906,13911],'2026-09-18','приток 143,7 млн (144 млн после округления)'),
                         ([4306,13935,12911],'2026-09-21','приток 269,98 млн (270 млн после округления)'),
                         ([4334,13942],'2026-09-22','приток 162,2 млн (162 млн после округления)')]:
    label(ids,'eth','tune-eth-etf-'+date,'Отчёт о потоке ETH-ETF за '+date+': '+amount+'. Разные даты потоков — разные события.',[])
LABELS[13911]['reason'] += ' В воскресном посте повторены последние торговые потоки и три предыдущих значения из субботней таблицы; это предварительная интерпретация повторения пятничных данных, дата в строке не указана.'
label([4191],'eth','tune-eth-etf-2026-09-15','Дневной отток ETH-ETF 142,3 млн; отдельный торговый день.', [('event','Общий чистый отток'),('redistribution','Общий чистый отток')])
label([4281],'eth','tune-eth-etf-week-ambiguous','Недельный отток 140 млн. В сентябрьском посте написано «14 по 18 августа»: сохраняем противоречие, не исправляем месяц и не объединяем с дневными данными.', [('event','Общий чистый отток'),('redistribution','📊 #BTC #ETH #ETF На прошлой неделе')])
label([13825],'eth','tune-eth-etf-2026-09-09','В таблице сообщён отдельный приток ETH-ETF 35 млн; котировки сами по себе не новость.',[])
label([13837],'eth','tune-eth-etf-2026-09-10','В таблице сообщён отдельный отток ETH-ETF 30 млн.',[])
label([13846],'eth','tune-eth-etf-2026-09-11','В таблице сообщён отдельный приток ETH-ETF 216 млн.',[])
label([4271,7811],'eth','tune-moex-perps-2026-09-22','Анонс запуска фьючерсов Мосбиржи 22 сентября, включая ETH; одна строка многотемного календаря. Тексты двух публикаций совпадают, первоисточник не установлен.', [('event','🇷🇺 Мосбиржа'),('redistribution','🇷🇺 Мосбиржа')],origin='repost')
label([14,7943],'zec','tune-zkghost-wl','Открытый WL одной коллекции zkGhosts, 10 000 NFT; разные формулировки в двух дайджестах. Это NFT-активность, не обновление Zcash.',[])
label([15,16],'zec','tune-cyphersquad-mint','Один запланированный минт CypherSquad 22 сентября в 20:00 МСК; публикации в одном канале, это повторный анонс, не независимое подтверждение.',[])
label([4240,12853],'zec','tune-zec-four-wallets-2026-09-18','Четыре новых кошелька выводят ZEC: 15860+7081+5818+3534=32293. Сводный пересказ совпадает по сумме, числу кошельков, действию и дате.',[])
label([7021],'zec','tune-zec-1400-2026-09-17','Краткий ценовой алерт ZEC на уровне 1400 долларов.', [('event','#zec = 1400$ say GM 🏆')],origin='own',role='author')
label([7336],'zec','tune-zec-nu7-vote-deadline','Одна строка дайджеста: предстоящее завершение голосования NU7. Это анонс дедлайна, не результат голосования и не активация обновления.', [('event','🙋‍♂️ #ZEC'),('redistribution','🙋‍♂️ #ZEC')])
label([7734],'zec','tune-zec-top10','Сообщается вход ZEC в топ-10; автор объясняет рост сквизом и тонким рынком. Дата NU7 — вторичный явно размеченный эпизод; активация ещё не произошла.', [('event','ZEC разогнался'),('event','Плюс ко всему'),('redistribution','Плюс ко всему'),('author_position','Работает механика'),('promo_service','❝[Консенсус')],role='author',secondary=['tune-zec-nu7-plan'])
label([7442],'zec','tune-zec-punks-mint','Анонс сегодняшнего минта панков на ZEC по 0.015 ZEC; событие коллекции в экосистеме, не запуск NFT в основной сети.', [('event','Сегодня еще'),('event','Паблик в'),('event','MP 0.015'),('promo_service','Минт будет')],origin='own',role='author')
label([4238],'zec','tune-zec-short-12285','Убыток шорта 12285 ZEC на 7,66 млн; не следует отождествлять с любым другим шортистом ZEC.', [('event','Но шорт'),('event','Его шорт'),('redistribution','Его шорт')])
label([4268],'zec','tune-zec-dormant-whale','Перемещение ZEC на 362 млн после десяти месяцев бездействия и частичный перевод на Coinbase; не вывод четырёх новых кошельков с бирж.', [('event','– крупный инвестор'),('redistribution','– крупный инвестор')])
label([4282],'zec','tune-zec-jin-close','Закрытие шорта Гаррета Джина с убытком 35,44 млн; спотовый остаток отдельно от закрытой позиции.', [('event','3. Гаррет'),('redistribution','3. Гаррет')])
label([13841],'eth',None,'Авторский технический тезис о пробое и условном альтсезоне при удержании 2500; не самостоятельное сообщение о новом событии.', [('author_position','Зефир Витальевич')],origin='own',role='author',relevant=False)
label([4184],'zec','tune-near-trader-profit','Прибыль трейдеров NEAR; ZEC упомянут как направление свапа и объяснение нарратива. Новость о NEAR не становится новостью Zcash.', [('event','$32.3M'),('author_position','Вопросов к пампу')],origin='own',role='author',relevant=False)
for ident, reason in [(6993,'ETH только в таблице котировок; основной текст о смене позиции по BTC.'),(6994,'ETH только в котировочном подвале; приглашение в игру 67 не новость Ethereum.'),(6997,'ETH только в котировочном подвале; основной предмет — рынок и CLARITY Act.')]:
    label([ident],'eth',None,reason,[('promo_service','🔹ETH')],origin='own',role='author',relevant=False)
label([7009],'zec',None,'ZEC служит предостерегающим примером в промоподборке других коллекций. Нет конкретного нового события Zcash; авторскую оценку не превращаем в подтверждённый сбой сети.', [('author_position','По примеру ZEC'),('promo_service','OranguNation:'),('promo_service','Еще больше NFT')],origin='own',relevant=False)
label([7330],'zec',None,'Короткий анонс материала/каналов об экосистемах без конкретного события или раскрытого тезиса.', [('promo_service','За экосистему'),('promo_service','FACKBLOCK')],origin='unknown',role='unknown',relevant=False)
label([12721],'zec',None,'Приглашение читать аналитическую статью; исторический рост — контекст, нового датированного события не заявлено.', [('promo_service','Постарались создать'),('promo_service','+ подключили')],origin='own',relevant=False)
label([12867],'zec','tune-zama-growth','Ценовой алерт относится к ZAMA; ZEC находится в заголовке ссылки на другой материал.', [('event','😳 #ZAMA'),('promo_service','Grok 4.6'),('promo_service','Токен доступен')],relevant=False)
label([7054],'eth','tune-metamask-ipo','Сообщается разделение Consensys и подготовка MetaMask к IPO; это инфраструктура Ethereum. Оценка перспектив MASK — собственная позиция автора, планы IPO не факт размещения.', [('event','Consensys разделяет'),('event','Консьюмерский финтех'),('redistribution','Консьюмерский финтех'),('author_position','🗒 Токена')],role='author')
label([6995],'eth','tune-keeper-multichain','Переименование кошелька и добавление нескольких сетей, включая Ethereum; поддержка сети в кошельке — конкретная функциональность, не одно лишь упоминание.', [('event','🟪Кошелёк Tonkeeper'),('author_position','Что дальше?'),('promo_service','🔹ETH')],role='author')

# Префиксы строк задают точные фрагменты; остальные строки дайджеста не размечаются автоматически.
LABELS[14]['spans']=[('event','👍Продолжаем'),('redistribution','👍Продолжаем'),('promo_service','👍Продолжаем'),('promo_service','👍 Полезные')]
LABELS[7943]['spans']=[('event','🛡️Zkghost'),('redistribution','🛡️Zkghost'),('promo_service','🟢Zkghost')]
LABELS[15]['spans']=[('event','• CypherSquad:'),('redistribution','• CypherSquad:'),('promo_service','Еще больше NFT')]
LABELS[16]['spans']=[('event','🔘Сегодня в 20:00'),('redistribution','🔘Сегодня в 20:00'),('promo_service','👍 Полезные')]
LABELS[4240]['spans']=[('event','1. t1UcyM'),('event','2. За последние'),('event','3. t1YLeD'),('event','4. t1gxP4'),('redistribution','🔍 Новые кошельки')]
LABELS[12853]['spans']=[('event','➤ Киты активно'),('redistribution','➤ Киты активно')]
for ident, value in LABELS.items():
    if not value['spans']:
        prefix = '▫️#ETH' if ident == 12911 else ('Общий чистый' if ident < 10000 else ('📈 🔴 ETH ETF:' if ident in [13894,13902,13837] else '📈 🟢 ETH ETF:'))
        value['spans']=[('event',prefix),('redistribution',prefix)]
        if ident >= 13800: value['spans'].append(('promo_service','⟠ ETH:'))

# post_id в этом списке — raw_item.id; ключ комментария проверяется по базе.
COMMENTS = [
(15,'572180','other_subject','NFT-подборка ZEC','Оценка «там один скам» относится к подборке коллекций; не доказанный факт о сети.'),
(15,'572168','other_subject','NFT-подборка ZEC','Негативная оценка подборки без указания отдельной новости.'),
(15,'572170','other_subject','NFT-подборка ZEC','Возражает родительской оценке «Мусор».'),
(15,'572131','topic_level_uncertain','ZADDR / инфраструктура ZEC','Во время разговора о минте пишет «зек лагает»; кошелёк, площадка и сеть не различены, сбой базовой сети не установлен.'),
(15,'572127','other_subject','ZADDR','Спрашивает об отдельном минте ZADDR, не о выбранном событии CypherSquad.'),
(15,'572129','other_subject','ZecVisions','Ссылка и предложение GTD касаются другой коллекции.'),
(15,'572133','other_subject','ZecVisions','Просит розыгрыш в ответ на предложение GTD ZecVisions.'),
(15,'572119','project','Zcash: кошельки','Прямой вопрос о кошельке для ZEC, не реакция на конкретный минт.'),
(15,'572120','project','Zcash: кошельки','Ответ Noir на прямой вопрос о кошельке ZEC.'),
(15,'572112','project','Zcash: цена','Говорит о самом ZEC после роста; не новость о NFT.'),
(15,'572109','other_subject','NFT-подборка ZEC','Хвалит сводную подборку, не отдельное событие.'),
(7021,'188801','event','tune-zec-1400-2026-09-17','Сожаление о неоткрытом лонге по 450 под конкретным ценовым алертом 1400; реакция FOMO.'),
(13841,'342557','author_thesis','Пробой ETH / альтсезон','Явно оспаривает тезис поста о пробое, предлагает интерпретацию забора ликвидности.'),
(13841,'342558','author_thesis','Пробой ETH / альтсезон','Ответ на разбор формации; дейктическое «здесь» поддерживается текстом родителя, график не додумывается.'),
(13841,'342526','author_thesis','Удержание ETH 2500','Уточняет таймфрейм условия из поста.'),
(13841,'342498','author_thesis','Пробой ETH / альтсезон','Альтернативный сценарий движения на 4ч относительно тезиса о пробое.'),
(13841,'342507','project','Ethereum: цена','Ироническое ожидание ETH по 5000; не связь с конкретным событием.'),
(13841,'342510','other_subject','Теннис','Объявляет теннисный полуфинал, меняет предмет ветки.'),
(13841,'342521','other_subject','Теннис / внешность','Текст и родитель продолжают постороннюю беседу о теннисе.'),
(13841,'342491','other_subject','Bitcoin: цена','Прямой вопрос о BTC 300к, не прогноз по ETH.'),
(13841,'342466','author_thesis','Объём пробоя ETH','Вопрос об объёмах повторяет существенный признак тезиса поста.'),
(13841,'342462','project','Ethereum: шорты','Собственное наблюдение о шортах ETH, не доказательство события или подтверждение пробоя.'),
(13841,'342464','topic_level_uncertain','Закрытый шорт: актив не указан','Не называет актив закрытого шорта; одной принадлежности ветке недостаточно.'),
(13841,'342461','other_subject','Bitcoin','Сравнение с BTC, а не сообщение о событии Ethereum.'),
]
POS = [
(4217,13894,'Дневной отток 224,1/224 млн за 16 сентября; одинаковая дата отчёта, округление суммы.'),
(4239,13902,'Дневной отток 39,3/39 млн за 17 сентября.'),
(4263,13906,'Дневной приток 143,7/144 млн за 18 сентября.'),
(4306,13935,'Дневной приток 270 млн за 21 сентября.'),
(4334,13942,'Дневной приток 162,2/162 млн за 22 сентября.'),
(4306,12911,'Один дневной приток: 270 млн и точная сумма 269 980 000.'),
(12911,13935,'Тот же дневной приток, полный список фондов и краткая таблица.'),
(4263,13911,'Предварительно: воскресная таблица повторяет пятничные 144 млн и всю последовательность потоков; дата сделки не указана, требуется человеческая проверка.'),
(14,7943,'Один WL zkGhosts на 10 000 NFT в разных каналах и разных формулировках.'),
(15,16,'Один минт CypherSquad 22 сентября 20:00; повторный анонс в одном канале.'),
(4240,12853,'Один вывод четырёх кошельков: сумма четырёх операций точно равна сводным 32 293 ZEC.'),
(4271,7811,'Точная перепечатка календаря; сравнивается анонс фьючерсов Мосбиржи с ETH.'),
]
NEG = [
(4191,4217,'Одна сущность ETH-ETF и отток, но разные торговые дни: 15 и 16 сентября.'),
(4217,4239,'ETH-ETF: два последовательных дня оттока, 224,1 и 39,3 млн.'),
(4263,4306,'ETH-ETF: притоки 18 и 21 сентября, не одно событие.'),
(4306,4334,'ETH-ETF: притоки за 21 и 22 сентября, разные суммы и дни.'),
(13825,13846,'ETH-ETF: притоки за 9 и 11 сентября, 35 и 216 млн.'),
(13837,13894,'ETH-ETF: оттоки за 10 и 16 сентября, 30 и 224 млн.'),
(4281,4191,'Недельная агрегация ETH-ETF с противоречивым месяцем и дневной отток — разные предметы отчёта.'),
(4240,4268,'Один ZEC, но новые кошельки выводят с бирж, а проснувшийся кит переводит часть на Coinbase; различаются действие, суммы и участники.'),
(4238,4282,'Один ZEC и убыточный шорт, но 12285 ZEC с открытым убытком 7,66 млн против закрытого шорта Джина на 35,44 млн.'),
(7336,7734,'NU7: анонс завершения голосования и последующий обзор роста с планом апгрейда — разные этапы, не один эпизод.'),
(7442,15,'NFT на ZEC: минт панков 15 сентября и минт CypherSquad 22 сентября.'),
(4271,4306,'ETH: запуск биржевых фьючерсов и приток в ETF — разные инструменты и действия.'),
]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def readable(text):
    if '\\u' in text:
        try: return json.loads('"' + text + '"')
        except json.JSONDecodeError: pass
    return text

def iso(value):
    return datetime.fromisoformat(value).isoformat() + ('+00:00' if datetime.fromisoformat(value).tzinfo is None else '')

def generate(db):
    posts=[]
    for ident, label_data in sorted(LABELS.items()):
        row=db.execute('SELECT * FROM raw_item WHERE id=?',(ident,)).fetchone()
        payload=json.loads(row['payload']); raw=payload['text']; text=readable(raw)
        expected={k:v for k,v in label_data.items() if k!='spans'}
        segments=[]
        for cls, prefix in label_data['spans']:
            lines=[line for line in text.splitlines() if line.startswith(prefix)]
            assert len(lines)==1, (ident,prefix,lines)
            quote=lines[0]; start=text.index(quote)
            segments.append(dict(**{'class':cls},start=start,end=start+len(quote),text=quote))
        expected['segments']=segments
        posts.append(dict(id=f'p{ident}', raw_item_id=ident,source_id=row['source_id'],channel=payload['channel_ref'],external_id=row['external_id'],link=payload['link'],timestamp=iso(row['timestamp']),text=text,text_raw=raw,stored_comments=db.execute('SELECT count(*) FROM comment WHERE source_id=? AND post_id=?',(row['source_id'],row['external_id'])).fetchone()[0],expected=expected,window_membership={}))
    byid={p['raw_item_id']:p for p in posts}; comments=[]
    for ident,cid,target,subject,reason in COMMENTS:
        p=byid[ident]
        c=db.execute('SELECT * FROM comment WHERE source_id=? AND post_id=? AND comment_id=?',(p['source_id'],p['external_id'],cid)).fetchone()
        assert c is not None,(ident,cid)
        parent=db.execute('SELECT comment_key,ts,text FROM comment WHERE source_id=? AND post_id=? AND comment_id=?',(c['source_id'],c['post_id'],c['parent_comment_id'])).fetchone() if c['parent_comment_id'] else None
        comments.append(dict(id=c['comment_key'],source_id=c['source_id'],channel=p['channel'],post_id=c['post_id'],post_ref=p['id'],external_id=c['comment_id'],parent_comment_id=c['parent_comment_id'],timestamp=iso(c['ts']),link=c['link'],text=c['text'],parent_context=dict(parent) if parent else None,expected={'class':'participant_reaction','link_target':target,'subject':subject,'reason':reason}))
    pairs=[]
    for same,entries in [(True,POS),(False,NEG)]:
        for a,b,reason in entries:
            ea,eb=byid[a]['expected'],byid[b]['expected']
            assert bool(set(ea['event_ids']) & set(eb['event_ids'])) == same
            pairs.append(dict(id=f'tune-pair-{len(pairs)+1:02}',a=f'p{a}',b=f'p{b}',same_event=same,event_id=ea['event_id'] if same else None,shared_topics=sorted(set(ea['topics'])&set(eb['topics'])),reason=reason))
    return {'posts.jsonl':posts,'comments.jsonl':comments,'pairs.jsonl':pairs}


def validate(data, eval_dir):
    posts,comments,pairs=(data[n+'.jsonl'] for n in ['posts','comments','pairs'])
    ep,ec,er=(read_jsonl(eval_dir/(n+'.jsonl')) for n in ['posts','comments','pairs'])
    post_keys={(p['source_id'],p['external_id']) for p in ep}
    comment_keys={c['id'] for c in ec}
    # Исключаются также родительские комментарии, встроенные контекстом в news-eval.
    comment_keys|={c['parent_context']['comment_key'] for c in ec if c['parent_context']}
    own_comments={c['id'] for c in comments}|{c['parent_context']['comment_key'] for c in comments if c['parent_context']}
    overlaps={
        'posts_by_id':len({p['id'] for p in posts}&{p['id'] for p in ep}),
        'posts_by_source_external_id':len({(p['source_id'],p['external_id']) for p in posts}&post_keys),
        'posts_by_exact_text':len({p['text'] for p in posts}&{p['text'] for p in ep}),
        'comments_including_parent_context':len(own_comments&comment_keys),
        'comments_by_exact_text':len({c['text'] for c in comments}&{c['text'] for c in ec}),
        'pairs':len({frozenset((p['a'],p['b'])) for p in pairs}&{frozenset((p['a'],p['b'])) for p in er}),
    }
    assert not any(overlaps.values()),overlaps
    assert len(posts)>=40 and len(comments)>=20
    assert Counter(p['same_event'] for p in pairs)=={True:12,False:12}
    assert len({p['id'] for p in posts})==len(posts)
    assert len({c['id'] for c in comments})==len(comments)
    assert len({frozenset((p['a'],p['b'])) for p in pairs})==len(pairs)
    for p in posts:
        assert set(p['expected']['topics']) <= {'zec','eth','btc','sol','ton'}
        assert not re.search(r'\b(aave|arc|arclings|archub)\b',p['text'],re.I),p['id']
        for s in p['expected']['segments']: assert p['text'][s['start']:s['end']]==s['text']
    return dict(posts=len(posts),comments=len(comments),pairs=len(pairs),same_event=12,different_event=12,channels=len({p['channel'] for p in posts}),topics=dict(Counter(t for p in posts for t in p['expected']['topics'])),relevant_news=dict(Counter(str(p['expected']['relevant_news']) for p in posts)),comment_links=dict(Counter(c['expected']['link_target'] for c in comments)),overlaps=overlaps)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'astrafeed.db')
    parser.add_argument('--export',type=Path,help='Новый, ещё не существующий каталог для трёх JSONL')
    args=parser.parse_args()
    baseline=json.loads((ROOT/'artifacts/pulse-slices.json').read_text())['db_md5']
    before=digest(args.db,'md5'); assert before==baseline,(before,baseline)
    try:
        with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            data=generate(db)
        report=validate(data,ROOT/'artifacts/news-eval')
        serialized={name:''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows) for name,rows in data.items()}
        if args.export:
            args.export.mkdir(parents=True,exist_ok=False)
            for name,body in serialized.items(): (args.export/name).write_text(body,encoding='utf-8')
        else:
            for name,body in serialized.items(): assert (HERE/name).read_text(encoding='utf-8')==body,name
            manifest=json.loads((HERE/'manifest.json').read_text())
            for name,expected in manifest['sha256'].items(): assert digest(HERE/name)==expected,name
        report['db_md5']=before
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        after=digest(args.db,'md5')
        assert after==before==baseline, 'MD5 базы изменился'

if __name__=='__main__': main()
