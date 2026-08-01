#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Wikidata 批量抓取物种的：学名(P225)、英文名(en label)、IUCN 保护等级(P141)。
流程：
  1) 读 data/animals.json，收集各物种的 wiki_title
  2) 批量用 MediaWiki API 把 title 映射为 Wikidata QID
  3) 批量用 wbgetentities 获取 labels + claims
  4) 写回 data/animals.json（scientific / en_name / iucn / qid）
支持断点续跑（已有 qid 且已抓成功的跳过）。
"""
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error

DATA = 'data/animals.json'
UA = {'User-Agent': 'WildlifeMapDemo/1.0 (educational project)'}
THROTTLE = 1.0  # 秒，避免 429

_last = [0.0]
def get(url, retries=5):
    """限速 + 指数退避重试"""
    for attempt in range(retries):
        wait = _last[0] + THROTTLE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt + 2)
                continue
            raise
        except Exception:
            time.sleep(2 ** attempt + 2)
            if attempt == retries - 1:
                raise
    return None

# P141 取值 -> (代码, 中文)
IUCN_MAP = {
    'Q28068568': ('CR', '极危'),
    'Q278113': ('EN', '濒危'),
    'Q11394': ('VU', '易危'),
    'Q719675': ('NT', '近危'),
    'Q211005': ('LC', '无危'),
    'Q11399': ('DD', '数据缺乏'),
    'Q28021314': ('NE', '未评估'),
}

def chunked(lst, n=50):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def main():
    data = json.load(open(DATA, encoding='utf-8'))
    species = data['species']
    by_name = {s['name']: s for s in species}

    # 1) 需要补 QID 的物种（按其 wiki_title）
    need = [s for s in species if not s.get('qid') and s.get('wiki_title')]
    print('待映射 QID:', len(need))

    for batch in chunked(need):
        titles = '|'.join(urllib.parse.quote(t) for t in [s['wiki_title'] for s in batch])
        url = ('https://zh.wikipedia.org/w/api.php?action=query&prop=pageprops'
               '&ppprop=wikibase_item&titles=%s&format=json&utf8=1&formatversion=2') % titles
        try:
            d = get(url)
            pages = d.get('query', {}).get('pages', [])
            for pg in pages:
                qid = pg.get('pageprops', {}).get('wikibase_item')
                title = pg.get('title')
                if qid and title:
                    for s in batch:
                        if s['wiki_title'] == title:
                            s['qid'] = qid
        except Exception as e:
            print('QID 批次失败:', e)
        time.sleep(0.2)

    # 2) 批量抓 entities（labels + P225 + P141）
    need_q = [s for s in species if s.get('qid') and not (s.get('scientific') or s.get('iucn'))]
    print('待抓 Wikidata 详情:', len(need_q))

    for batch in chunked(need_q, 50):
        ids = '|'.join(s['qid'] for s in batch)
        url = ('https://www.wikidata.org/w/api.php?action=wbgetentities'
               '&ids=%s&props=labels|claims&languages=zh|en&format=json&utf8=1') % ids
        try:
            d = get(url)
            ents = d.get('entities', {})
            for s in batch:
                e = ents.get(s['qid'], {})
                labels = e.get('labels', {})
                s['en_name'] = (labels.get('en') or {}).get('value', '')
                claims = e.get('claims', {})
                # 学名 P225
                p225 = claims.get('P225')
                if p225 and p225[0].get('mainsnak', {}).get('datavalue'):
                    s['scientific'] = p225[0]['mainsnak']['datavalue']['value']
                # IUCN P141
                p141 = claims.get('P141')
                if p141:
                    for st in p141:
                        dv = st.get('mainsnak', {}).get('datavalue')
                        if dv and dv.get('value', {}).get('id') in IUCN_MAP:
                            code, cn = IUCN_MAP[dv['value']['id']]
                            s['iucn'] = code
                            s['iucn_cn'] = cn
                            break
        except Exception as e:
            print('entities 批次失败:', e)
        time.sleep(0.2)

    # 3) 写回
    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    has_sci = sum(1 for s in species if s.get('scientific'))
    has_en = sum(1 for s in species if s.get('en_name'))
    has_iucn = sum(1 for s in species if s.get('iucn'))
    print('完成。学名:', has_sci, '/ 英文名:', has_en, '/ IUCN:', has_iucn)

    # 抽样展示
    from collections import Counter
    print('IUCN 分布:', dict(Counter(s.get('iucn') for s in species if s.get('iucn'))))
    for s in species:
        if s['name'] == '大熊猫':
            print('大熊猫:', {k: s.get(k) for k in ('scientific', 'en_name', 'iucn', 'iucn_cn', 'qid')})
            break

if __name__ == '__main__':
    main()
