const $ = (selector) => document.querySelector(selector);
let mode = 'auto', busy = false, pollTimer, toastTimer;
let accessKey = sessionStorage.getItem('career-access-key') || '';
const labels = {matching_jobs:'匹配岗位', salary_samples:'有效薪资样本', avg_monthly_salary:'平均月薪（元）', city:'城市', jobs:'岗位数', title:'岗位名称', address:'城市', companyTitle:'公司', salary:'薪资区间'};

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function toast(text) { $('#toast').textContent = text; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 6500); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json', ...(accessKey ? {'X-API-Key':accessKey} : {}), ...options.headers}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请检查输入或服务状态');
  return data;
}
function scrollChat() { $('#messages').scrollTop = $('#messages').scrollHeight; }
async function refreshHealth() {
  try {
    const health = await api('/api/health');
    $('#db-status').textContent = health.database ? '数据源已连接' : '数据库连接失败';
    $('#db-dot').classList.toggle('connected', health.database);
    $('#model-status').textContent = health.mode === 'live' ? `● ${health.model} 已配置` : health.mode === 'demo' ? '◌ 本地演示模式' : '◌ 待配置模型';
    $('#retrieval-label').textContent = `${health.embedding_provider === 'hash' ? '词面向量演示' : '语义向量'} + BM25 · Top 5`;
    const building = health.build.status === 'building';
    $('#rebuild').disabled = building;
    $('#rebuild').textContent = building ? '↻ 正在构建索引…' : '↻ 构建检索索引';
    $('#index-status').textContent = building ? '后台构建中，完成后自动更新' : health.build.error || (health.index.ready ? `${health.index.jobs.toLocaleString()} 岗位 / ${health.index.chunks.toLocaleString()} 文档块` : '尚未构建，请点击上方按钮');
    clearTimeout(pollTimer);
    if (building) pollTimer = setTimeout(refreshHealth, 2500);
  } catch (error) { $('#db-status').textContent = '服务未连接'; $('#model-status').textContent = '服务不可用'; toast(error.message); }
}
async function loadOverview() {
  try {
    const data = await api('/api/overview');
    for (const name of ['jobs','cities','companies']) $(`#metric-${name}`).textContent = Number(data[name]).toLocaleString();
    $('#metric-salary').textContent = data.avg_salary === null ? '暂无数据' : `¥${Number(data.avg_salary).toLocaleString()}`;
    $('#data-note').textContent = `样本收录日期 ${data.first_date || '—'} 至 ${data.last_date || '—'} · 薪资有效样本 ${data.salary_samples.toLocaleString()} 条 · 不代表实时全市场`;
    const chart = $('#city-chart'); chart.replaceChildren();
    const max = Math.max(...data.top_cities.map(row => row.count), 1);
    for (const city of data.top_cities) {
      const row = node('div','bar-row'), track = node('div','bar-track'), fill = node('div','bar-fill');
      fill.style.width = `${city.count / max * 100}%`; track.append(fill);
      row.append(node('span','',city.name),track,node('span','',city.count.toLocaleString())); chart.append(row);
    }
    const list = $('#category-list'); list.replaceChildren();
    data.top_categories.slice(0,5).forEach((item,index) => {
      const row = node('div','category-row'), name = node('span'); name.append(node('i','rank',String(index+1)),document.createTextNode(item.name));
      row.append(name,node('span','',`${item.count.toLocaleString()} 个岗位`)); list.append(row);
    });
  } catch (error) { toast(error.message); }
}
function addAnswer(data) {
  const block = node('article','message assistant'), meta = node('div','answer-meta');
  meta.append(node('span','',data.route === 'sql' ? '▥ 数据查询' : '✧ 岗位检索'),node('span','',data.mode === 'demo' ? '演示模式' : '模型模式'),node('span','',`${(data.elapsed_ms/1000).toFixed(2)}s`));
  block.append(meta,node('div','answer-body',data.answer));
  if (data.rows.length) {
    const wrap = node('div','table-wrap'), table = node('table'), head = node('tr'), thead = node('thead'), body = node('tbody');
    data.columns.forEach(key => head.append(node('th','',labels[key] || key))); thead.append(head); table.append(thead);
    data.rows.forEach(row => { const tr = node('tr'); data.columns.forEach(key => tr.append(node('td','',row[key] === null ? '—' : String(row[key])))); body.append(tr); });
    table.append(body); wrap.append(table); block.append(wrap);
    if (data.truncated) block.append(node('p','muted','结果达到返回上限，可能仍有更多匹配项。'));
  }
  if (data.sources.length) {
    const details = node('details'), summary = node('summary','',`查看 ${data.sources.length} 条岗位依据`); details.append(summary);
    data.sources.forEach((source,index) => {const card = node('div','source-card'); card.append(node('strong','',`[${index+1}] ${source.title} · ${source.company}`),node('p','',source.content),node('small','',`岗位 #${source.job_id} · RRF ${source.score.toFixed(4)}`)); details.append(card);});
    block.append(details);
  }
  if (data.sql || data.attempts.length) {
    const details = node('details'); details.append(node('summary','',`查询过程 · ${data.attempts.length} 次尝试`));
    if (data.sql) details.append(node('pre','',data.sql));
    data.attempts.forEach(item => details.append(node('p','',`第 ${item.attempt} 次：${item.status === 'success' ? '执行成功' : item.status === 'template' ? '模板查询成功' : item.error}`)));
    block.append(details);
  }
  block.append(node('p','muted',data.route_reason)); $('#messages').append(block); scrollChat();
}
async function sendQuestion(question) {
  if (busy || question.trim().length < 2) return;
  busy = true; $('#send').disabled = true; $('#clear').disabled = true; $('#welcome')?.remove();
  const user = node('article','message user'); user.append(node('div','user-text',question)); $('#messages').append(user);
  const thinking = node('div','thinking','正在分析问题并查询岗位数据…'); $('#messages').append(thinking); $('#question').value = ''; scrollChat();
  try { const data = await api('/api/chat',{method:'POST',body:JSON.stringify({question,mode})}); thinking.remove(); addAnswer(data); }
  catch (error) { thinking.remove(); const block = node('article','message error'); block.append(node('div','answer-body',error.message)); $('#messages').append(block); scrollChat(); }
  finally { busy = false; $('#send').disabled = false; $('#clear').disabled = false; $('#question').focus(); }
}
const welcomeMarkup = $('#welcome').cloneNode(true);
$('#chat-form').addEventListener('submit', event => {event.preventDefault(); sendQuestion($('#question').value.trim());});
$('#question').addEventListener('keydown', event => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); sendQuestion($('#question').value.trim());}});
$('#messages').addEventListener('click', event => {const button = event.target.closest('[data-question]'); if (button) sendQuestion(button.dataset.question);});
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => { mode = button.dataset.mode; document.querySelectorAll('[data-mode]').forEach(item => item.classList.toggle('active',item === button)); $('#mode-hint').textContent = mode === 'auto' ? '自动选择岗位检索或数据库查询' : mode === 'rag' ? '检索岗位资料并展示引用依据' : '查询数据库中的统计与岗位数据'; }));
$('#clear').addEventListener('click', () => {if (!busy) $('#messages').replaceChildren(welcomeMarkup.cloneNode(true));});
$('#rebuild').addEventListener('click', async () => {try {await api('/api/index/rebuild',{method:'POST'}); toast('索引已开始构建，完成后会自动更新状态。'); refreshHealth();} catch(error) {toast(error.message);}});
$('#nav-data').addEventListener('click', () => { $('#metrics').scrollIntoView({behavior:'smooth'}); $('#metrics').classList.remove('flash'); requestAnimationFrame(() => $('#metrics').classList.add('flash')); });
$('#nav-chat').addEventListener('click', () => { $('#chat-form').scrollIntoView({behavior:'smooth',block:'center'}); $('#question').focus({preventScroll:true}); });
$('#access-key').addEventListener('click', () => {const value = prompt('如服务配置了 SERVICE_API_KEY，请输入访问密钥（仅保存在当前标签页会话）：',accessKey); if(value !== null) {accessKey = value.trim(); sessionStorage.setItem('career-access-key',accessKey); refreshHealth(); loadOverview();}});
refreshHealth(); loadOverview();
