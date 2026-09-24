# Reaction subject v2 — generated tables

Same frozen sample and preliminary labels as v1: a regression comparison, not a new holdout.

## test

| arm | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | claim_error_rate | false_event | event_thesis_confusion | abstained | status_rejected | status_no_id | missed | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 69 | 0 | 0 | 3 | 0 | 3 | 1.0 | 0 | 0 | 66 | 0 | 0 | 48 | 0.043 | 0.0 |
| v1 context | 69 | 0 | 1 | 64 | 36 | 28 | 0.438 | 13 | 1 | 4 | 0 | 0 | 1 | 0.928 | 0.706 |
| v1 context+verify+id | 69 | 0 | 1 | 50 | 35 | 15 | 0.3 | 0 | 0 | 18 | 9 | 5 | 10 | 0.725 | 0.686 |
| v2 context | 69 | 0 | 3 | 58 | 36 | 22 | 0.379 | 5 | 1 | 8 | 0 | 0 | 4 | 0.841 | 0.706 |
| v2 context+id | 69 | 0 | 3 | 54 | 36 | 18 | 0.333 | 4 | 1 | 12 | 0 | 4 | 7 | 0.783 | 0.706 |
| v2 context+id+verify | 69 | 0 | 3 | 47 | 33 | 14 | 0.298 | 0 | 0 | 19 | 7 | 4 | 12 | 0.681 | 0.647 |

## test_undisputed

| arm | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | claim_error_rate | false_event | event_thesis_confusion | abstained | status_rejected | status_no_id | missed | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 44 | 0 | 0 | 2 | 0 | 2 | 1.0 | 0 | 0 | 42 | 0 | 0 | 31 | 0.045 | 0.0 |
| v1 context | 44 | 0 | 0 | 40 | 27 | 13 | 0.325 | 5 | 0 | 4 | 0 | 0 | 0 | 0.909 | 0.818 |
| v1 context+verify+id | 44 | 0 | 0 | 34 | 26 | 8 | 0.235 | 0 | 0 | 10 | 3 | 3 | 6 | 0.773 | 0.788 |
| v2 context | 44 | 0 | 3 | 36 | 27 | 9 | 0.25 | 1 | 0 | 5 | 0 | 0 | 3 | 0.818 | 0.818 |
| v2 context+id | 44 | 0 | 3 | 35 | 27 | 8 | 0.229 | 1 | 0 | 6 | 0 | 1 | 4 | 0.795 | 0.818 |
| v2 context+id+verify | 44 | 0 | 3 | 32 | 25 | 7 | 0.219 | 0 | 0 | 9 | 3 | 1 | 7 | 0.727 | 0.758 |

## dev

| arm | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | claim_error_rate | false_event | event_thesis_confusion | abstained | status_rejected | status_no_id | missed | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 0 | 0 | 0 | 0 | 0 | None | 0 | 0 | 30 | 0 | 0 | 29 | 0.0 | 0.0 |
| v1 context | 30 | 0 | 1 | 28 | 11 | 17 | 0.607 | 11 | 0 | 1 | 0 | 0 | 1 | 0.933 | 0.379 |
| v1 context+verify+id | 30 | 0 | 1 | 16 | 10 | 6 | 0.375 | 0 | 0 | 13 | 3 | 9 | 13 | 0.533 | 0.345 |
| v2 context | 30 | 0 | 1 | 28 | 22 | 6 | 0.214 | 3 | 2 | 1 | 0 | 0 | 1 | 0.933 | 0.759 |
| v2 context+id | 30 | 0 | 1 | 28 | 22 | 6 | 0.214 | 3 | 2 | 1 | 0 | 0 | 1 | 0.933 | 0.759 |
| v2 context+id+verify | 30 | 0 | 1 | 24 | 21 | 3 | 0.125 | 0 | 0 | 5 | 4 | 0 | 5 | 0.8 | 0.724 |

## test: по предмету (верно заявлено / заявлено; найдено / в эталоне)

