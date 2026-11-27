window.addEventListener('error', ev => { document.title = 'ERR ' + ev.message; });
// ================= 视图与绘制 =================
let inited = false;
function resize(){
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth, h = cv.clientHeight;
  if(w < 60 || h < 60) return;          // 尺寸未就绪，等待下一帧
  W = w; H = h;
  cv.width = Math.round(W * dpr);
  cv.height = Math.round(H * dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  if(!inited){
    inited = true;
    fitTo([...Array(nodes.length).keys()], false);   // 首帧直接就位，避免从原点放大
  } else {
    draw();
  }
}
window.addEventListener('resize', resize);

function toScreen(x,y){ return [x*view.k + view.x, y*view.k + view.y]; }
function toWorld(sx,sy){ return [(sx - view.x)/view.k, (sy - view.y)/view.k]; }

function fitTarget(list, pad, cap, leftPad){
  let minx=1e9,maxx=-1e9,miny=1e9,maxy=-1e9;
  list.forEach(i=>{
    const n = nodes[i];
    minx=Math.min(minx,n.x); maxx=Math.max(maxx,n.x);
    miny=Math.min(miny,n.y); maxy=Math.max(maxy,n.y);
  });
  const lp = leftPad || pad;
  const availW = Math.max(W - lp - pad, 120);
  const w = Math.max(maxx-minx, 60), h = Math.max(maxy-miny, 60);
  const k = Math.max(Math.min(availW/w, (H - pad*2)/h, cap), 0.06);
  return { k, x: lp + availW/2 - ((minx+maxx)/2)*k, y: H/2 - ((miny+maxy)/2)*k };
}

/* 视图补间：缩放走指数插值，位移走三次缓出，避免相位错乱 */
let fly = null;
function flyTo(target, ms){
  const dur = ms || 520;
  const f = { from:{k:view.k, x:view.x, y:view.y}, to:target, t0:performance.now(), ms:dur };
  fly = f;
  kick();
  // 兜底：若页面被节流、rAF 长时间不触发，超时后直接落位
  setTimeout(()=>{ if(fly === f){ Object.assign(view, target); fly = null; draw(); } }, dur + 160);
}

function fitTo(list, animate, leftPad, capOv){
  if(!list.length) return;
  const n = list.length;
  const tight = n <= 10;
  // 聚焦放大上限按节点数收敛：少节点可推得更近，多节点保留上下文
  const cap = capOv || (n <= 2 ? 1.6 : n <= 5 ? 1.25 : n <= 10 ? 1.0 : 2.2);
  const target = fitTarget(list, tight ? 168 : 90, cap, leftPad);
  if(animate === false || !inited){ Object.assign(view, target); draw(); return; }
  flyTo(target, tight ? 620 : 480);
}

/* ===== 动画循环：补间 + 导览闪烁 ===== */
let rafId = null, lastPaint = 0;
function kick(){ if(rafId === null) rafId = requestAnimationFrame(tick); }
function tick(now){
  rafId = null;
  let dirty = false, animating = false;

  if(fly){
    let p = (now - fly.t0) / fly.ms;
    if(p > 1) p = 1;
    const e = 1 - Math.pow(1 - p, 3);
    const f = fly.from, t = fly.to;
    view.k = f.k * Math.pow(t.k / f.k, e);          // 缩放在对数域插值
    view.x = f.x + (t.x - f.x) * e;
    view.y = f.y + (t.y - f.y) * e;
    if(p === 1) fly = null; else animating = true;
    dirty = true;
  }
  if(stepSet) dirty = true;                          // 闪烁需要持续重绘

  if(dirty){
    if(animating || now - lastPaint > 32){ draw(); lastPaint = now; }
    kick();
  }
}

function visible(i){
  const n = nodes[i];
  if(hidden.has(i)) return false;
  if(!layerOn[n.l]) return false;
  if(searchActive) return matchSet.has(i);
  if(focusMode && selected !== null) return i === selected || neighbors.has(i);
  return true;
}

function draw(){
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0,0,W,H);

  const k = view.k;
  const selSet = selected !== null ? new Set([selected, ...adj[selected]]) : null;

  // ---- 边 ----
  ctx.lineWidth = Math.max(0.3, 0.5*Math.min(k*1.6,1.2));
  for(let i=0;i<edges.length;i++){
    const e = edges[i];
    if(!visible(e.s) || !visible(e.t)) continue;
    const a = nodes[e.s], b = nodes[e.t];
    const [x1,y1] = toScreen(a.x,a.y), [x2,y2] = toScreen(b.x,b.y);
    if((x1<-40&&x2<-40)||(x1>W+40&&x2>W+40)) continue;
    if((y1<-40&&y2<-40)||(y1>H+40&&y2>H+40)) continue;
    const hot = selSet && (selSet.has(e.s) && selSet.has(e.t) &&
                (e.s===selected || e.t===selected));
    if(hot){ ctx.strokeStyle = 'rgba(88,166,255,.55)'; ctx.lineWidth = 1.15; }
    else   { ctx.strokeStyle = 'rgba(94,112,132,.26)'; ctx.lineWidth = 0.5; }
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  }

  // ---- 簇（包）标签 ----
  if(k < 1.15){
    ctx.font = '600 12px -apple-system,"Noto Sans SC","Microsoft YaHei",sans-serif';
    ctx.textAlign = 'center';
    const occupied = [];                       // 标签避让：大簇优先占位
    const sorted = clusters.slice().sort((a,b)=>(b.n||0)-(a.n||0));
    for(const c of sorted){
      const isDocC = c.k.startsWith('docs/');
      if((c.n || 0) < (isDocC ? 12 : 5)) continue;
      let [x,y] = toScreen(c.x, c.y);
      const rad = (c.r || 0) * view.k;
      x += rad * 0.42; y -= rad * 0.86;   // 标签落在岛的上方，避免压住节点
      if(x < -80 || x > W+80 || y < -40 || y > H+40) continue;
      const label = c.k === '(root)' ? '根级配置与文档'
        : isDocC ? '文档 · ' + c.k.replace('docs/','').split('/').slice(-2).join('/')
        : c.k.replace('packages/','').replace('apps/','');
      const w2 = ctx.measureText(label).width;
      const box = [x - w2/2 - 5, y - 10, x + w2/2 + 5, y + 7];
      if(occupied.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      occupied.push(box);
      ctx.globalAlpha = Math.max(0.35, Math.min(1, (1.2 - k) / 0.55));
      ctx.fillStyle = 'rgba(13,17,23,.82)';
      ctx.fillRect(box[0], box[1], w2 + 10, 17);
      ctx.fillStyle = isDocC ? '#8494a3' : '#a9bccf';
      ctx.fillText(label, x, y + 3);
      ctx.globalAlpha = 1;
    }
    ctx.textAlign = 'left';
  }

  // ---- 节点 ----
  const showLabel = k > 1.02;
  const labelMinDeg = k > 1.35 ? 7 : k > 1.1 ? 10 : 14;
  for(let oi=0; oi<drawOrder.length; oi++){
    const i = drawOrder[oi];
    if(!visible(i)) continue;
    const n = nodes[i];
    const [x,y] = toScreen(n.x,n.y);
    if(x < -30 || x > W+30 || y < -30 || y > H+30) continue;
    const isDoc = n.l === 'layer:reference-docs';
    const r = Math.min(3.4 + 2.4*Math.sqrt(n.d), 12) * Math.min(Math.max(k*1.35, 0.55), 1.45)
              * (isDoc ? 0.82 : 1);
    const col = layerColor[n.l] || '#8b949e';
    const inStep = stepSet ? stepSet.has(i) : false;

    if(selected === i){
      ctx.beginPath(); ctx.arc(x,y,r+5,0,6.2832);
      ctx.fillStyle = 'rgba(88,166,255,.18)'; ctx.fill();
      ctx.beginPath(); ctx.arc(x,y,r,0,6.2832);
      ctx.fillStyle = '#ffffff'; ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 2.2; ctx.stroke();
    } else {
      const dim = (selSet && !selSet.has(i)) || (searchActive && !matchSet.has(i));
      const sdim = stepSet && !inStep;
      ctx.globalAlpha = dim ? 0.30 : (sdim ? 0.34 : (isDoc ? 0.48 : 1));
      ctx.beginPath(); ctx.arc(x,y,r,0,6.2832);
      ctx.fillStyle = col; ctx.fill();
      ctx.globalAlpha = 1;
      if(inStep){   // 聚焦节点：加亮核 + 暖色描边
        ctx.beginPath(); ctx.arc(x,y,r*0.72,0,6.2832);
        ctx.fillStyle = 'rgba(255,232,200,.55)'; ctx.fill();
        ctx.beginPath(); ctx.arc(x,y,r+2.2,0,6.2832);
        ctx.strokeStyle = 'rgba(255,186,104,.9)'; ctx.lineWidth = 1.5; ctx.stroke();
      }
    }

    // 标签：度数高的节点 + 缩放足够时；导览聚焦节点始终显示
    const labelOk = isDoc ? (k > 1.5) : showLabel;
    if((labelOk || inStep) && (n.d >= labelMinDeg || inStep || (selSet && selSet.has(i)) || (searchActive && matchSet.has(i)))){
      const dim = (selSet && !selSet.has(i)) || (searchActive && !matchSet.has(i));
      const sdim = stepSet && !inStep;
      ctx.globalAlpha = dim ? 0.35 : (sdim ? 0.32 : 0.95);
      ctx.textAlign = 'left';
      if(inStep){
        ctx.font = '600 12px -apple-system,"Noto Sans SC","Microsoft YaHei",sans-serif';
        const lw = ctx.measureText(n.name).width;
        ctx.fillStyle = 'rgba(18,14,10,.86)';
        ctx.fillRect(x + r + 4, y - 9, lw + 10, 17);
        ctx.strokeStyle = 'rgba(255,186,104,.45)'; ctx.lineWidth = 1;
        ctx.strokeRect(x + r + 4, y - 9, lw + 10, 17);
        ctx.fillStyle = '#ffd9b1';
        ctx.fillText(n.name, x + r + 9, y + 3.6);
      } else {
        ctx.font = '10.5px -apple-system,"Noto Sans SC","Microsoft YaHei",sans-serif';
        ctx.fillStyle = '#c9d5e1';
        ctx.fillText(n.name, x + r + 3, y + 3.2);
      }
      ctx.globalAlpha = 1;
    }
  }
}

// ================= 命中测试 =================
function pick(sx, sy){
  const [wx, wy] = toWorld(sx, sy);
  const cx = (wx/GRID)|0, cy = (wy/GRID)|0;
  let best = null, bestD = 1e9;
  for(let dx=-1;dx<=1;dx++) for(let dy=-1;dy<=1;dy++){
    const arr = grid.get((cx+dx)+','+(cy+dy));
    if(!arr) continue;
    for(const i of arr){
      if(!visible(i)) continue;
      const n = nodes[i];
      const r = (Math.min(3.4 + 2.4*Math.sqrt(n.d), 12) * Math.min(Math.max(view.k*1.35, 0.55), 1.45));
      const d = Math.hypot(n.x - wx, n.y - wy);
      const tol = Math.max(r, 9) / Math.max(view.k, 0.12);
      if(d < tol && d < bestD){ best = i; bestD = d; }
    }
  }
  return best;
}

// ================= 交互 =================
const tip = document.getElementById('tip');
cv.addEventListener('mousemove', ev=>{
  if(dragging) return;
  const rect = cv.getBoundingClientRect();
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
  const i = pick(mx, my);
  if(i !== hovered){
    hovered = i;
    if(i === null){ tip.style.display = 'none'; }
    else{
      const n = nodes[i];
      tip.innerHTML = `<div class="n">${esc(n.name)}</div>
        <div class="p">${esc(n.p)}</div>
        <div class="s"><span style="color:${layerColor[n.l]}">●</span> ${esc(layerShort[n.l]||layerName[n.l]||'')} ·
        度数 ${n.d} · ${esc(n.c || 'n/a')}</div>
        <div class="s" style="margin-top:4px">${esc(n.s)}</div>`;
      tip.style.display = 'block';
      const tw = 340;
      tip.style.left = Math.min(mx + 16, W - tw - 10) + 'px';
      tip.style.top  = Math.max(my - 10, 8) + 'px';
    }
  }
});
cv.addEventListener('mouseleave', ()=>{ tip.style.display='none'; hovered=null; });

let dragging = false, moved = false, lx=0, ly=0;
cv.addEventListener('mousedown', ev=>{
  dragging = true; moved = false; lx = ev.clientX; ly = ev.clientY; fly = null;
  cv.classList.add('drag');
});
window.addEventListener('mouseup', ev=>{
  if(dragging && !moved){
    const rect = cv.getBoundingClientRect();
    const i = pick(ev.clientX-rect.left, ev.clientY-rect.top);
    selectNode(i);
  }
  dragging = false; cv.classList.remove('drag');
});
cv.addEventListener('mousemove', ev=>{
  if(!dragging) return;
  const dx = ev.clientX - lx, dy = ev.clientY - ly;
  if(Math.abs(dx)+Math.abs(dy) > 2) moved = true;
  view.x += dx; view.y += dy; lx = ev.clientX; ly = ev.clientY;
  draw();
});
cv.addEventListener('wheel', ev=>{
  ev.preventDefault();
  const rect = cv.getBoundingClientRect();
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
  const [wx, wy] = toWorld(mx, my);
  fly = null;
  const f = Math.exp(-ev.deltaY * 0.0014);
  view.k = Math.min(Math.max(view.k * f, 0.05), 3.2);
  view.x = mx - wx * view.k;
  view.y = my - wy * view.k;
  draw();
}, {passive:false});

document.getElementById('zin').onclick  = ()=>{ view.k = Math.min(view.k*1.25, 3.2); draw(); };
document.getElementById('zout').onclick = ()=>{ view.k = Math.max(view.k/1.25, 0.05); draw(); };
document.getElementById('fit').onclick  = ()=>{
  selected=null; activeStep=null; focusMode=false; stepSet=null;
  document.getElementById('dim').classList.remove('on');
  showDetail(null); renderTour(); fitTo([...Array(nodes.length).keys()].filter(visible));
};
const dimBtn = document.getElementById('dim');
dimBtn.onclick = ()=>{
  focusMode = !focusMode;
  dimBtn.classList.toggle('on', focusMode);
  draw();
};

// ================= 选中与详情 =================
function selectNode(i){
  selected = i;
  neighbors.clear();
  if(i !== null) adj[i].forEach(j=>neighbors.add(j));
  showDetail(i);
  draw();
}
const dEl = document.getElementById('detail');
document.getElementById('dclose').onclick = ()=>{ selected=null; showDetail(null); draw(); };

function showDetail(i){
  if(i === null){ dEl.classList.remove('on'); return; }
  const n = nodes[i];
  document.getElementById('dname').textContent = n.name;
  document.getElementById('dpath').innerHTML = esc(n.p)
    + (n.doc ? ` <a class="doclink" href="${esc(n.doc)}" data-doc="${esc(n.doc)}" target="_blank" rel="noopener">官方文档 ↗</a>` : '');
  document.getElementById('dsum').textContent = n.s;
  const kv = document.getElementById('dkv');
  kv.innerHTML = `<span style="border-color:${layerColor[n.l]};color:${layerColor[n.l]}">${esc(layerShort[n.l]||layerName[n.l]||'')}</span>`
    + `<span>度数 ${n.d}</span><span>复杂度 ${esc(n.c||'n/a')}</span>`
    + (n.g||[]).map(g=>`<span>${esc(g)}</span>`).join('');
  const nb = document.getElementById('dnb');
  const list = adj[i].slice().sort((a,b)=>nodes[b].d-nodes[a].d).slice(0,10);
  nb.innerHTML = list.length ? list.map(j=>{
    const m = nodes[j];
    return `<a data-j="${j}"><span style="color:${layerColor[m.l]}">●</span> ${esc(m.name)}
      <span style="color:#647382"> · ${esc(m.p.split('/').slice(-2).join('/'))}</span></a>`;
  }).join('') : '<span style="color:#647382;font-size:11px">无文件级关联</span>';
  nb.querySelectorAll('a').forEach(a=>{
    a.onclick = ()=>selectNode(parseInt(a.dataset.j,10));
  });
  dEl.classList.add('on');
}

// ================= 导览 =================
const tourEl = document.getElementById('tour');
function renderTour(){
  tourEl.innerHTML = '';
  tour.forEach(s=>{
    const d = document.createElement('div');
    d.className = 'step' + (activeStep === s.order ? ' active' : '');
    d.innerHTML = `<div class="no">${s.order}</div>
      <div><div class="tt">${esc(s.title)}</div>
      <div class="meta">${s.nodeIds.length} 个文件</div></div>`;
    d.onclick = ()=>activateStep(s);
    tourEl.appendChild(d);
  });
}
const sdEl = document.getElementById('stepdesc');
function closeStep(){ activeStep = null; stepSet = null; fly = null; sdEl.classList.remove('on'); renderTour(); draw(); }

let stepT0 = 0;
function activateStep(s){
  if(activeStep === s.order){ closeStep(); return; }
  activeStep = s.order;
  const ids = new Set(s.nodeIds.map(id=>nodes.findIndex(n=>n.id===id)).filter(i=>i>=0));
  selected = null; showDetail(null);
  focusMode = false; document.getElementById('dim').classList.remove('on');
  renderTour();
  sdEl.innerHTML = `<div class="sdclose" id="sdclose">×</div>
    <div class="sdhead"><div class="sdno">${s.order}</div><div class="sdtitle">${esc(s.title)}</div></div>
    <div class="sdbody">${esc(s.description + (s.languageLesson ? '\n\n' + s.languageLesson : ''))}</div>`
    + (s.doc ? `<a class="sddoc" href="${esc(s.doc)}" data-doc="${esc(s.doc)}" target="_blank" rel="noopener">官方文档 · ${esc(s.docTitle || '参考')} ↗</a>` : '');
  sdEl.classList.add('on');
  document.getElementById('sdclose').onclick = closeStep;
  // 高亮该步涉及节点：借由 search 机制之外的临时集合
  hidden.clear();
  highlightStep(ids);
  stepT0 = performance.now();
  // 自动焦点：留出左侧讲解卡片的空间，动画推近
  fitTo([...ids], true, 436);
  kick();
}
let stepSet = null;
function highlightStep(ids){ stepSet = ids; }

// 导览聚焦时：暖色扩散脉冲 + 呼吸底环（首 1.7s 更强）
const _draw = draw;
draw = function(){
  _draw();
  if(!stepSet) return;
  const t = (performance.now() - stepT0) / 1000;
  const burst = Math.max(0, 1 - t / 1.7);
  ctx.save();
  stepSet.forEach(i=>{
    const n = nodes[i];
    const [x,y] = toScreen(n.x,n.y);
    if(x < -70 || x > W+70 || y < -70 || y > H+70) return;
    const r0 = Math.min(3.4 + 2.4*Math.sqrt(n.d), 12) * Math.min(Math.max(view.k*1.35, 0.55), 1.45);

    // 暖色光晕（低频呼吸）
    const halo = 0.10 + 0.06 * Math.sin(t*3.2) + 0.08*burst;
    const g = ctx.createRadialGradient(x, y, r0*0.6, x, y, r0 + 15);
    g.addColorStop(0, `rgba(255,168,84,${(halo*1.5).toFixed(3)})`);
    g.addColorStop(1, 'rgba(255,168,84,0)');
    ctx.beginPath(); ctx.arc(x,y,r0+15,0,6.2832);
    ctx.fillStyle = g; ctx.fill();

    // 呼吸底环
    const breath = 0.44 + 0.34 * Math.sin(t*3.2);
    ctx.beginPath(); ctx.arc(x,y,r0+4.5,0,6.2832);
    ctx.strokeStyle = `rgba(255,178,92,${breath.toFixed(3)})`;
    ctx.lineWidth = 1.4; ctx.stroke();

    // 向外扩散的脉冲环（按索引错相位，避免整齐闪烁）
    for(let p=0; p<2; p++){
      const ph = (t*0.75 + p*0.5 + (i%7)*0.06) % 1;
      const rr = r0 + 4 + ph * (18 + 22*burst);
      const a  = (1-ph) * (0.75 + 0.25*burst);
      ctx.beginPath(); ctx.arc(x,y,rr,0,6.2832);
      ctx.strokeStyle = `rgba(255,190,110,${a.toFixed(3)})`;
      ctx.lineWidth = 2.2*(1-ph) + 0.5;
      ctx.stroke();
    }
  });
  ctx.restore();
};

// ================= 分层图例 =================
const layEl = document.getElementById('layers');
layers.forEach(l=>{
  const d = document.createElement('div');
  d.className = 'lay';
  d.innerHTML = `<span class="dot" style="background:${layerColor[l.id]}"></span>
    <span title="${esc(l.description)}">${esc(l.name)}</span>
    <span class="cnt">${l.nodeIds.length}</span>`
    + (l.doc ? `<a class="laydoc" href="${esc(l.doc)}" data-doc="${esc(l.doc)}" target="_blank" rel="noopener" title="悬浮展开官方文档 · ${esc(l.docTitle||'参考')}">↗</a>` : '');
  const dl = d.querySelector('.laydoc');
  if(dl) dl.onclick = ev=>ev.stopPropagation();
  d.onclick = ()=>{
    layerOn[l.id] = !layerOn[l.id];
    d.classList.toggle('off', !layerOn[l.id]);
    draw();
  };
  layEl.appendChild(d);
});

// ================= 搜索 =================
const qEl = document.getElementById('q');
qEl.addEventListener('input', ()=>{
  const q = qEl.value.trim().toLowerCase();
  matchSet.clear();
  searchActive = q.length > 0;
  if(searchActive && activeStep !== null) closeStep();
  if(searchActive){
    nodes.forEach((n,i)=>{
      if(n.name.toLowerCase().includes(q) || n.p.toLowerCase().includes(q) ||
         (n.g||[]).some(g=>String(g).toLowerCase().includes(q)) ||
         (n.s||'').toLowerCase().includes(q)) matchSet.add(i);
    });
    if(matchSet.size && matchSet.size < 400) fitTo([...matchSet], true, 0, matchSet.size <= 3 ? 0.9 : 2.2);
  }
  draw();
});

function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// ================= 官方文档悬浮展开 =================
// docs 全文拆到 data/docs.json 按需加载，避免阻塞首屏（原内嵌 1.8MB）
const DOC = DATA.docs || {};
let docsPromise = null;
function loadDocs(){
  if(Object.keys(DOC).length) return Promise.resolve();
  if(!docsPromise){
    docsPromise = fetch('data/docs.json')
      .then(r => r.json())
      .then(d => { Object.assign(DOC, d); return d; })
      .catch(e => { console.warn('docs load failed', e); docsPromise = null; });
  }
  return docsPromise;
}
const SITE_BASE = 'https://deepseek-harness.github.io/deepseek-harness/';
function docKeyFromUrl(u){
  if(!u) return null;
  // 站点链接：兼容官网绝对 URL 与本站 /deepseek-harness/ 路径
  let r = u;
  if(r.startsWith(SITE_BASE)) r = r.slice(SITE_BASE.length);
  r = r.replace(/^\/deepseek-harness\//, '').split(/[?#]/)[0].replace(/\/$/, '');
  if(r.startsWith('reference') || r.startsWith('guide') || r.startsWith('develop')){
    if(r === 'reference') r = 'reference/index';
    return DOC[r] ? r : null;
  }
  // 非站点链接：按 URL 末段在 payload 中做后缀匹配（如 GitHub 源码页）
  const tail = r.replace(/\.zh?\.md$/, '').split('/').slice(-2).join('/');
  const hit = Object.keys(DOC).find(k => k === 'reference/' + tail || k.endsWith('/' + tail));
  return hit || null;
}

// 轻量 Markdown 渲染：标题 / 列表 / 代码块 / 表格 / 引用 / 行内 code / 粗体 / 链接
function mdRender(md, docUrl){
  if(!md) return '';
  const lines = md.split('\n');
  const out = [];
  let inCode = false, code = [], listType = null, table = null;
  // 站内文档：#锚点 拼到当前文档页 URL，保证精确定位；离线面板保持页内锚点
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
      (_, t, h) => {
        let href = h;
        if(h.startsWith('#') && docUrl && docUrl.startsWith('/') && !docUrl.startsWith('//')) href = docUrl + h;
        return `<a href="${esc(href)}" target="_blank" rel="noopener">${t}</a>`;
      });
  const flushList = ()=>{ if(listType){ out.push(`</${listType}>`); listType = null; } };
  const flushTable = ()=>{
    if(table){
      const head = table.shift() || [];
      if(head.length && table.length && /^[\s:|-]+$/.test(table[0].join('|'))){
        table.shift();
        out.push('<table><thead><tr>' + head.map(c=>`<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
          + table.map(r=>'<tr>' + head.map((_,i)=>`<td>${inline(r[i]||'')}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
      } else {
        out.push('<p>' + [head, ...table].map(r=>inline(r.join(' · '))).join('<br>') + '</p>');
      }
      table = null;
    }
  };
  const flush = ()=>{ flushList(); flushTable(); };
  for(const raw of lines){
    const ln = raw.replace(/\s+$/, '');
    if(ln.startsWith('```')){
      if(inCode){ out.push('<pre><code>' + esc(code.join('\n')) + '</code></pre>'); code = []; inCode = false; }
      else { flush(); inCode = true; }
      continue;
    }
    if(inCode){ code.push(raw); continue; }
    if(ln.startsWith('|') && ln.endsWith('|')){
      flushList();
      const cells = ln.slice(1, -1).split('|').map(c=>c.trim());
      if(!table){ flushTable(); table = []; }
      table.push(cells);
      continue;
    }
    flushTable();
    const h = ln.match(/^(#{1,4})\s+(.*)$/);
    if(h){ flushList(); const lv = Math.min(h[1].length + 1, 4); out.push(`<h${lv}>${inline(h[2])}</h${lv}>`); continue; }
    if(/^\s*[-*+]\s+/.test(ln)){
      if(listType !== 'ul'){ flushList(); out.push('<ul>'); listType = 'ul'; }
      out.push('<li>' + inline(ln.replace(/^\s*[-*+]\s+/, '')) + '</li>'); continue;
    }
    if(/^\s*\d+\.\s+/.test(ln)){
      if(listType !== 'ol'){ flushList(); out.push('<ol>'); listType = 'ol'; }
      out.push('<li>' + inline(ln.replace(/^\s*\d+\.\s+/, '')) + '</li>'); continue;
    }
    if(/^>\s?/.test(ln)){ flushList(); out.push('<blockquote>' + inline(ln.replace(/^>\s?/, '')) + '</blockquote>'); continue; }
    if(ln.trim() === ''){ flushList(); continue; }
    flushList();
    out.push('<p>' + inline(ln) + '</p>');
  }
  flush();
  if(inCode && code.length) out.push('<pre><code>' + esc(code.join('\n')) + '</code></pre>');
  return out.join('');
}

const docpop = document.getElementById('docpop');
let docHideTimer = null, docCurKey = null;
function hideDoc(){
  clearTimeout(docHideTimer);
  docHideTimer = setTimeout(()=>{ docpop.classList.remove('on'); docCurKey = null; }, 140);
}
function keepDoc(){ clearTimeout(docHideTimer); }
async function showDoc(url, anchor){
  await loadDocs();
  const key = docKeyFromUrl(url);
  if(!key){ return; }
  keepDoc();
  if(key !== docCurKey){
    docCurKey = key;
    const d = DOC[key];
    if(!d) return;
    // 大文档只渲染前 60k 字符，悬浮体验优先；完整版可从本地文件 / 原网页查看
    const full = d.md.length > 60000;
    const body = mdRender(full ? d.md.slice(0, 60000) + '\n\n> …（内容较长，已截断；完整正文见本地文件或原网页）' : d.md, d.url);
    docpop.innerHTML = `<div class="dphead">
        <span class="dpgroup">${esc(d.group)}</span>
        <span class="dptitle">${esc(d.title)}</span>
        <a class="dpopen" href="${esc(d.url)}" target="_blank" rel="noopener">原网页 ↗</a>
      </div>
      <div class="dpbody">${body}</div>
      <div class="dpfoot"><span class="dplocal">本地：${esc(d.file)}</span>
        <span class="dpmore">悬停展开 · 滚轮滚动</span></div>`;
    docpop.querySelector('.dpbody').scrollTop = 0;
  }
  docpop.classList.add('on');
  // 定位：优先放锚点下方，空间不足则上方；水平居中并夹在视口内
  const r = anchor.getBoundingClientRect();
  const pw = docpop.offsetWidth, ph = docpop.offsetHeight;
  let x = r.left;
  if(x + pw > innerWidth - 12) x = innerWidth - pw - 12;
  if(x < 12) x = 12;
  let y = r.bottom + 8;
  if(y + ph > innerHeight - 12) y = Math.max(12, r.top - ph - 8);
  docpop.style.left = x + 'px';
  docpop.style.top = y + 'px';
}
// 事件委托：所有带 data-doc 的入口（讲解卡片 / 图层例 / 详情面板）
document.addEventListener('mouseover', ev=>{
  const a = ev.target.closest('[data-doc]');
  if(a) showDoc(a.getAttribute('data-doc'), a);
});
document.addEventListener('mouseout', ev=>{
  const a = ev.target.closest('[data-doc]');
  if(a) hideDoc();
});
docpop.addEventListener('mouseenter', keepDoc);
docpop.addEventListener('mouseleave', hideDoc);
// 点击入口：仍可在新标签打开原网页（保留可达性）
document.addEventListener('click', ev=>{
  const a = ev.target.closest('[data-doc]');
  if(a && a.tagName === 'A' && a.target === '_blank') ev.stopPropagation();
});

// ================= 启动 =================
const meta = DATA.meta || {};
document.getElementById('s-n').textContent = (meta.allNodes || nodes.length).toLocaleString();
document.getElementById('s-e').textContent = (meta.allEdges || edges.length).toLocaleString();
document.getElementById('s-l').textContent = layers.length;
document.getElementById('s-t').textContent = tour.length;
document.getElementById('s-canvas').textContent =
  `画布渲染 ${nodes.length.toLocaleString()} 个文件级节点 · ${edges.length.toLocaleString()} 条关系`;
renderTour();
requestAnimationFrame(()=>requestAnimationFrame(resize));
// 首屏渲染完成后，空闲时后台预取 docs，用户首次悬浮时已就绪
if(window.requestIdleCallback) requestIdleCallback(()=>loadDocs(), {timeout:3000});
else setTimeout(loadDocs, 1200);
