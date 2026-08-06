/* ==================== 全局状态 ==================== */
const GEO_URL = 'data/100000_full.json';
const DATA_URL = 'data/animals.json';
const DETAIL_URL = 'data/animals_detail.json';
const DEFAULT_PROVINCE = '四川省';
const DISPLAY = { '虎': '东北虎', '藏羚': '藏羚羊' };
const CATEGORIES = ['哺乳动物', '鸟类', '爬行动物', '两栖动物', '鱼类', '昆虫', '软体动物', '节肢动物', '其他无脊椎动物'];
const CAT_COLORS = ['#2d6a4f', '#40916c', '#74a57f', '#a8c3a0', '#d4a373', '#bc6c25', '#8a9a5b', '#c9ada7', '#8a8175'];
const IUCN_CLS = {
  CR: 'bg-[#b91c1c] text-white', EN: 'bg-[#d97706] text-white',
  VU: 'bg-[#b45309] text-white', NT: 'bg-[#8a9a5b] text-white',
  LC: 'bg-[#4b7a5c] text-white', DD: 'bg-[#a3a396] text-white', NE: 'bg-[#a3a396] text-white',
};

let species = [], byProvince = {}, countByProvince = {}, riskCount = {}, geo = null;
let currentProvince = DEFAULT_PROVINCE, levelFilter = '全部';
let chart = null, provPieChart = null, rankChart = null, catChart = null, highlightSpecies = null;
let mapMode = 'count';
let compareList = [];
let currentTab = 'list';
let LANG = localStorage.getItem('wm-lang') || 'zhs';
let openDetailName = null;
let detailData = null;   // 懒加载缓存
let detailPromise = null; // 避免重复请求
let labelShow = true;
let resizeTimer = null;

const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ====== HTML 安全转义（防止 XSS） ====== */
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

/* ====== 工具函数 ====== */
const displayName = n => DISPLAY[n] || n;
const byName = {};
const findSpecies = n => byName[n] || null;

/* ====== 带超时的 fetch ====== */
function fetchWithTimeout(url, ms = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { signal: ctrl.signal }).then(r => {
    clearTimeout(timer);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).catch(e => {
    clearTimeout(timer);
    throw e;
  });
}

/* ====== 懒加载详情数据 ====== */
function loadDetailData() {
  if (detailData) return Promise.resolve(detailData);
  if (detailPromise) return detailPromise;
  detailPromise = fetchWithTimeout(DETAIL_URL).then(data => {
    detailData = data;
    return data;
  });
  return detailPromise;
}

/* ====== 级别徽章 ====== */
function levelBadge(lv) {
  const cls = lv === '二级' ? 'bg-[#e3c9a2] text-[#5a432a]' : 'bg-[#1b4332] text-[#f2f7f3]';
  return `<span class="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full ${cls}">${esc(lv)}</span>`;
}

/* ====== 图片区块 ====== */
const PAW_SVG = cls => `<svg class="${cls}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
  <circle cx="6.2" cy="8.2" r="1.7"/><circle cx="10" cy="5.9" r="1.7"/><circle cx="14" cy="5.9" r="1.7"/><circle cx="17.8" cy="8.2" r="1.7"/>
  <path d="M12 11.2c-2.2 0-3.8 1.6-3.8 3.6 0 2.6 1.6 4.2 3.8 4.2s3.8-1.6 3.8-4.2c0-2-1.6-3.6-3.8-3.6z"/>
</svg>`;

function noImgHtml(s, size) {
  const latin = s.scientific || '';
  if (size === 'tiny') {
    return `<div class="flex items-center justify-center w-full h-full text-[var(--tx-3)]">${PAW_SVG('w-5 h-5 opacity-80')}</div>`;
  }
  if (size === 'list') {
    return `<div class="flex flex-col items-center justify-center w-full h-full gap-0.5 text-[var(--tx-3)] px-1">
      ${PAW_SVG('w-7 h-7 opacity-80')}
      <span class="w-full text-center text-[9px] leading-tight truncate text-[var(--tx-3)]">${esc(latin || displayName(s.name))}</span>
    </div>`;
  }
  return `<div class="flex flex-col items-center justify-center w-full h-full gap-1.5 text-[var(--tx-3)]">
    ${PAW_SVG('w-10 h-10 md:w-12 md:h-12 opacity-75')}
    <span class="text-[12px] font-semibold text-[var(--tx-2)]">${esc(displayName(s.name))}</span>
    ${latin ? `<span class="text-[11px] italic truncate max-w-[88%]">${esc(latin)}</span>` : ''}
    <span class="inline-flex items-center">${levelBadge(s.level)}</span>
  </div>`;
}

