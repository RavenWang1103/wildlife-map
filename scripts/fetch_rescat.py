#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从生态环境部《全国自然保护区名录》PDF 中提取官方「类型」字段，生成 data/rescat.json。

数据来源：
  《全国自然保护区名录》（生态环境部，2019-07 发布，由 Excel 导出，130 页）
  https://www.mee.gov.cn/ywgz/zrstbh/zrbhdjg/201908/P020190807403320559094.pdf
  列为：序号 / 保护区名称 / 行政区域 / 面积 / 主要保护对象 / 类型 / 级别 / 始建时间 / 主管部门

为什么要这份数据：
  维基《中华人民共和国国家级自然保护区列表》只有保护区名字，没有「类型」字段，
  因此主脚本只能拿名字去正则猜类型（infer_cat），导致大批保护区落进 other。
  本表里的「类型」是 GB/T 14529-1993 口径的官方标签，可直接替代名称猜测。

PDF 结构（实测）：
  文本被拆成片段，同一行的「序号锚点」(如 京/01) 带真实坐标，
  其余单元格的文本矩阵多为 (0,0)，按固定顺序紧跟锚点之后。
  因此用「锚点 + 按行取字段」的方式还原表格，比按字符位置切列更稳。

输出 data/rescat.json（含全部级别，主脚本按省份 + 名称查表时命中率更高）：
  {"generated": ..., "source": ..., "total": N,
   "reserves": [{"seq": "京01", "prov": "北京市", "name": "百花山",
                 "region": "北京市门头沟区", "area": 21743, "object": "温带次生林",
                 "type": "森林生态", "level": "国家级",
                 "since": "19850401", "dept": "林业"}, ...]}

用法：
  python3 scripts/fetch_rescat.py   # 缺 PDF 时自动下载，解析后写 data/rescat.json

依赖：pypdf —— 仅本脚本需要。产物 data/rescat.json 已纳入版本管理，
      因此日常跑主脚本无需安装 pypdf。
"""
import datetime
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'rescat.json')
CACHE = os.path.join(ROOT, 'scripts', '.reserves_cache')
PDF = os.path.join(CACHE, 'mee_reserves.pdf')

PDF_URL = ('https://www.mee.gov.cn/ywgz/zrstbh/zrbhdjg/201908/'
           'P020190807403320559094.pdf')

# GB/T 14529-1993 的 9 个类型
TYPES = ('森林生态', '草原草甸', '荒漠生态', '内陆湿地', '海洋海岸',
         '野生植物', '野生动物', '地质遗迹', '古生物遗迹')
LEVELS = ('国家级', '省级', '市级', '县级')

# 序号前缀（省级行政区简称）-> 地图使用的简体全称
# 名录里贵州写作「黔」、云南写作「滇」，与常见简称「贵」「云」不同，勿写错
PROV_BY_CHAR = {
    '京': '北京市', '津': '天津市', '冀': '河北省', '晋': '山西省',
    '蒙': '内蒙古自治区', '辽': '辽宁省', '吉': '吉林省', '黑': '黑龙江省',
    '沪': '上海市', '苏': '江苏省', '浙': '浙江省', '皖': '安徽省',
    '闽': '福建省', '赣': '江西省', '鲁': '山东省', '豫': '河南省',
    '鄂': '湖北省', '湘': '湖南省', '粤': '广东省', '桂': '广西壮族自治区',
    '琼': '海南省', '渝': '重庆市', '川': '四川省', '黔': '贵州省',
    '滇': '云南省', '藏': '西藏自治区', '陕': '陕西省', '甘': '甘肃省',
    '青': '青海省', '宁': '宁夏回族自治区', '新': '新疆维吾尔自治区',
}

# 每页重复出现的表头文字，需从字段流里排除
HEADER = {'保护区名称', '行政区域', '面积', '主要保护对象', '类型', '级别',
          '始建时间', '主管部门', '序号', '全国自然保护区名录'}

SEQ_RE = re.compile(r'^\d{2,3}$')


def download():
    """下载名录 PDF 到缓存目录（已存在则跳过）。"""
    if os.path.exists(PDF) and os.path.getsize(PDF) > 100000:
        return
    os.makedirs(CACHE, exist_ok=True)
    print('下载名录 PDF ...')
    req = urllib.request.Request(PDF_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(PDF, 'wb') as f:
        f.write(r.read())
    print('  已保存 %s (%d KB)' % (PDF, os.path.getsize(PDF) // 1024))


def page_fragments(page):
    """提取单页的文本片段，保留文本矩阵以区分单元格与页面装饰文字。"""
    out = []

    def visit(text, cm, tm, font_dict, font_size):
        if text and text.strip():
            out.append((round(tm[4], 1), round(tm[5], 1), text.strip()))

    page.extract_text(visitor_text=visit)
    return out


def page_rows(frags):
    """把单页片段还原成若干行字段列表。"""
    anchors = [i for i in range(len(frags) - 1)
               if frags[i][2] in PROV_BY_CHAR and SEQ_RE.match(frags[i + 1][2])]
    rows = []
    for k, start in enumerate(anchors):
        end = anchors[k + 1] if k + 1 < len(anchors) else len(frags)
        seq = frags[start][2] + frags[start + 1][2]
        # 同一行的单元格，其文本矩阵或为 (0,0)，或带真实坐标但 y 与序号行齐平；
        # 页眉(序号那一行)/页脚等装饰文字的 y 与任何数据行都不重合，借此排除
        row_y = frags[start][1]
        cells = [t for x, y, t in frags[start + 2:end]
                 if t not in HEADER and (y == 0.0 or abs(y - row_y) < 2.0)]
        rows.append((seq, cells))
    return rows


def parse_pdf():
    """遍历 PDF 还原全部行，返回全部级别的记录。"""
    from pypdf import PdfReader

    reader = PdfReader(PDF)
    records, skipped = [], 0
    for page in reader.pages:
        for seq, cells in page_rows(page_fragments(page)):
            prov = PROV_BY_CHAR[seq[0]]
            # 类型与级别相邻出现，用它定位字段边界；正常应落在第 5、6 个字段
            ti = next((i for i in range(len(cells) - 1)
                       if cells[i] in TYPES and cells[i + 1] in LEVELS), None)
            if ti is None or len(cells) < 2:
                skipped += 1
                continue
            records.append({
                'seq': seq,
                'prov': prov,
                'name': cells[0],
                'region': cells[1],
                'area': cells[2] if ti >= 3 else None,
                'object': cells[3] if ti >= 4 else None,
                'type': cells[ti],
                'level': cells[ti + 1],
                'since': cells[ti + 2] if len(cells) > ti + 2 else None,
                'dept': cells[ti + 3] if len(cells) > ti + 3 else None,
            })
    return records, skipped


def main():
    download()
    records, skipped = parse_pdf()
    if not records:
        raise SystemExit('未解析出任何记录，PDF 结构可能已变化')

    by_type = {}
    for r in records:
        by_type[r['type']] = by_type.get(r['type'], 0) + 1

    OUT_DIR = os.path.dirname(OUT)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({
            'generated': datetime.datetime.now().strftime('%Y-%m-%d'),
            'source': PDF_URL,
            'total': len(records),
            'reserves': records,
        }, f, ensure_ascii=False, indent=1)

    print('解析 %d 条（跳过无法定位类型的 %d 行）' % (len(records), skipped))
    for t in TYPES:
        if by_type.get(t):
            print('  %-6s %4d' % (t, by_type[t]))
    print('写出 %s (%d KB)' % (OUT, os.path.getsize(OUT) // 1024))


if __name__ == '__main__':
    main()
