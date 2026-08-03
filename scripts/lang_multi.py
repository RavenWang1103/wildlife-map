#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为每个物种生成多语言简介：
  1) desc_zhs / desc_zht：用 zhconv 把现有维基简介本地转换为简体 / 繁体
  2) desc_en / en_wiki：用 qid 批量解析英文维基标题，再抓英文维基摘要
写回 data/animals.json（原子写入 + 断点续跑）。
用法: python3 -u scripts/lang_multi.py
"""
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
import zhconv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'animals.json')

UA = {'User-Agent': 'WildlifeMapDemo/1.0 (educational project)'}
RATE_INTERVAL = 0.15
MAX_EN_CHARS = 500  # 英文摘要截断长度

_lock = threading.Lock()
_last_req = [0.0]
_done = [0]


def throttle():
    with _lock:
        wait = _last_req[0] + RATE_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def get_json(url, retries=4):
    for attempt in range(retries):
        throttle()
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 403, 500, 502, 503, 504):
                time.sleep(2 ** attempt + 1)
                continue
            return None
        except Exception:
            time.sleep(2 ** attempt + 1)
            if attempt == retries - 1:
                return None
    return None


def chunked(lst, n=50):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def resolve_en_titles(species):
    """批量用 qid 解析英文维基标题，返回 {name: en_title}。
    qid 无 enwiki sitelink 时回退到英文常用名（en_name）作为候选标题。"""
    need = [s for s in species if s.get('qid') and not s.get('desc_en')]
    result = {}
    for batch in chunked(need):
        ids = '|'.join(s['qid'] for s in batch)
        url = ('https://www.wikidata.org/w/api.php?action=wbgetentities'
               '&ids=%s&props=sitelinks&format=json&utf8=1') % urllib.parse.quote(ids)
        d = get_json(url)
        if d:
            ents = d.get('entities', {})
            for s in batch:
                sl = (ents.get(s['qid']) or {}).get('sitelinks', {})
                t = sl.get('enwiki', {}).get('title')
                result[s['name']] = t or s.get('en_name') or ''
        else:
            for s in batch:
                result[s['name']] = s.get('en_name') or ''
        print('已解析英文标题 %d/%d' % (len([v for v in result.values() if v]), len(need)), flush=True)
    return {k: v for k, v in result.items() if v}


def fetch_en_summary(title):
    u = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title)
    d = get_json(u)
    if not d or d.get('type') == 'disambiguation':
        return None
    return (d.get('extract') or '')[:MAX_EN_CHARS]


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    species = data['species']

    # 1) 本地简繁转换（无网络，秒级）
    n = 0
    for s in species:
        if s.get('desc') and not s.get('desc_zhs'):
            s['desc_zhs'] = zhconv.convert(s['desc'], 'zh-hans')
            s['desc_zht'] = zhconv.convert(s['desc'], 'zh-hant')
            n += 1
    print('简繁转换完成: %d 条' % n, flush=True)

    # 2) qid -> 英文标题
    en_titles = resolve_en_titles(species)
    print('英文标题总数: %d' % len(en_titles), flush=True)

    # 3) 并发抓英文摘要
    todo = [s for s in species if s['name'] in en_titles]
    total = len(todo)

    def worker(pool):
        while True:
            with _lock:
                if not pool:
                    return
                s = pool.pop()
            try:
                r = fetch_en_summary(en_titles[s['name']])
            except Exception:
                r = None
            with _lock:
                if r:
                    s['desc_en'] = r
                _done[0] += 1
                if _done[0] % 25 == 0:
                    print('英文摘要进度: %d/%d' % (_done[0], total), flush=True)
                if _done[0] % 50 == 0:
                    tmp = DATA + '.tmp'
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=1)
                    os.replace(tmp, DATA)

    pool = list(todo)
    threads = [threading.Thread(target=worker, args=(pool,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 写回
    tmp = DATA + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA)

    has_zhs = sum(1 for s in species if s.get('desc_zhs'))
    has_zht = sum(1 for s in species if s.get('desc_zht'))
    has_en = sum(1 for s in species if s.get('desc_en'))
    print('\n完成。简体: %d, 繁体: %d, 英文: %d' % (has_zhs, has_zht, has_en))


if __name__ == '__main__':
    main()