function imgBlock(s, size, imgCls) {
  if (!s) return '';
  if (s.image) {
    return `<img src="${esc(s.image)}" alt="${esc(displayName(s.name))}" loading="lazy" class="${imgCls || ''}" onerror="this.onerror=null;var p=this.closest('.img-wrap');p.innerHTML='${esc(noImgHtml(s, size))}'">`;
  }
  return noImgHtml(s, size);
}

/* ====== 主题（深色模式） ====== */
function applyTheme(dark) {
  document.documentElement.classList.toggle('dark', dark);
  document.getElementById('themeSun').classList.toggle('hidden', !dark);
  document.getElementById('themeMoon').classList.toggle('hidden', dark);
  localStorage.setItem('wm-theme', dark ? 'dark' : 'light');

  // 图表颜色依赖 CSS 变量——用 setOption 更新而非重建
  if (provPieChart) { provPieChart.dispose(); provPieChart = null; renderProvPie(); }
  if (currentTab === 'stats') { rankChart = null; catChart = null; renderStats(); }
  if (chart && geo) {
    chart.setOption(buildMapOption(true), true);
    applyHighlight();
  }
}

function initTheme() {
  const saved = localStorage.getItem('wm-theme');
  const dark = saved ? saved === 'dark' : window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (dark) {
    document.documentElement.classList.add('dark');
    document.getElementById('themeSun').classList.remove('hidden');
    document.getElementById('themeMoon').classList.add('hidden');
  }
}

/* ====== 简介语言 ====== */
function remapDesc(lang) {
  species.forEach(s => {
    const t = s['desc_' + lang];
    s.desc = t || s.desc_zhs || s.desc || '';
  });
}

function paintLangBtns() {
  document.querySelectorAll('.lang-btn').forEach(b => {
    const active = b.dataset.lang === LANG;
    b.className = 'lang-btn px-2 py-1 rounded-full transition ' +
      (active ? 'bg-white text-[#1b4332] shadow' : 'text-[#dbe7dd] hover:bg-white/10');
  });
}

function applyLang(lang) {
  LANG = lang;
  localStorage.setItem('wm-lang', lang);
  if (!species.length) { paintLangBtns(); return; }

  if (lang === 'zhs') {
    remapDesc('zhs');
    paintLangBtns();
    renderPanel();
    if (!document.getElementById('searchDropdown').classList.contains('hidden')) doSearch();
    if (openDetailName && !document.getElementById('drawer').classList.contains('hidden')) openDetail(openDetailName);
    if (!document.getElementById('compareModal').classList.contains('hidden')) openCompare();
    return;
  }

  // zht / en 需加载详情数据
  loadDetailData().then(() => {
    remapDesc(lang);
    paintLangBtns();
    renderPanel();
    if (!document.getElementById('searchDropdown').classList.contains('hidden')) doSearch();
    if (openDetailName && !document.getElementById('drawer').classList.contains('hidden')) openDetail(openDetailName);
    if (!document.getElementById('compareModal').classList.contains('hidden')) openCompare();
  }).catch(() => {
    // fallback
    remapDesc('zhs');
    paintLangBtns();
    renderPanel();
  });
}

/* ====== 数据索引 ====== */
function buildIndex(list) {
  byProvince = {}; countByProvince = {}; riskCount = {};
  for (const s of list) for (const p of s.provinces) {
    (byProvince[p] = byProvince[p] || []).push(s);
    countByProvince[p] = (countByProvince[p] || 0) + 1;
    if (s.iucn === 'CR' || s.iucn === 'EN') riskCount[p] = (riskCount[p] || 0) + 1;
  }
}

