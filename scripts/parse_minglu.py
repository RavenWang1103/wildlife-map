#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 2021 版《国家重点保护野生动物名录》HTML 表格，输出 data/species_raw.json"""
import re
import json
import html as htmlmod

SRC = '/tmp/minglu.html'
OUT = 'data/species_raw.json'

html_text = open(SRC, encoding='utf-8', errors='ignore').read()
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.S)

CLASS_MAP = {
    '哺乳纲': '哺乳动物', '鸟纲': '鸟类', '爬行纲': '爬行动物',
    '两栖纲': '两栖动物', '软骨鱼纲': '鱼类', '硬骨鱼纲': '鱼类',
    '肉鳍鱼纲': '鱼类', '圆口纲': '鱼类', '文昌鱼纲': '其他无脊椎动物',
    '肠鳃纲': '其他无脊椎动物', '昆虫纲': '昆虫', '蛛形纲': '节肢动物',
    '肢口纲': '节肢动物', '软甲纲': '节肢动物', '双壳纲': '软体动物',
    '头足纲': '软体动物', '腹足纲': '软体动物', '珊瑚纲': '其他无脊椎动物',
    '水螅纲': '其他无脊椎动物',
}

def clean(s):
    s = htmlmod.unescape(s)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('\u3000', '').replace('\xa0', ' ').strip()
    return s

records = []
current_class = None

for row in rows:
    tds = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)]
    joined = [t for t in tds if t]
    if not joined:
        continue
    first = joined[0]

    # 1) 纲 标题行 → 切换当前类别
    m = re.match(r'^([\u4e00-\u9fff·]{1,6})纲', first)
    if m and m.group(1) + '纲' in first:
        cls_name = m.group(1) + '纲'
        for k, v in CLASS_MAP.items():
            if cls_name in k:
                current_class = v
                break
        else:
            current_class = '其他'
        continue

    # 2) 提取级别（一级/二级），没有则跳过（目/科标题行）
    level = ''
    for t in joined[1:]:
        if t in ('一级', '二级'):
            level = t
            break
    if not level:
        continue

    # 3) 物种行：首格为中文名（可能带 * 前缀），其余格为备注
    name = first.lstrip('*· ').strip()
    if not name:
        continue
    remark = ' '.join(t for t in joined[1:] if t not in ('一级', '二级')).strip()
    records.append({
        'name': name,
        'level': level,
        'category': current_class or '未知',
        'remark': remark,
    })

# 去重（保留首个）
seen = {}
uniq = []
for r in records:
    if r['name'] not in seen:
        seen[r['name']] = True
        uniq.append(r)

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(uniq, f, ensure_ascii=False, indent=1)

lv1 = sum(1 for r in uniq if r['level'] == '一级')
lv2 = sum(1 for r in uniq if r['level'] == '二级')
from collections import Counter
print('总数:', len(uniq), '一级:', lv1, '二级:', lv2)
print('类别分布:', dict(Counter(r['category'] for r in uniq)))
print('样例:', json.dumps(uniq[:6], ensure_ascii=False))
