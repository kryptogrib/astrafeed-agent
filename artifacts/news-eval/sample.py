#!/usr/bin/env python3
"""Замороженная ручная агентская выборка; stdlib, SQLite только mode=ro.
Без аргументов — проверка. --export DIR — воспроизведение в НОВОМ каталоге.
Это декларации ответов по прочитанным публикациям, не правила классификатора.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MD5 = '8618099125a806df376354286ccd982e'
# id, темы запроса, релевантная новость по этим темам, событие, происхождение,
# роль наблюдаемого канала, основание, классы фрагментов.
LABELS = [
(1,'eth',False,None,'own','editorial','ETH — цена минта на Robinhood; подборка активностей не сообщает событие Ethereum.','promo_service'),
(3,'arc',True,'arc-nft-mints-0916','retelling','editorial','Названы коллекции и расписание сегодняшних минтов в экосистеме Arc; есть призывы к участию.','event,promo_service'),
(13,'zec',True,'zaddr-mint-0921','retelling','editorial','Конкретная дата минта Zaddr; подборка содержит и другие события экосистемы, а также промо.','event,promo_service'),
(22,'zec',False,None,'own','author','Подборка WL и общая оценка роста без отдельного конкретного нового события.','author_position,promo_service'),
(27,'eth',False,'balancer-closure-proposal','retelling','author','Предложение закрыть Balancer; Ethereum лишь место работы DEX. Это не закрытие сети Ethereum.','event,author_position'),
(49,'eth',False,'clarity-vote-failed','retelling','author','ETH встречается лишь в подвале котировок. Новости про Clarity Act и Алтын, плюс реклама карты.','event,author_position,promo_service'),
(56,'eth',False,None,'own','author','Автор оценивает силу BTC; ETH только в котировках.','author_position,promo_service'),
(60,'eth',False,'btc-week-gain-0921','own','author','Сообщение о недельной динамике BTC/SOL; ETH только в подвале.','event,author_position,promo_service'),
(65,'zec',True,'zec-rank9-0917','own','author','Сообщает о девятом месте ZEC и отдельно оценивает отсутствие FOMO.','event,author_position'),
(70,'zec',False,None,'own','author','Рассуждение об обещаниях проектов; ZEC приведён как пример влияния без нового события.','author_position'),
(221,'eth',True,'eth-base-wallet-standard-stop','retelling','editorial','Пересказ Coindesk об отказе Ethereum и Base от общего стандарта.','event,redistribution'),
(262,'eth',True,'tom-lee-eth6000-statement','retelling','editorial','Атрибутированное заявление Тома Ли; прогноз не является установленной будущей ценой.','event,redistribution'),
(345,'zec',True,'zec-1300-0917','unknown','editorial','Выделенный ценовой рубеж ZEC и ироническая оценка анонимности.','event,author_position'),
(423,'eth',True,'blackrock-exchange-transfers-0917','retelling','editorial','Переводы на биржу сообщаются отдельно от предположения о продаже.','event,author_position,redistribution'),
(446,'zec',True,'zec-nu7-vote','retelling','editorial','Результат голосования за блоки 25 секунд; цена 1400 — дополнительное событие.','event'),
(467,'zec',True,'zec-1500-0917','unknown','editorial','Самостоятельный ценовой алерт, не подвал котировок.','event'),
(474,'eth',True,'eth-fees-santiment-0917','retelling','editorial','Снижение комиссии до 0,095 доллара со ссылкой на Santiment.','event,redistribution'),
(653,'eth',True,'eth-holders-record-0919','retelling','editorial','Новый рекорд держателей и активность китов по Santiment.','event,redistribution'),
(731,'eth',True,'eth-2700-0921','unknown','editorial','Тестирование 2700 как максимума с января, отдельно редакционная реплика.','event,author_position'),
(745,'zec',True,'zec-nu7-november-plan','retelling','editorial','Сообщение о плане обновления в ноябре, не о фактическом запуске.','event,redistribution'),
(810,'eth',True,'bitmine-buy-27562-0921','retelling','editorial','Недельная покупка 27562 ETH; не покупка 27180 ETH неделей ранее.','event,redistribution'),
(1101,'zec',True,'zec-1600-0923','unknown','editorial','Отдельный ценовой рубеж 1600 через несколько дней после 1500.','event'),
(1909,'zec',True,'zec-nu7-vote','retelling','editorial','Заголовок сообщает поддержку ускорения и графика халвингов держателями.','event'),
(3900,'zec',True,'zec-nu7-november-plan','retelling','editorial','Заголовок о ноябрьском плане ускорения приватных платежей.','event'),
(4177,'zec',True,'garrett-short-loss-0917','retelling','editorial','Срез позиции: убыток 26,5 млн, размер 51 млн, ликвидация 2631.','event,redistribution'),
(4179,'zec',True,'garrett-spot-disclosure-0919','retelling','editorial','Показан спотовый адрес и объяснён хедж; это новое раскрытие, не прежний убыток.','event,author_position'),
(4233,'zec',True,'zec-1400-0917','unknown','editorial','Отдельный ценовой алерт 1400.','event'),
(4253,'zec',True,'dragonfly-zcash-fund-proposal','retelling','editorial','Предложение партнёра Dragonfly свернуть фонд; это заявление, не состоявшееся закрытие.','event,redistribution'),
(4274,'eth',True,'robinhood-l2-eth-fees-study','retelling','editorial','Прямое сравнение полученных Ethereum комиссий с доходами L2; ETH не случайное упоминание.','event,redistribution'),
(4301,'eth',True,'trueo-base-to-ethereum','retelling','editorial','Объявление миграции Trueo на Ethereum и цитируемая реакция Виталика.','event,redistribution'),
(6985,'eth',False,None,'own','author','Личный тест торгового бота и реферальное продвижение Veles, не новость сети/токена ETH.','author_position,promo_service'),
(7098,'zec',False,None,'unknown','editorial','ZEC — строка общей таблицы gainers/losers.','promo_service'),
(7381,'eth',True,'bitmine-buy-27180-0914','retelling','editorial','Покупка 27180 ETH; внизу атрибуция DeCenter.','event,redistribution'),
(7593,'zec',True,'garrett-short-loss-0917','repost','editorial','Точная копия raw_item 4177 в другом канале, опубликована позже.','event,redistribution'),
(7776,'zec',True,'garrett-spot-disclosure-0919','repost','editorial','Точная копия raw_item 4179 в агрегаторе.','event,redistribution'),
(8548,'eth',True,'bitmine-buy-27180-0914','retelling','editorial','Недельная покупка 27180 ETH и достижение около 4,9% предложения.','event,redistribution'),
(12834,'zec',True,'zec-nu7-vote','retelling','editorial','Подробности того же голосования; ноябрьская реализация ещё впереди.','event'),
(12837,'zec',True,'starkware-ceo-zec-statement','retelling','editorial','Атрибутированное мнение CEO StarkWare о причинах роста ZEC — событие заявления.','event,redistribution'),
(12838,'zec',True,'zec-1500-0917','unknown','editorial','Тот же рубеж 1500 в тот же день, другой канал.','event'),
(12843,'zec',False,None,'unknown','editorial','Идея технического анализа с целью 3100, нового события нет.','author_position'),
(12861,'zec',False,'garrett-btc-long-0918','retelling','editorial','Новость о лонге BTC, ZEC только в ссылке на прежнюю сделку.','event,redistribution'),
(13863,'eth',True,'bitmine-buy-27180-0914','retelling','author','Сообщает тот же достигнутый объём 4,9% в день отчёта 14 сентября; дальнейшие планы отдельно.','event,redistribution'),
(13659,'zec',False,None,'own','participant','Личный торговый опыт вокруг WORTH; прибыль Leo по ZEC — контекст без однозначной идентификации события.','participant_reaction'),
]
# Фрагменты выбирались при чтении вручную. Перекрытие event/redistribution допустимо.
SPANS = {
3: {'event':'Arcadians:  \n• 14:30 МСК;', 'promo_service':'Обязательно перепроверяем ссылки перед подключением кошельков, для минтов используем новые кошельки. DYOR.'},
13: {'event':'• дата минта: 21 сентября WL 16:00 МСК, public 19:00 МСК. Минт будет тут.', 'promo_service':'Все просто, регистрируемся в WL, ждем результатов, лутаем бабки.'},
22: {'author_position':'#ZEC растёт, с ним и активность в сети. NFT коллекции ожили первыми и уже дали кому-то заработать.', 'promo_service':'Дедлайны везде разные, лучше сделайте сейчас.'},
27: {'event':'Теперь казначейский совет вынес на голосование план закрытия.', 'author_position':'Классический конец эпохи DeFi 1.0.'},
49: {'event':'Clarity Act НЕ набрал 60 голосов для перехода к следующему этапу и заморожен.', 'author_position':'Крипта летит вниз…', 'promo_service':'советую оформить международную карту по промокоду DED всего за 699 рублей.'},
56: {'author_position':'Даже на относительно плохих новостях (отмена clarity act, повышение ставки ФРС) биток показывает силу, при чем даже в пятницу- это отличный знак!', 'promo_service':'BTC $80 200\nETH $2 552\nGRAM $1.37'},
60: {'event':'Биткоин сделал +9% за неделю, солана вообще +14%, хотя летом набирали её по $70', 'author_position':'BTC идёт вне ожиданий рынка и не на новостях вообще!', 'promo_service':'Ставь лайк, если рад или огонёк, если всё пропустил!'},
65: {'event':'ZEC уже 9 позиция в ТОПе крипты','author_position':'Но как будто FOMO тотального еще нет'},
345: {'event':'#ZEC = +20% > $1300','author_position':'становится еще анонимнее при цене > $1300 — аналитики'},
423: {'event':'BlackRock сегодня начал переводить BTC и ETH на биржи','author_position':'скорее всего, на продажу для клиентов','redistribution':'— мониторинг'},
731: {'event':'ETH тестирует отметку $2700, это максимум с января 2026г.','author_position':'Виталик одобряет.'},
4179: {'event':'показал свой спот адрес Zec','author_position':'фактически его шорт является частично дельта нейтральным (размер спота в разы больше шорта)'},
6985: {'author_position':'Мне такой подход нравится больше всего:', 'promo_service':'👉🏻 Veles — https://veles.finance/invite/krasnov'},
}
# source_id, post_id, comment_id, link_target, предмет, основание.
COMMENTS = [
(2,'5299','380287','other_subject','BITFOOTS','Предлагает добавить отдельную NFT-коллекцию, не обсуждает сеть ZEC.'),
(2,'5299','380296','topic_level_uncertain','Кошельки Zcash','Только ссылка; родителя 380286 в базе нет, конкретное событие неизвестно.'),
(2,'5299','380318','topic_level_uncertain','Неустановленный кошелёк','Текст «Этот же кош?» без имени; медиаконтекст не интерпретируется.'),
(2,'5299','380335','other_subject','Zeckers','Ссылка на NFT-чекер; смена предмета с общей подборки на конкретный сервис.'),
(2,'5299','380336','other_subject','Zeckers / Zodl','Вопрос о кошельке в ответ на ссылку Zeckers, не проблема сети Zcash.'),
(2,'5299','380337','other_subject','Zeckers','Закрытая форма — состояние NFT-сервиса, не сети.'),
(2,'5299','380347','other_subject','OTTO Club','Вопрос про ETH-кошелёк у OTTO внутри ZEC-ветки.'),
(2,'5299','380348','other_subject','OTTO Club','Уточняет, что OTTO не ZEC; сохраняем предмет родителя.'),
(2,'5299','380352','other_subject','Noir','Рекомендация NFT-кошелька, не реакция на протокольную новость.'),
(2,'5299','380362','other_subject','Zeckers','Не находит поле проверки WL при минте Zeckers.'),
(2,'5299','380370','other_subject','Zeckers','Подозрение в скаме и отсутствие продаж относится к чекеру из родителя 380335.'),
(6,'2426','150547','author_thesis','FOMO','Прямо оспаривает тезис автора: FOMO уже у всех.'),
(6,'2426','150550','author_thesis','FOMO','Обсуждает условие возникновения FOMO, названное в посте.'),
(6,'2426','150552','project','Zcash','Ожидание дохода от шорта ZEC, не реакция на место в рейтинге.'),
(6,'2426','150563','project','Zcash','Собственный ценовой прогноз по теме ветки без связи с событием.'),
(6,'2426','150566','project','Zcash','Сценарий перехода в приватность; не факт нового события.'),
(6,'2426','150569','other_subject','DASH','Явно переключает обсуждение на DASH.'),
(6,'2426','150558','other_subject','Шутка про хейтеров','Продолжение шутки родителя, не тезис о проекте.'),
(6,'2426','150560','topic_level_uncertain','Неустановленная телепередача','Недостаточно данных, чтобы связать с девятым местом или другой новостью.'),
(21,'21078','342794','author_thesis','BMNR против ETH','Развивает инвестиционный тезис о BMNR, не подтверждает покупку ETH.'),
(21,'21078','342795','other_subject','Личный портфель BMNR','Ответ о собственных покупках и дивидендах; не сделка компании.'),
(3,'6921','138136','event:balancer-closure-proposal','Закрытие Balancer','Остатки казны и май 2027 однозначно связывают реплику с предложением закрытия.'),
(3,'6921','138133','author_thesis','История Balancer','Спрашивает про тезис «пережил не один цикл».'),
(1,'7139','571620','other_subject','Сайт Arclings','Жалоба на недоступность NFT-сайта; не утверждение о сбое сети Arc или ZEC.'),
(1,'7139','571621','other_subject','Сайт Arclings','Нет кнопки минта на сайте из родительской жалобы.'),
(1,'7139','571644','other_subject','OpenSea','Вопрос о наградах OpenSea переключает предмет относительно минтов Arc.'),
]
POS = [(1909,446),(1909,12834),(446,12834),(3900,745),(467,12838),(4177,7593),(4179,7776),(8548,7381),(8548,13863),(7381,13863)]
NEG = [(4177,4179),(8548,810),(7381,810),(467,1101),(345,467),(446,4253),(474,653),(221,4301),(12837,4253),(423,810)]
# Только резерв темы и окна; ответы holdout не создаются.
HOLDOUT = {'topic':'aave','aliases':['aave'],'window':{'start':'2026-09-22T00:00:00+00:00','end':'2026-09-24T00:00:00+00:00','interval':'[start,end)'}}

def decode(text):
    # Один слой JSON-экранирования только для payload с буквальным \\u.
    return json.loads('"' + text.replace('"', '\\"') + '"') if '\\u' in text else text

def digest(path, algo='sha256'):
    h = hashlib.new(algo)
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def iso(value):
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc).isoformat()

def build(db):
    before = digest(db,'md5')
    assert before == MD5, 'MD5 базы не совпадает с замороженным'
    con = sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    posts=[]
    for rid,topics,news,event,origin,role,reason,classes in LABELS:
        r=con.execute('SELECT * FROM raw_item WHERE id=?',(rid,)).fetchone()
        p=json.loads(r['payload']); raw=p['text']; text=decode(raw)
        segments=[]
        for cls in classes.split(','):
            quote=SPANS.get(rid,{}).get(cls,text)
            start=text.index(quote)
            segments.append({'class':cls,'start':start,'end':start+len(quote),'text':quote})
        n=con.execute('SELECT count(*) FROM comment WHERE source_id=? AND post_id=?',(r['source_id'],r['external_id'])).fetchone()[0]
        events=[event] if event else []
        if rid==446: events.append('zec-1400-0917')
        if rid==12834: events.append('zec-nu7-november-plan')
        if rid==13: events += ['bitx-waitlist','zecfrogs-mint-0921']
        posts.append({'id':f'p{rid}','raw_item_id':rid,'source_id':r['source_id'],'channel':p['channel_ref'],'external_id':r['external_id'],'link':p['link'],'timestamp':iso(r['timestamp']),'text':text,'text_raw':raw,'stored_comments':n,'expected':{'topics':topics.split(','),'relevant_news':news,'segments':segments,'origin':origin,'source_role':role,'event_id':event,'event_ids':events,'reason':reason}})
    index={p['raw_item_id']:p for p in posts}
    comments=[]
    for sid,pid,cid,target,subject,reason in COMMENTS:
        r=con.execute('SELECT * FROM comment WHERE source_id=? AND post_id=? AND comment_id=?',(sid,pid,cid)).fetchone()
        parent=con.execute('SELECT comment_key,ts,text FROM comment WHERE source_id=? AND post_id=? AND comment_id=?',(sid,pid,r['parent_comment_id'])).fetchone()
        post=next(p for p in posts if p['source_id']==sid and p['external_id']==pid)
        comments.append({'id':r['comment_key'],'source_id':sid,'channel':post['channel'],'post_id':pid,'post_ref':post['id'],'external_id':cid,'parent_comment_id':r['parent_comment_id'],'timestamp':iso(r['ts']),'link':r['link'],'text':r['text'],'parent_context':dict(parent) if parent else None,'expected':{'class':'participant_reaction','link_target':target,'subject':subject,'reason':reason}})
    pairs=[]
    for truth,items in [(True,POS),(False,NEG)]:
        for a,b in items:
            ea=index[a]['expected'];eb=index[b]['expected']
            assert (ea['event_id']==eb['event_id']) == truth
            pairs.append({'id':f'pair-{len(pairs)+1:02}','a':f'p{a}','b':f'p{b}','same_event':truth,'event_id':ea['event_id'] if truth else None,'shared_topics':sorted(set(ea['topics']) & set(eb['topics'])),'reason':('Один наблюдаемый эпизод: '+ea['reason']+' / '+eb['reason']) if truth else ('Разные эпизоды при совпадающей теме: '+ea['reason']+' / '+eb['reason'])})
    windows={'timezone':'UTC','interval':'[start,end)','topics':{}}
    boundaries={'zec':(1909,745),'eth':(8548,810),'arc':(3,3)}
    for topic,(a,b) in boundaries.items():
        start=index[a]['timestamp'];end=index[b]['timestamp']
        if a==b: end=(dt.datetime.fromisoformat(start)+dt.timedelta(days=1)).isoformat()
        windows['topics'][topic]={'windows':[{'id':topic+'-coverage','start':'2026-09-09T00:00:00+00:00','end':'2026-09-24T00:00:00+00:00'},{'id':topic+'-boundary','start':start,'end':end}],'boundary_cases':[]}
        for rid in sorted({a,b}):
            t=dt.datetime.fromisoformat(index[rid]['timestamp'])
            probe={'post_ref':f'p{rid}','timestamp':t.isoformat(),'probes':[]}
            for offset in [-1,0,1]:
                cutoff=t+dt.timedelta(seconds=offset)
                probe['probes'].append({'start':'2026-09-09T00:00:00+00:00','end':cutoff.isoformat(),'expected_included':offset>0})
            probe['start_equal_included']=True
            windows['topics'][topic]['boundary_cases'].append(probe)
            index[rid].setdefault('boundary',[]).append({'topic':topic,'at_start':rid==a,'at_end':rid==b and a!=b})
        for p in posts:
            if topic in p['expected']['topics']:
                p.setdefault('window_membership',{})[topic+'-boundary']=start<=p['timestamp']<end
    con.close()
    assert digest(db,'md5')==before
    assert len(posts)>=40 and len(comments)>=20 and len(pairs)==20
    return posts,comments,pairs,windows

def summary(posts,comments,pairs):
    return {'posts':len(posts),'comments':len(comments),'pairs':len(pairs),'channels':len({p['channel'] for p in posts}),'topics':dict(collections.Counter(t for p in posts for t in p['expected']['topics'])),'relevant_news':dict(collections.Counter(str(p['expected']['relevant_news']).lower() for p in posts)),'classes_posts':dict(collections.Counter(c for p in posts for c in {s['class'] for s in p['expected']['segments']})),'origins':dict(collections.Counter(p['expected']['origin'] for p in posts)),'source_roles':dict(collections.Counter(p['expected']['source_role'] for p in posts)),'news_without_stored_comments':sum(p['expected']['relevant_news'] and p['stored_comments']==0 for p in posts),'opinion_without_event':sum(p['expected']['event_id'] is None and any(s['class']=='author_position' for s in p['expected']['segments']) for p in posts),'boundary_posts':sum('boundary' in p for p in posts),'comment_links':dict(collections.Counter(c['expected']['link_target'].split(':')[0] for c in comments)),'same_event':sum(p['same_event'] for p in pairs),'different_event':sum(not p['same_event'] for p in pairs)}

def content(posts,comments,pairs,windows):
    out={}
    for name,rows in [('posts',posts),('comments',comments),('pairs',pairs)]:
        out[name+'.jsonl']=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
    for name,obj in [('windows',windows),('holdout',HOLDOUT)]:
        out[name+'.json']=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'astrafeed.db')
    parser.add_argument('--export',type=Path)
    args=parser.parse_args()
    data=build(args.db); expected=content(*data)
    if args.export:
        args.export.mkdir(parents=True,exist_ok=False)
        for name,text in expected.items(): (args.export/name).write_text(text,encoding='utf-8')
    else:
        manifest=json.loads((HERE/'manifest.json').read_text())
        for name,sha in manifest['sha256'].items(): assert digest(HERE/name)==sha, name
        for name,text in expected.items(): assert (HERE/name).read_text()==text, name
    print(json.dumps(summary(*data[:3]),ensure_ascii=False,indent=2))
    print('MD5 базы до/после: '+MD5+'; read-only; проверка пройдена.')

if __name__=='__main__': main()