/* ====== 地图高亮 ====== */
function buildMapOption(withVmap) {
  const useRisk = mapMode === 'risk';
  const data = geo.features.map(f => {
    const name = f.properties.name;
    if (highlightSpecies) {
      const hit = highlightSpecies.provinces.includes(name);
      return hit
        ? { name, value: countByProvince[name] || 1, itemStyle: { areaColor: '#14532d' } }
        : { name, value: 0, itemStyle: { areaColor: cssVar('--map-muted') } };
    }
    const base = useRisk ? riskCount[name] || 0 : countByProvince[name] || 0;
    return { name, value: base };
  });
  const maxV = useRisk
    ? Math.max.apply(null, Object.values(riskCount).concat([0])) || 1
    : Math.max.apply(null, Object.values(countByProvince)) || 1;
  const range = useRisk
    ? { text: ['极危/濒危多', '少'], colors: ['#fdece3', '#f7c9b3', '#e8895e', '#c94f30', '#8c1c13'] }
    : { text: ['物种丰富', '稀少'], colors: ['#eef4e6', '#c9e3c4', '#8ec592', '#4b9d63', '#1e6f43'] };
  return {
    tooltip: {
      trigger: 'item', backgroundColor: 'rgba(27,67,50,0.95)', borderColor: '#1b4332',
      padding: [8, 12], textStyle: { color: '#f6f3ec', fontSize: 12 },
      formatter: p => '<strong>' + p.name + '</strong><br/>' +
        (mapMode === 'risk'
          ? '极危/濒危物种：' + (riskCount[p.name] || 0) + ' 种'
          : '保护动物：' + (countByProvince[p.name] || 0) + ' 种'),
    },
    visualMap: withVmap
      ? {
          min: 0, max: maxV,
          left: 16, bottom: 16, orient: 'vertical', itemWidth: 12, itemHeight: 90,
          text: range.text, textGap: 12, textStyle: { color: cssVar('--tx-3'), fontSize: 11 },
          inRange: { color: range.colors },
        }
      : undefined,
    series: [{
      type: 'map', map: 'china', roam: true, selectedMode: false,
      label: { show: true, color: cssVar('--map-label'), fontSize: 10 },
      itemStyle: { borderColor: '#ffffff', borderWidth: 1, areaColor: cssVar('--map-muted') },
      emphasis: {
        label: { show: true, color: '#ffffff', fontWeight: 'bold' },
        itemStyle: { areaColor: '#14532d', shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.25)' },
      },
      data,
    }],
  };
}

function applyHighlight() {
  if (!chart || !geo) return;
  chart.setOption(buildMapOption(!highlightSpecies), true);
  labelShow = true;
  const banner = document.getElementById('highlightBanner');
  if (highlightSpecies) {
    document.getElementById('highlightText').textContent =
      '正在查看「' + displayName(highlightSpecies.name) + '」的分布省份（深色为分布区）';
    banner.classList.remove('hidden');
    banner.classList.add('flex');
  } else {
    banner.classList.add('hidden');
    banner.classList.remove('flex');
  }
}

function setHighlight(s) { highlightSpecies = s; applyHighlight(); }
function clearHighlight() { highlightSpecies = null; applyHighlight(); }

/* ====== 省份面板 ====== */
function renderProvPie() {
  const list = byProvince[currentProvince] || [];
  const lv1 = list.filter(s => s.level === '一级').length;
  const lv2 = list.filter(s => s.level === '二级').length;
  const total = list.length;
  document.getElementById('provPieTotal').textContent = total || '—';
  document.getElementById('provPieLv1').textContent = lv1;
  document.getElementById('provPieLv2').textContent = lv2;
  if (provPieChart) provPieChart.dispose();
  provPieChart = echarts.init(document.getElementById('provPie'));
  provPieChart.setOption({
    series: [{
      type: 'pie', radius: ['62%', '80%'], avoidLabelOverlap: false,
      label: { show: false }, emphasis: { scale: false },
      data: [
        { value: lv1, name: '一级', itemStyle: { color: '#1b4332' } },
        { value: lv2, name: '二级', itemStyle: { color: '#e3c9a2' } },
      ],
    }],
  });
}

function cardHTML(s) {
  const wikiLink = s.wiki
    ? `<a href="${esc(s.wiki)}" target="_blank" rel="noopener" class="text-[11px] text-[var(--tx-green-2)] hover:text-[var(--tx-head)] hover:underline">维基百科 ›</a>`
    : '';
  return `
  <article data-name="${esc(s.name)}"
    class="fade-up cursor-pointer bg-[var(--bg-card)] rounded-2xl p-3 shadow-sm border border-[var(--br-2)] hover:shadow-md hover:border-[#c9dfc4] transition-all duration-200 flex gap-3">
    <div class="img-wrap w-20 h-20 shrink-0 rounded-xl overflow-hidden border border-[#e6ecdd]" data-size="list">
      ${imgBlock(s, 'list')}
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex items-start justify-between gap-2">
        <h3 class="font-bold text-[15px] text-[var(--tx-head)] leading-snug">${esc(displayName(s.name))}</h3>
        ${levelBadge(s.level)}
      </div>
      <div class="mt-1 flex items-center gap-1.5 text-[12px] text-[var(--tx-3)]">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="#7a9b6d" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 7h16"/><path d="M6 7v11a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/>
        </svg>
        <span>${esc(s.category)}</span>
        ${s.iucn ? `<span class="text-[#b45309]">· IUCN ${esc(s.iucn)}</span>` : ''}
      </div>
      <p class="mt-1.5 text-[12.5px] leading-relaxed text-[var(--tx-2)] line-clamp-2">${s.desc || '暂无简介'}</p>
      <div class="mt-1">${wikiLink}</div>
    </div>
  </article>`;
}

