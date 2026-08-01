#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从中文维基百科抓取物种简介 + 图片，生成 data/animals.json。
- 入口：data/species_master.json（含 name/level/category/provinces）
- 输出：data/animals.json（在 master 基础上附加 desc/image/wiki）
- 断点续跑：已抓取成功的物种直接跳过
"""
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import threading

MASTER = 'data/species_master.json'
OUT = 'data/animals.json'
UA = {'User-Agent': 'WildlifeMapDemo/1.0 (educational project; contact: example@example.com)'}

# 全局限速：两次请求最小间隔（秒），避免被维基百科限流
RATE_INTERVAL = 0.15
_rate_lock = threading.Lock()
_last_req = [0.0]

def _throttle():
    with _rate_lock:
        wait = _last_req[0] + RATE_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()

def http_get_json(url, retries=3):
    """带指数退避重试的 GET，处理 429/5xx"""
    for attempt in range(retries):
        _throttle()
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt + 1)
                continue
            raise
        except Exception:
            time.sleep(2 ** attempt + 1)
            if attempt == retries - 1:
                raise
    return None

# 手动别名：名录名称 -> 维基百科页面标题（命中即用，不再搜索）
ALIAS = {
    '虎': '虎',
    '藏羚': '藏羚',
    '大熊猫': '大熊猫',
    '川金丝猴': '川金丝猴',
    '雪豹': '雪豹',
    '金丝猴': '川金丝猴',
    '斑鳖': '斑鳖',
    '江豚': '长江江豚',
    '长江江豚': '长江江豚',
    '白鱀豚': '白鱀豚',
    '中华白海豚': '中华白海豚',
    '中华鲟': '中华鲟',
    '白鲟': '白鲟',
    '虎纹蛙': '虎纹蛙',
    '黄胸鹀': '黄胸鹀',
    '大鸨': '大鸨',
    '朱鹮': '朱鹮',
    '扬子鳄': '扬子鳄',
    '金斑喙凤蝶': '金斑喙凤蝶',
    '黄嘴白鹭': '黄嘴白鹭',
    '勺嘴鹬': '勺嘴鹬',
    '黑嘴松鸡': '黑嘴松鸡',
    '丹顶鹤': '丹顶鹤',
    '绿孔雀': '绿孔雀',
    '普氏野马': '普氏野马',
    '麋鹿': '麋鹿',
    '驼鹿': '驼鹿',
    '穿山甲': '穿山甲',
    '大灵猫': '大灵猫',
    '小灵猫': '小灵猫',
    '紫貂': '紫貂',
    '雪兔': '雪兔',
    '河狸': '河狸',
    '中华穿山甲': '中华穿山甲',
    '马来穿山甲': '马来穿山甲',
    '印度穿山甲': '印度穿山甲',
    '海南长臂猿': '海南长臂猿',
    '长臂猿': '长臂猿',
    '黔金丝猴': '黔金丝猴',
    '滇金丝猴': '滇金丝猴',
    '川西白眉长臂猿': '白眉长臂猿',
    # 消歧义页面 → 具体词条
    '黑熊': '亚洲黑熊',
    '马鹿': '欧洲马鹿',
    '蟒蛇': '缅甸蟒',
    '野牛': '印度野牛',
    '野猫': '斑猫',
    '红脚隼': '阿穆尔隼',
    '灰林鸮': '西灰林鸮',
    '冠斑犀鸟': '斑犀鳥',
}

def http_get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def summary(title):
    """返回 (title, desc, image, page_url) 或 None"""
    u = 'https://zh.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title)
    try:
        d = http_get_json(u)
    except Exception:
        return None
    if d.get('type') == 'disambiguation':
        return None
    return (d.get('title') or title,
            d.get('extract') or '',
            (d.get('thumbnail') or {}).get('source'),
            (d.get('content_urls') or {}).get('desktop', {}).get('page'))

def search_title(name):
    u = ('https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=%s'
         '&srlimit=1&format=json&utf8=1&formatversion=2&srnamespace=0') % urllib.parse.quote(name)
    try:
        d = http_get_json(u)
        hits = d.get('query', {}).get('search', [])
        if hits:
            return hits[0]['title']
    except Exception:
        pass
    return None

def fetch_one(name):
    # 1) 别名表
    if name in ALIAS:
        r = summary(ALIAS[name])
        if r:
            return r
    # 2) 候选标题：原名 / 去掉"所有种" / 去掉"属所有种"
    candidates = [name]
    for suf in ('属所有种', '所有种'):
        if name.endswith(suf):
            candidates.append(name[: -len(suf)])
    for cand in candidates:
        r = summary(cand)
        if r and r[1]:
            return r
    # 3) 搜索回退
    t = search_title(name)
    if t:
        r = summary(t)
        if r and r[1]:
            return r
    return None

def main():
    master = json.load(open(MASTER, encoding='utf-8'))
    existing = {}
    if os.path.exists(OUT):
        existing = {s['name']: s for s in json.load(open(OUT, encoding='utf-8')).get('species', [])}

    todo = [m for m in master if m['name'] not in existing or not existing[m['name']].get('desc')]
    print('总物种:', len(master), '待抓取:', len(todo))

    lock = threading.Lock()
    done_count = [0]
    fail_names = []

    def worker(pool):
        while True:
            lock.acquire()
            if not pool:
                lock.release()
                return
            m = pool.pop()
            lock.release()
            try:
                r = fetch_one(m['name'])
            except Exception as e:
                r = None
            with lock:
                if r:
                    existing[m['name']] = {
                        **m,
                        'desc': r[1][:400],
                        'image': r[2],
                        'wiki': r[3],
                        'wiki_title': r[0],
                    }
                else:
                    existing[m['name']] = {**m, 'desc': '', 'image': None, 'wiki': None}
                    fail_names.append(m['name'])
                done_count[0] += 1
                if done_count[0] % 25 == 0:
                    print('进度:', done_count[0], '/', len(todo), flush=True)
                # 定期落盘
                if done_count[0] % 50 == 0:
                    with open(OUT, 'w', encoding='utf-8') as f:
                        json.dump({'species': sorted(existing.values(), key=lambda s: s['name'])},
                                  f, ensure_ascii=False, indent=1)
            time.sleep(0.05)

    pool = list(todo)
    threads = [threading.Thread(target=worker, args=(pool,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'species': sorted(existing.values(), key=lambda s: s['name'])},
                  f, ensure_ascii=False, indent=1)

    with_img = sum(1 for s in existing.values() if s.get('image'))
    with_desc = sum(1 for s in existing.values() if s.get('desc'))
    print('完成。总:', len(existing), '有图:', with_img, '有简介:', with_desc)
    print('失败/无条目:', fail_names)

if __name__ == '__main__':
    main()