| arm | event | author_thesis | project | other_subject | unclear | тезис: класс найден | тезис с id: найден / в эталоне | тезис с id: заявлено верно / заявлено |
|---|---|---|---|---|---|---|---|---|
| baseline | 0/0; 0/13 | 0/0; 0/7 | 0/2; 0/2 | 0/1; 0/29 | 0/66; 18/18 | 0/7 | 0/3 | 0/0 |
| v1 context | 10/23; 10/13 | 4/4; 4/7 | 0/3; 0/2 | 22/34; 22/29 | 0/4; 4/18 | 4/7 | 3/3 | 3/3 |
| v1 context+verify+id | 9/9; 9/13 | 4/4; 4/7 | 0/3; 0/2 | 22/34; 22/29 | 0/18; 9/18 | 4/7 | 3/3 | 3/3 |
| v2 context | 11/16; 11/13 | 3/6; 3/7 | 0/2; 0/2 | 22/34; 22/29 | 0/8; 6/18 | 3/7 | 3/3 | 3/3 |
| v2 context+id | 11/15; 11/13 | 3/3; 3/7 | 0/2; 0/2 | 22/34; 22/29 | 0/12; 7/18 | 3/7 | 3/3 | 3/3 |
| v2 context+id+verify | 8/8; 8/13 | 3/3; 3/7 | 0/2; 0/2 | 22/34; 22/29 | 0/19; 9/18 | 3/7 | 3/3 | 3/3 |

## test: v1 context+verify+id → v2 context+id+verify

### ошибка устранена (3)
- «флагманский продукт лять )))» — эталон unclear; v1 other_subject/ok; v2 unclear/rejected
- «ыы писало же.)» — эталон unclear; v1 other_subject/ok; v2 unclear/ok
- «это было в недельном обзоре, Раванга предположила, что вы его прочитали.» — эталон unclear; v1 other_subject/ok; v2 None/invalid

### новая ошибка (3)
- «На койнгеко написали что ключ украли» — эталон event; v1 unclear/rejected; v2 other_subject/ok
- «А не жирно ли работягам столько?» — эталон unclear; v1 unclear/rejected; v2 other_subject/ok
- «чувствую запах денег» — эталон unclear; v1 unclear/ok; v2 other_subject/ok

### ошибка в обоих (11)
- «То бишь hype или zec 😁» — эталон author_thesis; v1 other_subject/ok; v2 project/ok
- «Рекомендую посмотреть пару usdjpy к btcusdt и ethusdt. Там дневка и неделька рисуют интересные зоны дисбаланса» — эталон author_thesis; v1 other_subject/ok; v2 other_subject/ok
- «речь о Японии, сегодня ночью» — эталон unclear; v1 other_subject/ok; v2 other_subject/ok
- «моя ии не делает таких банальных ошибок» — эталон unclear; v1 other_subject/ok; v2 other_subject/ok
- «я стал откупать эфир и щитки, когда при 60 все до единого наши инфлы сказали, что идем на 48 )» — эталон project; v1 other_subject/ok; v2 other_subject/ok
- «Если Глиф и Р2 не появятся, возможно, шортисты заработают. Все падает без их ругани» — эталон unclear; v1 other_subject/ok; v2 other_subject/ok
- «готовы ректоваться?» — эталон event; v1 project/ok; v2 project/ok
- «норм метод через эллипс: ликвы нет, цены ниже реальных. стартер пакт на рект» — эталон unclear; v1 project/ok; v2 other_subject/ok
- «Удалите какашку)» — эталон unclear; v1 other_subject/ok; v2 other_subject/ok
- «а разрабы?» — эталон project; v1 other_subject/ok; v2 other_subject/ok
- «Ага "танцор диско"» — эталон unclear; v1 other_subject/ok; v2 other_subject/ok