function renderPanel() {
  const total = (byProvince[currentProvince] || []).length;
  const list = (byProvince[currentProvince] || []).filter(s => levelFilter === '全部' || s.level === levelFilter);
  document.getElementById('provinceName').textContent = currentProvince;
  document.getElementById('provinceCount').textContent = total + ' 种保护动物';
  renderProvPie();
  if (!total) {
    document.getElementById('animalCards').innerHTML = '<div class="fade-up py-16 text-center text-sm text-[var(--tx-3)]">该省份暂未收录保护动物分布数据</div>';
  } else if (!list.length) {
    document.getElementById('animalCards').innerHTML = '<div class="fade-up py-16 text-center text-sm text-[var(--tx-3)]">该省份暂无「' + esc(levelFilter) + '」保护动物</div>';
  } else {
    document.getElementById('animalCards').innerHTML = list.map(cardHTML).join('');
  }
  document.getElementById('panel').scrollTop = 0;
}

function selectProvince(name) { currentProvince = name; renderPanel(); switchTab('list'); }

/* ====== 统计标签 ====== */
function renderStats() {
  // 省份排名条形图（ECharts）
  const entries = Object.entries(countByProvince).sort((a, b) => a[1] - b[1]);
  if (rankChart) rankChart.dispose();
  rankChart = echarts.init(document.getElementById('rankChart'));
  rankChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: cssVar('--tx-3') } },
    yAxis: { type: 'category', data: entries.map(e => e[0]), axisLabel: { fontSize: 9, color: cssVar('--tx-2') } },
    series: [{
      type: 'bar', data: entries.map(e => ({ value: e[1], itemStyle: { color: '#4b9d63' } })),
      barMaxWidth: 20, emphasis: { itemStyle: { color: '#2d6a4f' } },
    }],
  });
  rankChart.on('click', function (params) {
    selectProvince(entries[params.dataIndex][0]);
  });

  // 类别占比环形图（ECharts）
  const counts = CATEGORIES.map(c => species.filter(s => s.category === c).length);
  if (catChart) catChart.dispose();
  catChart = echarts.init(document.getElementById('catChart'));
  catChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 种' },
    series: [{
      type: 'pie', radius: ['58%', '75%'],
      label: {
        show: true, position: 'outside', formatter: '{b}',
        fontSize: 11, color: cssVar('--tx-2'),
      },
      labelLine: { length: 8, length2: 6 },
      emphasis: { label: { show: true } },
      data: CATEGORIES.map((c, i) => ({
        value: counts[i], name: c, itemStyle: { color: CAT_COLORS[i] },
      })),
    }],
  });
  catChart.on('click', function (params) {
    openCategory(params.name);
  });
}

/* ====== 种类浏览 ====== */
function catCount(c) { return species.filter(s => s.category === c).length; }

function renderCatDropdown() {
  document.getElementById('catDropdownList').innerHTML = CATEGORIES.map(c =>
    `<button data-cat="${esc(c)}" class="cat-btn w-full text-left px-4 py-2 text-[13px] text-[var(--tx-2)] hover:bg-[var(--bg-hover)] flex items-center justify-between">
      <span>${esc(c)}</span><span class="text-[11px] text-[var(--tx-3)]">${catCount(c)}</span>
    </button>`
  ).join('');
}

function openCategory(cat) {
  document.getElementById('catDropdown').classList.add('hidden');
  const list = species.filter(s => s.category === cat).sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  document.getElementById('modalTitle').textContent = cat;
  document.getElementById('modalCount').textContent = list.length + ' 种';
  document.getElementById('modalGrid').innerHTML = list.map(s =>
    `<button data-name="${esc(s.name)}" class="species-card fade-up text-left bg-[var(--bg-card)] rounded-2xl overflow-hidden border border-[var(--br-2)] hover:border-[#c9dfc4] hover:shadow-md transition">
      <div class="img-wrap h-28 overflow-hidden" data-size="banner">${imgBlock(s, 'banner', 'w-full h-full object-cover')}</div>
      <div class="p-2.5">
        <div class="text-[13px] font-bold text-[var(--tx-head)] truncate">${esc(displayName(s.name))}</div>
        <div class="mt-1">${levelBadge(s.level)}</div>
      </div>
    </button>`
  ).join('');
  document.getElementById('categoryModal').classList.remove('hidden');
}

