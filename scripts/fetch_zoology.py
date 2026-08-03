#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从中国动物主题数据库（zoology.especies.cn）批量抓取权威动物志描述。
流程：
  1) 读 data/animals.json（509 种，含 scientific 学名）
  2) 按类别依次尝试匹配数据库（descriptionType）
  3) 命中后按优先级抓取描述正文（description，每物种最多 MAX_TYPES 类）
  4) 写回 data/animals.json 的 fauna 字段
API Key 从项目根目录 .env 读取（ZOOLOGY_API_KEY），支持断点续跑。
用法: python3 -u scripts/fetch_zoology.py [--limit N] [--workers N] [--throttle X]
"""
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'animals.json')
ENV = os.path.join(ROOT, '.env')

MAX_TYPES = 2       # 每物种最多抓取的描述类型数
MAX_DB_TRIES = 3    # 每物种最多尝试的数据库数
HARD_CAP = 1900     # 全天调用安全上限，超出即停止（可续跑）
WORKERS = 3         # 并发线程数
THROTTLE = 0.3      # 秒，全局最小请求间隔

# 数据库优先级（名称必须与 dbaseName 返回完全一致）
DB_BY_CAT = {
    '鸟类':     ['中国鸟类数据库', '中国动物图谱数据库', '中国动物志数据库'],
    '哺乳动物': ['中国哺乳动物数据库', '中国动物图谱数据库', '中国动物志数据库'],
    '爬行动物': ['中国爬行动物数据库', '中国动物图谱数据库', '中国动物志数据库'],
    '两栖动物': ['中国两栖动物', '中国动物图谱数据库', '中国动物志数据库'],
    '鱼类':     ['中国内陆水体鱼类数据库', '中国动物图谱数据库', '中国动物志数据库'],
    '昆虫':     ['中国蝴蝶数据库', '中国直翅目与革翅目昆虫数据库', '中国动物图谱数据库'],
}
DB_FALLBACK = ['中国动物图谱数据库', '中国动物志数据库']

# 描述类型优先级（ID -> 名称），按类别取前 MAX_TYPES 个
TYPE_PRI = {
    'default': [('1', '形态描述'), ('152', '生境信息'), ('101', '生物学'), ('209', '国内分布')],
    '鸟类':    [('1', '形态描述'), ('152', '生境信息'), ('159', '鸣声描述'), ('209', '国内分布')],
    '鱼类':    [('1', '形态描述'), ('101', '生物学'), ('209', '国内分布'), ('152', '生境信息')],
}

BASE = 'http://zoology.especies.cn/api/v1'
KEY = ''
_lock = threading.Lock()      # 节流锁
_calls = [0]                  # 总调用次数
_done = [0]                   # 已处理物种数
SAVE_EVERY = 10


def load_key():
    if not os.path.exists(ENV):
        sys.exit('未找到 .env，请先写入 ZOOLOGY_API_KEY')
    for line in open(ENV, encoding='utf-8'):
        line = line.strip()
        if line.startswith('ZOOLOGY_API_KEY='):
            return line.split('=', 1)[1].strip()
    sys.exit('.env 中缺少 ZOOLOGY_API_KEY')


def post(endpoint, params, retries=4):
    """限速 + 指数退避重试的 POST 请求"""
    body = urllib.parse.urlencode(params).encode('utf-8')
    for attempt in range(retries):
        with _lock:
            wait = THROTTLE - (time.time() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
            _calls[0] += 1
        req = urllib.request.Request(BASE + '/' + endpoint, data=body,
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt + 2)
                continue
            return {'code': e.code, 'message': 'HTTP %d' % e.code}
        except Exception:
            time.sleep(2 ** attempt + 2)
            if attempt == retries - 1:
                return {'code': -1, 'message': 'network error'}
    return {'code': -1, 'message': 'retry exhausted'}


_last = [0.0]


def fetch_one(s):
    """处理单个物种，返回结果字符串"""
    sci = (s.get('scientific') or '').strip()
    if not sci:
        return '[%s] 无学名，跳过' % s['name']
    cat = s.get('category', '')
    dbs = DB_BY_CAT.get(cat, DB_FALLBACK)[:MAX_DB_TRIES]
    pri = TYPE_PRI.get(cat, TYPE_PRI['default'])

    # 1) 找数据库
    db = None
    types = []
    for d in dbs:
        r = post('descriptionType', {'scientificName': sci, 'dbaseName': d, 'apiKey': KEY})
        if r.get('code') == 200 and r.get('data', {}).get('desType'):
            db = d
            types = [(tid, tname) for t in r['data']['desType'] for tid, tname in t.items()]
            break
    if not db:
        return '[%s] 未命中' % s['name']

    # 2) 按优先级挑类型抓正文
    type_map = dict(types)
    picked = [(tid, type_map[tid]) for tid, _ in pri if tid in type_map][:MAX_TYPES] or types[:MAX_TYPES]
    items = {}
    for tid, tname in picked:
        r = post('description', {'scientificName': sci, 'dbaseName': db,
                                 'descriptionType': tid, 'apiKey': KEY})
        infos = (r.get('data') or {}).get('DescriptionInfo') or [] if r.get('code') == 200 else []
        if infos and infos[0].get('descontent', '').strip():
            items[tname] = {'content': infos[0]['descontent'], 'refs': infos[0].get('refs', [])}
    if items:
        s['fauna'] = {'dbase': db, 'items': items}
        return '[%s] 命中 %s (%d 类)' % (s['name'], db, len(items))
    return '[%s] 命中数据库但无正文' % s['name']


def save(data):
    tmp = DATA + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA)


def main():
    global KEY, WORKERS, THROTTLE
    KEY = load_key()
    if '--workers' in sys.argv:
        WORKERS = int(sys.argv[sys.argv.index('--workers') + 1])
    if '--throttle' in sys.argv:
        THROTTLE = float(sys.argv[sys.argv.index('--throttle') + 1])

    data = json.load(open(DATA, encoding='utf-8'))
    species = data['species']
    todo = [s for s in species if not s.get('fauna')]
    if '--limit' in sys.argv:
        todo = todo[:int(sys.argv[sys.argv.index('--limit') + 1])]
    print('共 %d 种，待抓 %d 种（workers=%d, throttle=%.2fs）'
          % (len(species), len(todo), WORKERS, THROTTLE), flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, s): s for s in todo}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                msg = fut.result()
            except Exception as e:
                msg = '[%s] 异常: %s' % (s['name'], e)
            with _lock:
                _done[0] += 1
                n = _done[0]
            print('[%d/%d] %s（累计调用 %d 次）' % (n, len(todo), msg, _calls[0]), flush=True)
            if n % SAVE_EVERY == 0:
                save(data)
            if _calls[0] >= HARD_CAP:
                print('!! 达到 %d 次调用安全上限，停止' % HARD_CAP, flush=True)
                ex.shutdown(cancel_futures=True)
                break

    save(data)
    n_fauna = sum(1 for s in species if s.get('fauna'))
    print('\n完成。fauna 覆盖率: %d / %d，累计调用 %d 次'
          % (n_fauna, len(species), _calls[0]), flush=True)


if __name__ == '__main__':
    main()