### верная связь сохранена (27)
- «ващета сегодня» — эталон event; v1 event/ok; v2 event/ok
- «да да, точно» — эталон event; v1 event/ok; v2 event/ok
- «Там у хайпера если что фри позицию раздают 1к юсдт с 3 плечом за холд 2к юсдт на балансе просто» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Золото? Вот это поворот!» — эталон event; v1 event/ok; v2 event/ok
- «Вот это поворот, золото в крипте, ждем дальше» — эталон event; v1 event/ok; v2 event/ok
- «Вот это поворот, ждем новостей!» — эталон event; v1 event/ok; v2 event/ok
- «Ну это ж круто, смотрю за развитием» — эталон event; v1 event/ok; v2 event/ok
- «всем гм старые токены перефармлены, для безопасности ваших средств рекомендую искать новые лаунчи / грузиться » — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «а где можно посвапать usdc to eth на Lisk» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «юнипеги остановитесь, мы еще от второго ланчпада не отошли 😂» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Лаунчпад без воштрейдинг ботофермы - не лаунчпад, к сожалению 💧» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «💹 #NEAR +107% с начала сентября. ➟ В NEAR сделали фьючерсы на базе Hyperliquid приватными по умолчанию. ➟ Посл» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «А золото не смотрели? Просто оно снизу при перегретом рси красиво ретестит 200 ема. Но при этом криптоконтракт» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «золото зависит от ставки, если будет риторика что ее будут поднимать, оно не вырастет» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Благодарю. У меня просто ступор небольшой. По индикаторам моим вот просто всё указывает на либо локальный отка» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Кстати, если ентересно...держу етф msos начиная с 3,85. Сейчас 5,34 и он по идее в скором времени пробьет гори» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Ну если смотреть промсектор то рынок заложил плоххой и даже не забыл вшортить» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «рынок это больное на голову животное, а не гуру 😁» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «В истории на графике посмотришь 🤣» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «дальше 1500)» — эталон author_thesis; v1 author_thesis/ok; v2 author_thesis/ok
- «Скорее бы уже хоть что-то отросло, медвежка уже угнетает Хотя это всегда возможность взять со скидкой под гряд» — эталон author_thesis; v1 author_thesis/ok; v2 author_thesis/ok
- «еще скажи всю жизнь за эфир топил)» — эталон author_thesis; v1 author_thesis/ok; v2 author_thesis/ok
- «Kageuri норм еще» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «От дудлес будет нфт на робингуде, фришка» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «минт для GTD будет $50» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «рады слышать» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok
- «Минару в чс. Сутки не могли дать анонс по токену 😕» — эталон other_subject; v1 other_subject/ok; v2 other_subject/ok

### верная связь потеряна (8)
- «xaut давно же был на v4» — эталон event; v1 event/ok; v2 unclear/rejected
- «Ну зашквар или новый уровень?» — эталон event; v1 event/ok; v2 unclear/rejected
- «Вот это поворот, интригующе же» — эталон event; v1 event/ok; v2 unclear/rejected
- «DU, granddaughters! I've compiled today's top crypto news for you: 1️⃣ BTC adjusted a little after yesterday, » — эталон other_subject; v1 other_subject/ok; v2 None/invalid
- «Желаю вам, друзья, хорошего и успешного дня! Пусть сегодня всё получится 🤝» — эталон other_subject; v1 other_subject/ok; v2 unclear/ok
- «ага, Раванга это и предположила» — эталон author_thesis; v1 author_thesis/ok; v2 unclear/rejected
- «сейчас за Hazels слежу, топ-500 за GTD звучит как нормальная мотивация» — эталон other_subject; v1 other_subject/ok; v2 unclear/no_id
- «Это отличная рубрика, спасибо, так бы пропустил, что уже есть ВЛ на jpeg frens.🫂» — эталон other_subject; v1 other_subject/ok; v2 None/invalid

### новая верная связь (6)
- «Вот это поворот, золото в крипте, интересно» — эталон event; v1 unclear/rejected; v2 event/ok
- «кто вкрячил дизлайк бесплатной тулзе? 😱» — эталон other_subject; v1 project/ok; v2 other_subject/ok
- «АКА отлично покормили, а вот Arclings походу заскамили на 12 баксов» — эталон event; v1 None/invalid; v2 event/ok
- «утро надо начинать с большой кружки кофе и со сбора кукурузки» — эталон other_subject; v1 unclear/no_id; v2 other_subject/ok
- «Какие там затраты для топа?» — эталон other_subject; v1 unclear/no_id; v2 other_subject/ok
- «ты можешь зайти, бесплатные ключи потратить и надеяться на рафл» — эталон other_subject; v1 unclear/no_id; v2 other_subject/ok

## Цена и время

| версия | вызовы | USD | LLM, с |
|---|---|---|---|
| v1 | 44 | 0.00854 | 320.3 |
| v2 | 122 | 0.01175 | 409.5 |