/* ====== 物种详情 ====== */
function openDetail(name) {
  const s = findSpecies(name); if (!s) return;
  openDetailName = s.name;
  document.getElementById('categoryModal').classList.add('hidden');
  document.getElementById('searchDropdown').classList.add('hidden');
  document.getElementById('drawerImg').innerHTML = imgBlock(s, 'banner', 'w-full h-full object-cover');
  document.getElementById('drawerName').textContent = displayName(s.name);
  document.getElementById('drawerLevel').textContent = '国家' + s.level;
  document.getElementById('drawerLevel').className = 'shrink-0 text-xs font-medium px-3 py-1 rounded-full ' +
    (s.level === '二级' ? 'bg-[#e3c9a2] text-[#5a432a]' : 'bg-[#1b4332] text-white');
  const latin = [s.scientific || '', s.en_name ? '· ' + s.en_name : ''].filter(Boolean).join(' ');
  document.getElementById('drawerLatin').textContent = latin || '—';
  document.getElementById('drawerCat').textContent = s.category;
  const iucnEl = document.getElementById('drawerIucn');
  if (s.iucn) {
    iucnEl.textContent = 'IUCN ' + s.iucn + ' · ' + (s.iucn_cn || '');
    iucnEl.className = 'text-[11px] px-2.5 py-1 rounded-full ' + (IUCN_CLS[s.iucn] || 'bg-[var(--bg-amber-soft)] text-[var(--tx-amber)]');
  } else {
    iucnEl.textContent = 'IUCN 未收录';
    iucnEl.className = 'text-[11px] px-2.5 py-1 rounded-full bg-[var(--bg-amber-soft)] text-[var(--tx-amber)]';
  }
  document.getElementById('drawerDesc').textContent = s.desc || '暂无简介';
  const faunaEl = document.getElementById('drawerFauna');
  // 尝试从懒加载数据中获取 fauna
  if (detailData && detailData[name] && detailData[name].fauna && detailData[name].fauna.items && Object.keys(detailData[name].fauna.items).length) {
    const fauna = detailData[name].fauna;
    faunaEl.classList.remove('hidden');
    faunaEl.innerHTML = `
      <div class="flex items-center gap-1.5 mb-2">
        <span class="text-xs font-bold text-[var(--tx-head)]">动物志描述</span>
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-green-soft2)] text-[var(--tx-green)]">${esc(fauna.dbase)}</span>
      </div>
      ${Object.entries(fauna.items).map(([t, v]) => `
        <div class="mb-3 rounded-xl bg-[var(--bg-soft)]/60 border border-[var(--br-2)] p-3">
          <div class="text-[11px] font-bold text-[var(--tx-green)] mb-1">▍${esc(t)}</div>
          <p class="text-[12.5px] leading-relaxed text-[var(--tx-2)] whitespace-pre-line">${esc(v.content)}</p>
          ${v.refs && v.refs.length ? `<p class="mt-1.5 text-[10.5px] text-[var(--tx-3)]">参考：${esc(v.refs.join('；'))}</p>` : ''}
        </div>`).join('')}`;
  } else {
    faunaEl.classList.add('hidden');
    faunaEl.innerHTML = '';
  }
  document.getElementById('drawerProvCount').textContent = s.provinces.length;
  document.getElementById('drawerProvs').innerHTML = s.provinces.map(p =>
    `<button data-prov="${esc(p)}" class="prov-btn text-[11px] px-2.5 py-1 rounded-full bg-[var(--bg-green-soft)] text-[var(--tx-green)] hover:bg-[var(--bg-green-soft2)] transition">${esc(p)}</button>`
  ).join('');
  const wiki = document.getElementById('drawerWiki');
  if (s.wiki) { wiki.href = s.wiki; wiki.classList.remove('pointer-events-none', 'opacity-40'); }
  else { wiki.href = '#'; wiki.classList.add('pointer-events-none', 'opacity-40'); }
  document.getElementById('drawer').classList.remove('hidden');
  // 更新对比按钮状态
  const inCmp = compareList.some(x => x.name === s.name);
  const cmpBtn = document.getElementById('drawerCompare');
  cmpBtn.textContent = inCmp ? '已加入对比 ✓（再点移除）' : '＋ 加入对比（最多 2 个物种）';
  cmpBtn.dataset.name = s.name;
}

function closeDrawer() { document.getElementById('drawer').classList.add('hidden'); }

