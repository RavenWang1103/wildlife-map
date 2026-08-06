#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拆分 animals.json → 主数据(精简) + 详情数据(懒加载)。

主数据保留：name, level, category, provinces, desc_zhs, image, wiki, 等基本信息
详情数据保留：desc_zht, desc_en, fauna（按需加载）
"""
import json
import os
import sys

SRC = 'data/animals.json'
MAIN = 'data/animals.json'    # 覆盖原文件
DETAIL = 'data/animals_detail.json'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

with open(SRC, encoding='utf-8') as f:
    data = json.load(f)

species = data['species']
main_species = []
detail_map = {}

for s in species:
    main_species.append({
        'name': s['name'],
        'level': s['level'],
        'category': s['category'],
        'provinces': s['provinces'],
        'desc_zhs': s.get('desc_zhs', ''),
        'image': s.get('image', ''),
        'wiki': s.get('wiki', ''),
        'wiki_title': s.get('wiki_title', ''),
        'qid': s.get('qid', ''),
        'en_name': s.get('en_name', ''),
        'scientific': s.get('scientific', ''),
        'iucn': s.get('iucn', ''),
        'iucn_cn': s.get('iucn_cn', ''),
    })
    detail_map[s['name']] = {
        'desc_zht': s.get('desc_zht', ''),
        'desc_en': s.get('desc_en', ''),
        'fauna': s.get('fauna'),
    }

with open(MAIN, 'w', encoding='utf-8') as f:
    json.dump({'species': main_species}, f, ensure_ascii=False, indent=1)

with open(DETAIL, 'w', encoding='utf-8') as f:
    json.dump(detail_map, f, ensure_ascii=False, indent=1)

main_size = os.path.getsize(MAIN) / 1024
detail_size = os.path.getsize(DETAIL) / 1024
print(f'主数据: {len(main_species)} 个物种, {main_size:.1f} KB')
print(f'详情数据: {len(detail_map)} 个条目, {detail_size:.1f} KB')
print(f'缩减: {main_size + detail_size:.1f} KB (原 {main_size + detail_size + 50:.1f} KB)')