#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 iNaturalist 为无图物种补图（按学名精确匹配，图片 CDN 国内可访问）。
- 输入/输出：data/animals.json（原子写盘 + 断点续跑）
- 图片许可：iNaturalist 默认 CC BY-NC / CC BY（公益科普站适用）
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
THROTTLE = 0.5      # iNaturalist 限速（毫秒级间隔即可，0.5s 更稳）
MAX_WORKERS = 3
SAVE_EVERY = 10
TIMEOUT = 25        # iNaturalist 从国内访问较慢
RETRIES = 2

_lock = threading.Lock()
_last = [0.0]


def throttle():
    with _lock:
        wait = _last[0] + THROTTLE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def get_json(url, retries=RETRIES):
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
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def search(query):
    """iNaturalist 分类搜索，返回 results 列表"""
    url = ('https://api.inaturalist.org/v1/taxa?q=%s&per_page=30'
           '&fields=id,name,preferred_common_name,rank,default_photo'
           % urllib.parse.quote(query))
    d = get_json(url)
    if not d:
        return []
    return d.get('results') or []


def medium_url(photo):
    if not photo:
        return None
    return (photo.get('medium_url') or photo.get('url') or '').replace('square.jpeg', 'medium.jpeg')


def fetch_one(s):
    """按学名搜（精确匹配）；失败再用英文名兜底"""
    sci = s.get('scientific') or ''
    en = s.get('en_name') or ''
    sci_n = norm(sci)
    en_n = norm(en)

    # 1) 学名搜索，要求结果里存在精确匹配的物种
    for r in search(sci or s['name']):
        if r.get('rank') == 'species' and norm(r.get('name')) == sci_n:
            u = medium_url(r.get('default_photo'))
            if u:
                return u

    # 2) 英文名兜底
    if en:
        for r in search(en):
            if r.get('rank') == 'species' and (
                    norm(r.get('name')) == en_n or norm(r.get('preferred_common_name')) == en_n):
                u = medium_url(r.get('default_photo'))
                if u:
                    return u
    return None


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
    count = [0]
    failed = []

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