/* ====== 物种对比 ====== */
function toggleCompare(name) {
  const s = findSpecies(name); if (!s) return;
  const i = compareList.findIndex(x => x.name === name);
  if (i >= 0) {
    compareList.splice(i, 1);
  } else {
    if (compareList.length >= 2) { openCompare(); return; }
    compareList.push(s);
  }
  const btn = document.getElementById('drawerCompare');
  const names = compareList.map(x => displayName(x.name)).join(' vs ');
  btn.textContent = compareList.length
    ? '已选 ' + compareList.length + '/2：' + names + (compareList.length === 2 ? '（再点击查看对比）' : '')
    : '＋ 加入对比（最多 2 个物种）';
  if (compareList.length === 2) openCompare();
}

function openCompare() {
  document.getElementById('compareGrid').innerHTML = compareList.map(s => {
    const latin = [s.scientific || '', s.en_name ? '· ' + s.en_name : ''].filter(Boolean).join(' ');
    const provTxt = s.provinces.length ? s.provinces.join('、') : '暂无分布数据';
    return `
    <div class="bg-[var(--bg-card)] rounded-2xl overflow-hidden border border-[var(--br-2)] shadow-sm fade-up">
      <div class="img-wrap h-36 overflow-hidden" data-size="banner">${imgBlock(s, 'banner', 'w-full h-full object-cover')}</div>
      <div class="p-3.5">
        <div class="flex items-center justify-between gap-2">
          <h4 class="font-bold text-[15px] text-[var(--tx-head)]">${esc(displayName(s.name))}</h4>
          ${levelBadge(s.level)}
        </div>
        <div class="mt-0.5 text-[12px] text-[var(--tx-3)] italic truncate">${esc(latin) || '—'}</div>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <span class="text-[10.5px] px-2 py-0.5 rounded-full bg-[var(--bg-green-soft)] text-[var(--tx-green-2)]">${esc(s.category)}</span>
          <span class="text-[10.5px] px-2 py-0.5 rounded-full bg-[var(--bg-amber-soft)] text-[var(--tx-amber)]">${s.iucn ? 'IUCN ' + esc(s.iucn) : 'IUCN 未收录'}</span>
        </div>
        <p class="mt-2.5 text-[12px] leading-relaxed text-[var(--tx-2)] line-clamp-3">${s.desc || '暂无简介'}</p>
        <div class="mt-3 pt-3 border-t border-[var(--br-2)]">
          <div class="text-[10.5px] font-bold text-[var(--tx-head)] mb-1.5">分布（${s.provinces.length} 省）</div>
          <p class="text-[11px] leading-relaxed text-[var(--tx-3)]">${esc(provTxt)}</p>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <button data-name="${esc(s.name)}" class="cmp-map-btn flex-1 text-[12px] font-medium px-3 py-1.5 rounded-full bg-[#1b4332] text-white hover:bg-[#2d6a4f] transition">地图查看</button>
          <button data-name="${esc(s.name)}" class="cmp-detail-btn flex-1 text-[12px] font-medium px-3 py-1.5 rounded-full bg-[var(--bg-soft)] text-[var(--tx-2)] hover:bg-[var(--bg-hover)] transition">详情</button>
        </div>
      </div>
    </div>`;
  }).join('');
  document.getElementById('compareModal').classList.remove('hidden');
}

/* ====== 搜索 ====== */
function doSearch() {
  const kw = document.getElementById('searchInput').value.trim();
  if (!kw) { document.getElementById('searchDropdown').classList.add('hidden'); return; }
  const results = species.filter(s =>
    s.name.includes(kw) || displayName(s.name).includes(kw) ||
    (s.scientific || '').toLowerCase().includes(kw.toLowerCase()) ||
    (s.en_name || '').toLowerCase().includes(kw.toLowerCase())
  ).slice(0, 12);
  const dd = document.getElementById('searchDropdown');
  if (!results.length) {
    dd.innerHTML = '<div class="px-4 py-6 text-center text-sm text-[var(--tx-3)]">未找到与「' + esc(kw) + '」相关的保护动物</div>';
  } else {
    dd.innerHTML = results.map(s =>
      `<button data-name="${esc(s.name)}" class="search-result w-full text-left flex items-center gap-3 px-3 py-2 hover:bg-[var(--bg-hover)] transition">
        <div class="img-wrap w-10 h-10 shrink-0 rounded-lg overflow-hidden" data-size="tiny">
          ${imgBlock(s, 'tiny', 'w-full h-full object-cover')}
        </div>
        <div class="min-w-0 flex-1">
          <div class="text-[13px] font-medium text-[var(--tx)] truncate">${esc(displayName(s.name))}</div>
          <div class="text-[11px] text-[var(--tx-3)]">${esc(s.category)} · ${esc(s.level)}</div>
        </div>
        <span class="text-[10px] text-[var(--tx-green-2)] whitespace-nowrap">${s.provinces.length}省</span>
      </button>`
    ).join('');
  }
  dd.classList.remove('hidden');
}

