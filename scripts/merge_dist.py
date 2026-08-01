#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并各 dist_*.json 分布文件 → data/species_master.json
合并优先级：dist_core.json（人工核验的核心省份）> 其他
同时校验名称必须存在于 species_raw.json，并清洗私有区字符。"""
import json
import glob
import os

RAW = 'data/species_raw.json'
OUT = 'data/species_master.json'
FIX_CHARS = {'\ue147': '鵟'}  # 名录解析产生的私有区字符修正

def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

raw = load(RAW)
# 清洗原始清单
for r in raw:
    r['name'] = ''.join(FIX_CHARS.get(c, c) for c in r['name'])
name2raw = {}
for r in raw:
    if r['name'] not in name2raw:
        name2raw[r['name']] = r

# 合并分布（core 优先）
order = ['data/dist_core.json'] + sorted(glob.glob('data/dist_*.json'))
prov_by_name = {}   # name -> 有序省份列表
src_by_name = {}    # name -> 来源文件

for f in order:
    if f == OUT or f.endswith('species_raw.json'):
        continue
    data = load(f)
    for item in data:
        name = ''.join(FIX_CHARS.get(c, c) for c in item['name'])
        provs = item.get('provinces', [])
        # 去重保序
        uniq = []
        for p in provs:
            if p not in uniq:
                uniq.append(p)
        if name in prov_by_name:
            if f == 'data/dist_core.json':
                prov_by_name[name] = uniq
                src_by_name[name] = f
            else:
                # 非 core 冲突：已有顺序（core 优先）在前，新省份补在后
                merged = prov_by_name[name] + [p for p in uniq if p not in prov_by_name[name]]
                prov_by_name[name] = merged
        else:
            prov_by_name[name] = uniq
            src_by_name[name] = f

# 校验并组装
bad = []
master = []
for name, provs in prov_by_name.items():
    if name not in name2raw:
        bad.append(name)
        continue
    r = name2raw[name]
    master.append({
        'name': r['name'],
        'level': r['level'],
        'category': r['category'],
        'provinces': provs,
    })

master.sort(key=lambda x: x['name'])
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(master, f, ensure_ascii=False, indent=1)

print('master 物种数:', len(master))
print('不在原始清单中的名称:', bad)
lv1 = sum(1 for m in master if m['level'] == '一级')
print('一级:', lv1, '二级:', len(master) - lv1)
from collections import Counter
print('类别:', dict(Counter(m['category'] for m in master)))
# 各省份物种数
prov_cnt = Counter()
for m in master:
    for p in m['provinces']:
        prov_cnt[p] += 1
print('省份物种数 top10:', prov_cnt.most_common(10))
