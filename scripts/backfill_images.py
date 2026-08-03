#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为无图物种自动补图：
  1) 英文维基百科 REST summary（词条主图）
  2) Wikimedia Commons 按学名/英文名搜索文件（优先文件名精确包含学名）
- 输入/输出：data/animals.json（原子写盘 + 断点续跑）
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DATA = 'data/animals.json'
UA = {'User-Agent': 'WildlifeMapDemo/1.0 (educational project; contact: example@example.com)'}
THROTTLE = 0.25
MAX_WORKERS = 4
SAVE_EVERY = 10
TIMEOUT = 8   # 网络不稳定时快速失败，避免长时间卡死
RETRIES = 2
IMG_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')

_lock = threading.Lock()
_last = [0.0]


def throttle():
    with _lock:
        wait = _last[0] + THROTTLE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def get_json(url, retries=RETRIES):
    """带指数退避重试的 GET（429/403/5xx 都重试）"""
    for attempt in range(retries):
        throttle()
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 403, 500, 502, 503, 504):
                time.sleep(2 ** attempt + 1)
                continue
            return None
        except Exception:
            time.sleep(2 ** attempt + 1)
    return None


def norm(s):
    """规范化字符串用于文件名匹配（去标点空格、小写）"""
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def en_thumb(s):
    """英文维基词条主图"""
    title = s.get('en_name') or s.get('wiki_title') or s.get('scientific')
    if not title:
        return None
    url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title)
    d = get_json(url)
    if not d:
        return None
    return (d.get('thumbnail') or {}).get('source')


def commons_search(s):
    """在 Wikimedia Commons 按学名/英文名搜索图片文件"""
    sci = s.get('scientific') or ''
    en = s.get('en_name') or ''
    queries = [x for x in (sci, en) if x]
    sci_n = norm(sci)
    en_n = norm(en)
    for q in queries:
        url = ('https://commons.wikimedia.org/w/api.php?action=query&list=search'
               '&srsearch=%s&srnamespace=6&srlimit=8&format=json&formatversion=2'
               % urllib.parse.quote('"%s"' % q))
        d = get_json(url)
        if not d:
            continue
        for h in d.get('query', {}).get('search', []):
            title = h.get('title', '')
            low = title.lower()
            if not low.endswith(IMG_EXTS) or not low.startswith('file:'):
                continue
            base = norm(title[5:title.rfind('.')])
            # 文件名必须包含完整学名或英文名，避免抓错图
            if (sci_n and sci_n in base) or (en_n and en_n in base):
                u = ('https://commons.wikimedia.org/w/api.php?action=query&titles=%s'
                     '&prop=imageinfo&iiprop=url|mime&iiurlwidth=400&format=json&formatversion=2'
                     % urllib.parse.quote(title))
                dd = get_json(u)
                if not dd:
                    continue
                for p in dd.get('query', {}).get('pages', []):
                    ii = (p.get('imageinfo') or [{}])[0]
                    if ii.get('mime', '').startswith('image/') and ii.get('thumburl'):
                        return ii['thumburl']
    return None


def fetch_one(s):
    """返回图片 URL 或 None：先英文维基，再 Commons"""
    img = en_thumb(s)
    if img:
        return img
    return commons_search(s)


def save(data, path):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    species = data['species']
    todo = [s for s in species if not s.get('image')]
    print('总物种:', len(species), '待补图:', len(todo))

    lock = threading.Lock()
    done = [0]
    failed = []
    count = [0]

    def worker(pool):
        while True:
            with lock:
                if not pool:
                    return
                s = pool.pop()
            try:
                img = fetch_one(s)
            except Exception:
                img = None
            with lock:
                done[0] += 1
                if img:
                    s['image'] = img
                    count[0] += 1
                    print('  [%d/%d] 补图成功: %s' % (done[0], len(todo), s['name']), flush=True)
                else:
                    failed.append(s['name'])
                if done[0] % SAVE_EVERY == 0 or done[0] == len(todo):
                    save(data, DATA)
                    print('  进度 %d/%d，已保存' % (done[0], len(todo)), flush=True)

    pool = list(todo)
    threads = [threading.Thread(target=worker, args=(pool,)) for _ in range(MAX_WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    save(data, DATA)
    print('完成。补图成功:', count[0], '仍无图:', len(failed))
    if failed:
        print('仍无图名单:', failed)


if __name__ == '__main__':
    main()