/* ====== 地图 ====== */
const ZOOM_HIDE = 0.85, ZOOM_SHOW = 1.0;

function syncLabelByZoom(zoom) {
  const target = zoom <= ZOOM_HIDE ? false : (zoom >= ZOOM_SHOW ? true : labelShow);
  if (target !== labelShow) {
    labelShow = target;
    chart.setOption({ series: [{ label: { show: labelShow } }] });
  }
}

function renderChart() {
  chart = echarts.init(document.getElementById('mapChart'));
  chart.setOption(buildMapOption(true));
  chart.on('click', function (params) {
    if (params && params.name) { clearHighlight(); selectProvince(params.name); }
  });
  chart.on('georoam', function () {
    const zoom = chart.getOption().series[0].zoom;
    if (typeof zoom === 'number') syncLabelByZoom(zoom);
  });
}

/* ====== 初始化 ====== */
function showError() {
  document.getElementById('mapLoading').style.display = 'none';
  const err = document.getElementById('mapError');
  err.classList.remove('hidden'); err.classList.add('flex');
}

function init() {
  Promise.all([
    fetchWithTimeout(GEO_URL),
    fetchWithTimeout(DATA_URL),
  ]).then(function ([geoJson, data]) {
    geo = geoJson;
    document.getElementById('mapLoading').style.display = 'none';
    document.getElementById('panelLoading').style.display = 'none';

    species = data.species || [];
    species.forEach(s => { byName[s.name] = s; });
    remapDesc(LANG);
    paintLangBtns();
    buildIndex(species);

    const provCount = Object.keys(countByProvince).length;
    document.getElementById('navSub').textContent =
      '已收录 ' + provCount + ' 个省级地区 / ' + species.length + ' 种保护动物';

    echarts.registerMap('china', geo);
    renderChart();
    applyHighlight();
    setMapMode('count');

    if (species.length) {
      selectProvince(DEFAULT_PROVINCE);
      document.querySelector('[data-lv="全部"]').click();
    }

    // 页面加载完成后预加载详情数据（空闲时）
    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => loadDetailData().catch(() => {}));
    }
  }).catch(showError);
}

/* ====== 事件绑定（事件委托，避免 inline onclick XSS） ====== */

// 主题
document.getElementById('themeBtn').addEventListener('click', function () {
  applyTheme(!document.documentElement.classList.contains('dark'));
});

// 语言
document.getElementById('langSwitch').addEventListener('click', function (e) {
  const btn = e.target.closest('.lang-btn'); if (!btn) return;
  applyLang(btn.dataset.lang);
});

// 清除高亮
document.getElementById('clearHighlight').addEventListener('click', clearHighlight);

// 地图模式
document.getElementById('modeCountBtn').addEventListener('click', function () {
  setMapMode('count');
});
document.getElementById('modeRiskBtn').addEventListener('click', function () {
  setMapMode('risk');
});

// 筛选级别
document.getElementById('filterBar').addEventListener('click', function (e) {
  const btn = e.target.closest('.lv-chip'); if (!btn) return;
  levelFilter = btn.dataset.lv;
  document.querySelectorAll('.lv-chip').forEach(b => {
    const active = b.dataset.lv === levelFilter;
    b.className = 'lv-chip px-3 py-1 text-xs rounded-full border transition ' +
      (active ? 'bg-[#1b4332] text-white border-[#1b4332]' : 'bg-[var(--bg-card)] text-[var(--tx-2)] border-[var(--br)] hover:border-[#a8b795]');
  });
  renderPanel();
});

// Tab 切换
document.querySelectorAll('.tab-btn').forEach(b =>
  b.addEventListener('click', function () {
    const tab = this.dataset.tab;
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      const active = btn.dataset.tab === tab;
      btn.className = 'tab-btn text-xs font-medium px-4 py-1.5 rounded-full transition ' +
        (active ? 'bg-[#1b4332] text-white shadow' : 'text-[var(--tx-2)] hover:bg-[var(--bg-hover)]');
    });
    document.getElementById('tabList').classList.toggle('hidden', tab !== 'list');
    document.getElementById('tabStats').classList.toggle('hidden', tab !== 'stats');
    if (tab === 'stats') renderStats();
  })
);

