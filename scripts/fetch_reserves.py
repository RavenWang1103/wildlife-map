#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取中国国家级自然保护区名录与经纬度，生成 data/reserves.json。

数据来源（多源合并，按精度优先级取第一个命中的坐标）：
  1. 中文维基《中华人民共和国国家级自然保护区列表》raw wikitext —— 名录 469 条
  2. 中文维基 prop=coordinates                                  —— 坐标
  3. Wikidata P625（经 pageprops 拿 QID 后 wbgetentities）        —— 坐标
  4. OSM Overpass（boundary=protected_area / leisure=nature_reserve / protect_class）
  5. 高德地图 Web 服务 POI 关键字搜索（需环境变量 AMAP_KEY）        —— 坐标补齐

用法：
  AMAP_KEY=你的key python3 scripts/fetch_reserves.py
无 AMAP_KEY 时自动跳过第 5 步，仅用前 4 个源（覆盖率约 38%）。

注意：高德返回 GCJ-02 坐标，与地图底图存在数百米级偏移；
在省级比例尺下该偏移不可见，故不做坐标纠偏。
"""
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'reserves.json')
CACHE = os.path.join(ROOT, 'scripts', '.reserves_cache')

MINGLU_TITLE = '中华人民共和国国家级自然保护区列表'
UA = {'User-Agent': 'WildlifeMapDemo/1.0 (educational project; contact: example@example.com)'}

S = requests.Session()
S.headers.update(UA)

# 省级行政区 -> 高德 adcode
PROV_ADCODE = {
    '北京': '110000', '天津': '120000', '河北': '130000', '山西': '140000',
    '内蒙古': '150000', '辽宁': '210000', '吉林': '220000', '黑龙江': '230000',
    '上海': '310000', '江苏': '320000', '浙江': '330000', '安徽': '340000',
    '福建': '350000', '江西': '360000', '山东': '370000', '河南': '410000',
    '湖北': '420000', '湖南': '430000', '广东': '440000', '广西': '450000',
    '海南': '460000', '重庆': '500000', '四川': '510000', '贵州': '520000',
    '云南': '530000', '西藏': '540000', '陕西': '610000', '甘肃': '620000',
    '青海': '630000', '宁夏': '640000', '新疆': '650000', '台湾': '710000',
    '香港': '810000', '澳门': '820000',
}

# 简称 -> 地图 feature name / PROV_I18N 使用的简体全称
PROV_CANON = {
    '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
    '河北': '河北省', '山西': '山西省', '辽宁': '辽宁省', '吉林': '吉林省',
    '黑龙江': '黑龙江省', '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省',
    '福建': '福建省', '江西': '江西省', '山东': '山东省', '河南': '河南省',
    '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '海南': '海南省',
    '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '陕西': '陕西省',
    '甘肃': '甘肃省', '青海': '青海省', '台湾': '台湾省',
    '内蒙古': '内蒙古自治区', '广西': '广西壮族自治区', '西藏': '西藏自治区',
    '宁夏': '宁夏回族自治区', '新疆': '新疆维吾尔自治区',
    '香港': '香港特别行政区', '澳门': '澳门特别行政区',
}

# 维基百科繁简混用，统一成简体省份名
T2S = str.maketrans({
    '區': '区', '壯': '壮', '維': '维', '爾': '尔', '寧': '宁', '龍': '龙',
    '遼': '辽', '蘇': '苏', '貴': '贵', '雲': '云', '陝': '陕', '肅': '肃',
    '臺': '台', '門': '门', '廣': '广', '東': '东', '內': '内', '蒙': '蒙',
    '古': '古', '藏': '藏', '特': '特', '別': '别', '政': '政', '治': '治',
})

# 保护区类型推断规则（按顺序匹配，先命中者生效）
CAT_RULES = [
    ('geology', r'地质|化石|遗迹|剖面|冰川|火山|丹霞|地貌|古生物|陨石|洞穴|岩溶|喀斯特'),
    ('marine', r'海洋|海域|海岛|海湾|海岸|岛礁|珊瑚|红树林|海龟|斑海豹|儒艮|文昌鱼|贝壳堤|牡蛎'),
    ('wetland', r'湿地|沼泽|湖泊|湖水|泡|沼|滩涂|河口|三角洲|天鹅|鹤|鹳|鹮|鸥|雁|鸭|鹭|鸻|鹬'),
    ('grassland', r'草原|草甸|荒漠|戈壁|沙地|胡杨|梭梭|桫椤?草'),
    ('plant', r'植物|树木|原始林|森林|林区|松林|杉|桦|栎|楠|樟|红豆杉|水杉|银杉|桫椤|苏铁|木兰|杜鹃|竹'),
    ('wildlife', r'野生动物|猕猴|猴|豹|虎|鹿|羚|麝|獐|貂|猫|熊|熊猫|象|牛|马|驴|驼|羊|兔|鼠|鲵|鲟|鲤|鱼|蛙|蛇|蜥|龟|鳖|蝶|蝶类|蜂虎|雉|鹀|莺|画眉|长臂猿|穿山甲|野驴|野马'),
    ('forest', r'林'),
]

PROV_PREFIX = re.compile(
    r'^(中华人民共和国|中国|北京市|天津市|上海市|重庆市|河北省|山西省|辽宁省|吉林省|'
    r'黑龙江省|江苏省|浙江省|安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|'
    r'海南省|四川省|贵州省|云南省|陕西省|甘肃省|青海省|内蒙古自治区|广西壮族自治区|'
    r'西藏自治区|宁夏回族自治区|新疆维吾尔自治区|台湾省|香港特别行政区|澳门特别行政区|'
    r'北京|天津|上海|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|'
    r'河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|内蒙古|广西|西藏|宁夏|新疆)'
)
LEVEL_RE = re.compile(r'(国家级|省级|市级|县级)')
SUFFIX_RE = re.compile(r'(自然保护区|保护区|保护地)$')


# ---------------------------------------------------------------- 工具

def core_name(name):
    """取保护区核心地名：去省市前缀、去级别与类型后缀。"""
    s = PROV_PREFIX.sub('', name.strip())
    s = LEVEL_RE.sub('', s)
    s = SUFFIX_RE.sub('', s)
    return re.sub(r'[\s·・]', '', s)


def norm_prov(prov):
    """省份名繁转简并去掉行政后缀，用于查 adcode。"""
    p = prov.translate(T2S)
    for suf in ('维吾尔自治区', '回族自治区', '壮族自治区', '自治区',
                '特别行政区', '省', '市'):
        if p.endswith(suf):
            p = p[: -len(suf)]
            break
    return p


def prov_full(prov):
    """归一到地图 feature name / PROV_I18N 使用的简体全称（如 内蒙古自治区）。"""
    return PROV_CANON.get(norm_prov(prov), prov.translate(T2S).strip())


def clean_text(s):
    """清理 wikitext 残留：-{A|鱀}-、[[a|b]]、'''粗体'''、<ref> 等。"""
    s = re.sub(r'-\{(?:[^{}|]*\|)?([^{}|]*)\}-', r'\1', s)
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'<ref[^>]*>.*?</ref>|<ref[^>]*/>', '', s, flags=re.S)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r"'{2,}", '', s)
    return s.strip()


def infer_cat(name):
    for cat, pat in CAT_RULES:
        if re.search(pat, name):
            return cat
    return 'other'


def cached(name, producer):
    """带磁盘缓存的取数，避免重复请求。"""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + '.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    data = producer()
    if data is not None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    return data


def api_json(url, params, retries=4, mode='get', headers=None):
    """带指数退避的 JSON 请求，容忍 429/5xx 与非 JSON 响应。"""
    delay = 2.0
    for attempt in range(retries):
        try:
            if mode == 'get':
                r = S.get(url, params=params, timeout=40, headers=headers)
            else:
                r = S.post(url, data=params, timeout=200, headers=headers)
            if r.status_code == 200 and r.text.lstrip().startswith('{'):
                return r.json()
            print(f'    ! HTTP {r.status_code} (第 {attempt + 1} 次)', file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f'    ! {type(e).__name__}: {e}', file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    return None


# ---------------------------------------------------------------- 1. 名录

def _produce_minglu():
    url = 'https://zh.wikipedia.org/w/index.php'
    r = S.get(url, params={'title': MINGLU_TITLE, 'action': 'raw'}, timeout=60)
    r.raise_for_status()
    return {'wikitext': r.text}


def parse_minglu(text):
    """解析名录 wikitext：`*[[省]]` 切省，`**[[条目|显示名]]` 取保护区。"""
    region = province = None
    items, seen = [], set()
    for line in text.split('\n'):
        m = re.match(r'^==+\s*(.+?)\s*==+\s*$', line)
        if m:
            region, province = m.group(1), None
            continue
        m = re.match(r'^\*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*$', line)
        if m:
            province = m.group(2) or m.group(1)
            continue
        m = re.match(r'^\*\*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', line)
        if m and province:
            title = m.group(1)
            if title in seen:
                continue
            seen.add(title)
            items.append({
                'title': title,
                'name': clean_text(m.group(2) or title),
                'prov': province,
                'region': region,
            })
    return items


# ---------------------------------------------------------------- 2. 中文维基坐标

def _produce_wiki_coords(titles):
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = api_json('https://zh.wikipedia.org/w/api.php', {
            'action': 'query', 'prop': 'coordinates', 'redirects': 1,
            'titles': '|'.join(chunk), 'format': 'json', 'formatversion': 2,
        })
        if d:
            q = d.get('query', {})
            alias = {x['to']: x['from'] for x in (q.get('redirects') or [])}
            alias.update({x['to']: x['from'] for x in (q.get('normalized') or [])})
            for page in q.get('pages') or []:
                coords = page.get('coordinates')
                if not coords:
                    continue
                lat, lon = coords[0]['lat'], coords[0]['lon']
                for key in (page.get('title'), alias.get(page.get('title'))):
                    if key:
                        out[key] = [lat, lon]
        print(f'  维基坐标 {min(i + 50, len(titles))}/{len(titles)} -> {len(out)}')
        time.sleep(1.2)
    return out


# ---------------------------------------------------------------- 3. Wikidata

def _produce_qids(titles):
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = api_json('https://zh.wikipedia.org/w/api.php', {
            'action': 'query', 'prop': 'pageprops', 'ppprop': 'wikibase_item',
            'redirects': 1, 'titles': '|'.join(chunk),
            'format': 'json', 'formatversion': 2,
        })
        if d:
            q = d.get('query', {})
            alias = {x['to']: x['from'] for x in (q.get('redirects') or [])}
            alias.update({x['to']: x['from'] for x in (q.get('normalized') or [])})
            for page in q.get('pages') or []:
                qid = (page.get('pageprops') or {}).get('wikibase_item')
                if not qid:
                    continue
                for key in (page.get('title'), alias.get(page.get('title'))):
                    if key:
                        out[key] = qid
        print(f'  QID {min(i + 50, len(titles))}/{len(titles)} -> {len(out)}')
        time.sleep(1.2)
    return out


def _produce_wd_coords(qids):
    out = {}
    ids = sorted(set(qids.values()))
    for i in range(0, len(ids), 45):
        chunk = ids[i:i + 45]
        d = api_json('https://www.wikidata.org/w/api.php', {
            'action': 'wbgetentities', 'ids': '|'.join(chunk),
            'props': 'claims', 'format': 'json',
        })
        if d:
            for qid, ent in (d.get('entities') or {}).items():
                claims = (ent.get('claims') or {}).get('P625')
                if not claims:
                    continue
                try:
                    v = claims[0]['mainsnak']['datavalue']['value']
                    out[qid] = [v['latitude'], v['longitude']]
                except (KeyError, IndexError, TypeError):
                    continue
        print(f'  Wikidata 坐标 {min(i + 45, len(ids))}/{len(ids)} -> {len(out)}')
        time.sleep(1.5)
    return out


# ---------------------------------------------------------------- 4. OSM

OVERPASS_ENDPOINTS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]
# 注意：overpass-api.de 在部分网络下 SSL 被阻断；nwr 全量查询会被镜像网关 504，
# 故只取带名称的 protected_area 关系（实测可稳定返回）。
OSM_HEADERS = {'User-Agent': 'WildlifeMap/1.0 (educational student project)'}
OSM_QUERY = """
[out:json][timeout:120];
area["ISO3166-1"="CN"][admin_level=2]->.cn;
(
  rel["boundary"="protected_area"]["name"](area.cn);
  rel["leisure"="nature_reserve"]["name"](area.cn);
);
out center tags;
"""


def _produce_osm():
    d = None
    for url in OVERPASS_ENDPOINTS:
        print(f'  Overpass 尝试 {url}')
        d = api_json(url, {'data': OSM_QUERY}, retries=1, mode='post',
                     headers=OSM_HEADERS)
        if d:
            break
    if not d:
        return None
    out = {}
    for el in d.get('elements', []):
        tags = el.get('tags') or {}
        name = tags.get('name') or tags.get('name:zh')
        if not name:
            continue
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if lat is None or lon is None:
            continue
        out.setdefault(core_name(name), [lat, lon])
    print(f'  OSM 归一化地物 {len(out)}')
    return out


# ---------------------------------------------------------------- 5. 高德

AMAP_TEXT = 'https://restapi.amap.com/v3/place/text'


def _amap_search(key, keyword, adcode):
    d = api_json(AMAP_TEXT, {
        'key': key, 'keywords': keyword, 'city': adcode, 'citylimit': 'true',
        'offset': 10, 'page': 1, 'extensions': 'base',
    }, retries=3)
    if not d or d.get('status') != '1':
        info = (d or {}).get('info', 'unknown')
        if info in ('INVALID_USER_KEY', 'USERKEY_PLAT_NOMATCH', 'INVALID_USER_SCODE'):
            raise SystemExit(f'高德 Key 无效或平台类型不符（{info}），请确认选的是「Web服务」Key')
        if info == 'DAILY_QUERY_OVER_LIMIT':
            raise SystemExit('高德 Key 今日配额已用尽，请明天再跑或换 Key')
        return None
    return d.get('pois') or []


def _poi_ok(core, poi_name):
    """校验 POI 名称与保护区核心地名是否互含。"""
    a = re.sub(r'[\s·・()（）\-—－]', '', core)
    b = re.sub(r'[\s·・()（）\-—－]', '', poi_name)
    if not a or not b:
        return False
    return a in b or b in a


def _produce_amap(items, key, need_titles):
    """对仍未命中坐标的条目逐个走高德 POI 搜索。"""
    out = {}
    todo = [it for it in items if it['title'] in need_titles]
    print(f'  高德待补 {len(todo)} 条')
    for idx, it in enumerate(todo, 1):
        core = core_name(it['name']) or core_name(it['title'])
        adcode = PROV_ADCODE.get(norm_prov(it['prov']))
        if not core or not adcode:
            continue
        for keyword in (core, core + '自然保护区', it['name']):
            pois = _amap_search(key, keyword, adcode)
            hit = None
            for poi in pois:
                loc = (poi.get('location') or '').split(',')
                if len(loc) != 2:
                    continue
                if _poi_ok(core, poi.get('name') or ''):
                    hit = {
                        'lat': float(loc[1]), 'lon': float(loc[0]),
                        'poi': poi.get('name'), 'addr': poi.get('adname') or '',
                    }
                    break
            if hit:
                out[it['title']] = hit
                break
        if idx % 20 == 0:
            print(f'  高德 {idx}/{len(todo)} -> 命中 {len(out)}')
        time.sleep(0.15)
    print(f'  高德命中 {len(out)}/{len(todo)}')
    return out


# ---------------------------------------------------------------- 主流程

def main():
    key = os.environ.get('AMAP_KEY', '').strip()
    if not key:
        env_file = os.path.join(ROOT, '.env')
        if os.path.exists(env_file):
            for line in open(env_file, encoding='utf-8'):
                if line.strip().startswith('AMAP_KEY'):
                    key = line.split('=', 1)[1].strip().strip('"\'')
                    break

    raw = cached('minglu', _produce_minglu)
    items = parse_minglu(raw['wikitext'])
    print(f'名录：{len(items)} 条，{len(set(i["prov"] for i in items))} 个省级行政区')

    titles = [it['title'] for it in items]

    wiki = cached('wiki_coords', lambda: _produce_wiki_coords(titles)) or {}
    qids = cached('wd_qids', lambda: _produce_qids(titles)) or {}
    wd_coords = cached('wd_coords', lambda: _produce_wd_coords(qids)) or {}
    osm = cached('osm', _produce_osm) or {}

    wd = {t: wd_coords[q] for t, q in qids.items() if q in wd_coords}

    # 合并：维基 > Wikidata > OSM
    merged = {}
    for it in items:
        t = it['title']
        if t in wiki:
            merged[t] = (wiki[t], 'wiki')
        elif t in wd:
            merged[t] = (wd[t], 'wikidata')
        elif core_name(t) in osm:
            merged[t] = (osm[core_name(t)], 'osm')
    print(f'免费源合并：{len(merged)}/{len(items)} = {len(merged) / len(items) * 100:.1f}%')

    if key:
        need = {it['title'] for it in items} - set(merged)
        amap = cached('amap', lambda: _produce_amap(items, key, need)) or {}
        for t, v in amap.items():
            if t not in merged:
                merged[t] = ([v['lat'], v['lon']], 'amap')
        print(f'高德补齐后：{len(merged)}/{len(items)} = {len(merged) / len(items) * 100:.1f}%')
    else:
        print('未提供 AMAP_KEY，跳过高德补齐（可用 AMAP_KEY=xxx 重跑）')

    reserves = []
    for it in items:
        coord, src = merged.get(it['title'], (None, None))
        rec = {
            'title': it['title'],
            'name': it['name'],
            'short': core_name(it['name']) or it['name'],
            'prov': prov_full(it['prov']),
            'region': it['region'],
            'cat': infer_cat(it['name']),
            'lat': round(coord[0], 5) if coord else None,
            'lon': round(coord[1], 5) if coord else None,
            'src': src,
        }
        reserves.append(rec)

    with_coord = sum(1 for r in reserves if r['lat'] is not None)
    payload = {
        'generated': time.strftime('%Y-%m-%d'),
        'source': {
            'minglu': '中文维基百科《中华人民共和国国家级自然保护区列表》',
            'coord': '中文维基 coordinates / Wikidata P625 / OSM Overpass / 高德地图 POI 搜索',
        },
        'total': len(reserves),
        'with_coord': with_coord,
        'reserves': reserves,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, OUT)
    print(f'已写出 {OUT}：{len(reserves)} 条，其中 {with_coord} 条带坐标 '
          f'（{with_coord / len(reserves) * 100:.1f}%）')

    by_src = {}
    for r in reserves:
        by_src[r['src']] = by_src.get(r['src'], 0) + 1
    print('坐标来源分布:', by_src)


if __name__ == '__main__':
    main()
