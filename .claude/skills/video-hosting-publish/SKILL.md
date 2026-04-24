---
name: video-hosting-publish
description: Публикует одобренные редактором черновики на локальный видеохостинг. Читает строки из pipeline Google Sheet где approved=TRUE и vh_video_id пуст. Берёт ТОЛЬКО финальные значения chosen_* (не варианты). После успешной публикации пишет vh_video_id и published_at обратно в Sheet. Идемпотентно — повторный запуск не публикует уже опубликованное.
---

# /video-hosting-publish

Вторая половина human-in-the-loop: код публикует то, что одобрил редактор. Никаких автопубликаций «из коробки».

## Принципы

- **Только одобренное.** Читаем строки где `approved == TRUE` И `vh_video_id` пустой.
- **Только финальное.** Берём `chosen_title`, `chosen_desc`, `chosen_thumb`. Не варианты. Это центральная HITL-гарантия: если редактор поправил заголовок вручную — идёт правка, не вариант №1.
- **Идемпотентно.** После заливки пишем `vh_video_id` + `published_at` в ту же строку. На следующем запуске она отфильтруется.
- **LLM не участвует.** Чистое I/O: прочитать Sheet → POST на API → записать результат обратно.

## Рабочая директория

`/Users/turilinalexander/learning engine/m07-hitl-sandbox/`

## Шаги

### 1. Получить список строк к публикации

```bash
.venv/bin/python scripts/cli.py list-approved
```

Возвращает JSON-массив. Каждый элемент:
```json
{"row_index": 0, "video_filename": "clip_xxx.mp4", "chosen_title": "...", "chosen_desc": "...", "chosen_thumb": "/abs/path/clip_xxx_2.png"}
```

`row_index` — 0-based индекс среди data-строк (понадобится на шаге 3). Если массив пуст — публиковать нечего.

### 2. Для каждой строки — загрузить на видеохостинг

```bash
.venv/bin/python scripts/cli.py upload "<video_filename>" "<chosen_thumb>" "<chosen_title>" "<chosen_desc>"
```

Скрипт делает POST multipart на `http://localhost:5001/video_hosting/api/videos` с Bearer-токеном из `VH_TOKEN` в `.env`. Возвращает JSON ответа на stdout — поле `video_id` и `published_at`.

Если upload падает (HTTP 4xx/5xx) — логируй, **не** помечай строку как опубликованную, идёт дальше.

### 3. Пометить строку как опубликованную

```bash
.venv/bin/python scripts/cli.py mark-published <row_index> <video_id> <published_at>
```

Пишет `vh_video_id` и `published_at` в колонки P/Q этой строки. Следующий запуск её пропустит.

### 4. Отчёт

Кратко: сколько опубликовано, сколько упало и по какой причине, ссылка на галерею `http://localhost:5173/video-hosting` — глазами проверить.

## Границы

- **Не** трогай колонки `video_filename`, `subject`, `title_*`, `desc_*`, `thumb_*`, `chosen_*`, `approved`. Они уже финальные.
- **Не** переопубликовывай — если `vh_video_id` непустой, строку пропускай.
- **Не** используй варианты (`title_1/2/3`, `desc_1/2/3`, `thumb_1/2/3`). Только `chosen_*`.