// 种类浏览按钮
document.getElementById('catBtn').addEventListener('click', function () {
  const dd = document.getElementById('catDropdown');
  dd.classList.toggle('hidden');
  if (!dd.classList.contains('hidden')) renderCatDropdown();
});

// 种类 Modal
document.getElementById('categoryModal').addEventListener('click', function (e) {
  if (e.target.closest('[data-close-modal]')) this.classList.add('hidden');
});

// 种类 Modal 关闭按钮
document.getElementById('categoryModal').querySelector('[data-close-modal]').addEventListener('click', function () {
  document.getElementById('categoryModal').classList.add('hidden');
});

// 详情抽屉
document.getElementById('drawer').addEventListener('click', function (e) {
  if (e.target.closest('[data-close-drawer]')) this.classList.add('hidden');
});

// 对比 Modal
document.getElementById('compareModal').addEventListener('click', function (e) {
  if (e.target.closest('[data-close-compare]')) this.classList.add('hidden');
});

// 搜索
let searchTimer = null;
document.getElementById('searchInput').addEventListener('input', function () {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 180);
});
document.getElementById('searchInput').addEventListener('focus', doSearch);

// 全局点击关闭下拉
document.addEventListener('click', function (e) {
  if (!e.target.closest('#searchInput') && !e.target.closest('#searchDropdown')) {
    document.getElementById('searchDropdown').classList.add('hidden');
  }
  if (!e.target.closest('#catBtn') && !e.target.closest('#catDropdown')) {
    document.getElementById('catDropdown').classList.add('hidden');
  }
});

// 键盘 Escape 关闭最上层弹窗
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') return;
  if (!document.getElementById('compareModal').classList.contains('hidden')) {
    document.getElementById('compareModal').classList.add('hidden');
  } else if (!document.getElementById('drawer').classList.contains('hidden')) {
    document.getElementById('drawer').classList.add('hidden');
  } else if (!document.getElementById('categoryModal').classList.contains('hidden')) {
    document.getElementById('categoryModal').classList.add('hidden');
  }
});

// resize 防抖
window.addEventListener('resize', function () {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () {
    if (chart) chart.resize();
    if (rankChart) rankChart.resize();
    if (catChart) catChart.resize();
    if (provPieChart) provPieChart.resize();
  }, 150);
});

// ====== 全局事件委托（代替 inline onclick） ======

// 物种卡片 → 打开详情
document.addEventListener('click', function (e) {
  const article = e.target.closest('[data-name]');
  if (article && !e.target.closest('a')) {
    openDetail(article.dataset.name);
  }
});

// 种类浏览按钮（种类下拉）
document.addEventListener('click', function (e) {
  const btn = e.target.closest('.cat-btn');
  if (btn) openCategory(btn.dataset.cat);
});

// 种类 Modal 中的物种卡片
document.addEventListener('click', function (e) {
  const card = e.target.closest('.species-card');
  if (card) openDetail(card.dataset.name);
});

// 搜索下拉结果
document.addEventListener('click', function (e) {
  const result = e.target.closest('.search-result');
  if (result) {
    openDetail(result.dataset.name);
    document.getElementById('searchDropdown').classList.add('hidden');
  }
});

// 详情抽屉省份按钮
document.addEventListener('click', function (e) {
  const btn = e.target.closest('.prov-btn');
  if (btn) {
    selectProvince(btn.dataset.prov);
    document.getElementById('drawer').classList.add('hidden');
  }
});

// 对比 Modal 中的地图查看按钮
document.addEventListener('click', function (e) {
  const btn = e.target.closest('.cmp-map-btn');
  if (btn) {
    setHighlight(findSpecies(btn.dataset.name));
    document.getElementById('compareModal').classList.add('hidden');
  }
});

// 对比 Modal 中的详情按钮
document.addEventListener('click', function (e) {
  const btn = e.target.closest('.cmp-detail-btn');
  if (btn) {
    openDetail(btn.dataset.name);
    document.getElementById('compareModal').classList.add('hidden');
  }
});

// 详情抽屉「在地图上查看」
document.getElementById('drawerViewDist').addEventListener('click', function () {
  if (openDetailName) {
    setHighlight(findSpecies(openDetailName));
    closeDrawer();
  }
});

// 详情抽屉「加入对比」
document.getElementById('drawerCompare').addEventListener('click', function () {
  const name = this.dataset.name;
  if (name) toggleCompare(name);
});

// 详情抽屉 维基百科链接（已用 data 属性 + a 标签，不需要额外绑定）

// ====== 启动 ======
document.addEventListener('DOMContentLoaded', function () {
  initTheme();
  init();
});