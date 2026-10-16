import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Sparkles, X, Settings2, ArrowUp, Square, Plus, Paperclip, Check, Loader2, Link, Upload, RotateCcw, ChevronDown, History } from 'lucide-react'
import { api, copyText, uploadFile } from '../api'
import './agent.css'

const uid = () => crypto.randomUUID().replaceAll('-', '')
export const STATUS = { awaiting_approval: '等待批准', awaiting_sample: '样图待确认', queued: '排队中', pending: '待处理', running: '执行中', stopping: '停止中', completed: '已完成', cancelled: '已停止', paused: '已暂停', unknown: '结果待查询', failed: '失败', import_failed: '待恢复入库', undone: '已撤销' }
const CONN = { connected: 'Codex 已连接', disconnected: '未连接', not_installed: '未安装 Codex', not_logged_in: 'Codex 未登录', connecting: '连接中', error: '连接失败' }
const img = id => `/file/${id}`

export function FullPreview({ src, title, onClose }) {
  useEffect(() => { const key = e => { if (e.key === 'Escape') { e.stopImmediatePropagation(); onClose() } }; window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true) }, [onClose])
  return createPortal(<div className="agent-preview" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}><header><strong>{title}</strong><span>适应窗口 · Esc 关闭</span><button className="btn btn-icon" aria-label="关闭预览" onClick={onClose}><X size={18}/></button></header><div><img src={src} alt={title} onClick={e => e.stopPropagation()} /></div></div>, document.body)
}

export function AgentResults({ plan, onTasks }) {
  const [preview, setPreview] = useState(null)
  const result = plan?.items?.find(i => i.status === 'completed' && i.asset_id && i.job_id)
  if (!result) return null
  const original = result.references?.[0]
  return <section className="agent-results"><header><strong>本次任务 · {plan.title}</strong><button className="btn btn-ghost btn-sm" onClick={onTasks}>查看任务与结果 →</button></header><div className="agent-comparison">{original && <button onClick={() => setPreview({ src: img(original.id), title: '原图 · ' + original.name })}><span>原图</span><img src={img(original.id)} alt="原图"/></button>}<button onClick={() => setPreview({ src: img(result.asset_id), title: '生成结果' })}><span className="accent">{plan.status === 'awaiting_sample' ? '样图 · 等待确认' : '生成结果'}</span><img src={img(result.asset_id)} alt="生成结果"/></button></div>{preview && <FullPreview {...preview} onClose={() => setPreview(null)}/>}</section>
}

export function AgentPanel({ selectedIds, scope, onClose, onChanged, onPlan, requestedTab }) {
  const [tab, setTab] = useState('chat'), [connection, setConnection] = useState({ state: 'disconnected' })
  const [session, setSession] = useState(null), [plans, setPlans] = useState([]), [skills, setSkills] = useState([])
  const [skillIds, setSkillIds] = useState(['needs-analysis', 'batch-edit']), [text, setText] = useState('')
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [settings, setSettings] = useState(false)
  const [refs, setRefs] = useState([]), [attached, setAttached] = useState([]), [preview, setPreview] = useState(null)
  const [editing, setEditing] = useState(null), [history, setHistory] = useState(null)
  const viewId = useRef(uid()), messagesEnd = useRef(null), scroll = useRef(null), stick = useRef(true), lastChange = useRef('')
  const selectedKey = JSON.stringify([...new Set([...selectedIds, ...attached])])
  const refreshRef = useRef(onChanged), planRef = useRef(onPlan)
  refreshRef.current = onChanged; planRef.current = onPlan

  useEffect(() => { if (requestedTab) setTab(requestedTab.tab) }, [requestedTab])
  useEffect(() => {
    let alive = true
    async function init() {
      try {
        const [status, list, sk] = await Promise.all([api.get('/api/agent/status'), api.get('/api/agent/sessions'), api.get('/api/agent/skills')])
        if (!alive) return
        setConnection(status); setSkills(sk)
        const saved = localStorage.getItem('agent-session-' + status.library_id)
        const s = list.find(s => s.id === saved) || list[0] || await api.post('/api/agent/sessions')
        if (alive) { setSession(s); localStorage.setItem('agent-session-' + status.library_id, s.id) }
      } catch (e) { if (alive) setError(e.message) }
    }
    init(); return () => { alive = false }
  }, [])
  useEffect(() => {
    let alive = true
    const ids = JSON.parse(selectedKey)
    const heartbeat = () => api.post('/api/agent/context', { view_id: viewId.current, selected_ids: ids, scope }).catch(e => alive && setError(e.message))
    heartbeat()
    Promise.all(ids.slice(0, 12).map(id => api.get('/api/assets/' + id).catch(() => null))).then(a => alive && setRefs(a.filter(Boolean)))
    const timer = setInterval(heartbeat, 30000)
    return () => { alive = false; clearInterval(timer) }
  }, [selectedKey, scope])
  useEffect(() => {
    if (!session?.id) return
    let alive = true, timer
    async function poll() {
      try {
        const [s, p, c] = await Promise.all([api.get('/api/agent/sessions/' + session.id), api.get('/api/agent/plans'), api.get('/api/agent/status')])
        if (!alive) return
        setSession(s); setPlans(p); setConnection(c)
        planRef.current(p.find(p => p.kind === 'generation' && p.items.some(i => i.asset_id)) || null)
        const signature = p.map(p => `${p.id}:${p.status}:${p.items.map(i => i.asset_id || i.status).join(',')}`).join('|')
        if (lastChange.current && signature !== lastChange.current) refreshRef.current()
        lastChange.current = signature
      } catch (e) { if (alive) setError(e.message) }
      if (alive) timer = setTimeout(poll, 1000)
    }
    poll(); return () => { alive = false; clearTimeout(timer) }
  }, [session?.id])
  useEffect(() => { if (stick.current) messagesEnd.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [session?.messages, plans.length])
  useEffect(() => {
    if (!session?.id) return
    const controller = new AbortController()
    let cursor = 0, timer, refreshTimer, alive = true
    async function listen() {
      try {
        const res = await fetch(`/api/agent/sessions/${session.id}/stream?after=${cursor}`, { signal: controller.signal })
        if (!res.ok || !res.body) throw new Error('stream unavailable')
        const reader = res.body.getReader(), decoder = new TextDecoder()
        let pending = ''
        while (alive) {
          const part = await reader.read(); if (part.done) break
          pending += decoder.decode(part.value, { stream: true })
          let boundary
          while ((boundary = pending.indexOf('\n\n')) >= 0) {
            const chunk = pending.slice(0, boundary); pending = pending.slice(boundary + 2)
            if (chunk.startsWith('data: ')) {
              const event = JSON.parse(chunk.slice(6)); cursor = event.seq
              if (!refreshTimer) refreshTimer = setTimeout(async () => { refreshTimer = null; try { const s = await api.get('/api/agent/sessions/' + session.id); if (alive) setSession(s) } catch {} }, 200)
            }
          }
        }
      } catch { /* Ordinary polling remains a fallback. */ }
      if (alive) timer = setTimeout(listen, 3000)
    }
    listen()
    return () => { alive = false; controller.abort(); clearTimeout(timer); clearTimeout(refreshTimer) }
  }, [session?.id])

  const action = async fn => { setError(''); setBusy(true); try { return await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const connect = () => action(async () => { setConnection(c => ({ ...c, state: 'connecting' })); try { setConnection(await api.post('/api/agent/connect')) } catch (e) { setConnection(c => ({ ...c, state: 'error' })); throw e } })
  const send = () => action(async () => {
    if (!text.trim() || !session) return
    await api.post('/api/agent/context', { view_id: viewId.current, selected_ids: JSON.parse(selectedKey), scope })
    setSession(await api.post(`/api/agent/sessions/${session.id}/message`, { text, view_id: viewId.current, skill_ids: skillIds, request_id: uid() }))
    setText(''); setAttached([]); stick.current = true
  })
  const updatePlan = (p, verb, body = {}) => action(async () => { await api.post(`/api/agent/plans/${p.id}/${verb}`, body); setPlans(await api.get('/api/agent/plans')); onChanged() })
  const newChat = () => action(async () => { const s = await api.post('/api/agent/sessions'); setSession(s); setTab('chat'); setHistory(null); localStorage.setItem('agent-session-' + connection.library_id, s.id) })
  const importFile = e => {
    const file = e.target.files?.[0]; e.target.value = ''; if (!file) return
    action(async () => { const res = await fetch('/api/agent/skills/import?name=' + encodeURIComponent(file.name), { method: 'POST', body: file }); const data = await res.json(); if (!res.ok) throw new Error(data.detail || '导入失败'); setSkills(await api.get('/api/agent/skills')); setEditing(data) })
  }
  const visiblePlans = tab === 'chat' ? plans.filter(p => p.session_id === session?.id) : plans
  const importFolder = e => {
    const files = [...e.target.files]; e.target.value = ''; if (!files.length) return
    action(async () => {
      if (files.length > 100 || files.reduce((n, f) => n + f.size, 0) > 2 * 1024 * 1024) throw new Error('技能目录最多 100 个文件、总计 2 MB')
      const items = []
      for (const file of files) { const b = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (const byte of b) binary += String.fromCharCode(byte); items.push({ name: file.webkitRelativePath, data: btoa(binary) }) }
      const data = await api.post('/api/agent/skills/import-folder', { files: items }); setSkills(await api.get('/api/agent/skills')); setEditing(data)
    })
  }
  return <aside className="agent-panel" aria-label="灵图助手">
    <header className="agent-heading"><Sparkles size={23} className="agent-mark"/><strong>灵图助手</strong><span className={`agent-connection ${connection.state === 'connected' ? 'online' : ''}`}><i/>{CONN[connection.state] || connection.state}</span><button className="btn btn-icon btn-ghost" onClick={() => setSettings(v => !v)} aria-label="助手连接设置"><Settings2 size={17}/></button><button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="收起助手"><X size={17}/></button></header>
    <nav className="agent-tabs">{[['chat', '对话'], ['tasks', '任务'], ['skills', '技能']].map(([id, label]) => <button key={id} data-on={tab === id} onClick={() => { setTab(id); setEditing(null) }}>{label}</button>)}</nav>
    {settings && <section className="agent-connect-box"><strong>本机 Codex 连接</strong><p>{connection.version || '使用本机已登录的 Codex CLI'}。未安装时先安装 Codex CLI，并运行 codex login。</p><div className="agent-row"><button className="btn btn-sm" disabled={busy} onClick={connect}><Link size={13}/>{connection.state === 'connected' ? '检测连接' : '连接 Codex'}</button><button className="btn btn-sm" disabled={busy} onClick={() => action(async () => setConnection(await api.post('/api/agent/disconnect')))}>断开</button></div><button className="btn btn-sm" onClick={() => action(async () => copyText(JSON.stringify(await api.get('/api/agent/mcp-config'), null, 2)))}>复制外部 MCP 配置</button><small>配置含本机连接令牌，仅粘贴到本机 MCP 设置；重启后重新复制。DeepSeek 适配将后续提供。</small></section>}
    {(error || session?.error) && <div className="agent-error" role="alert">{error || session?.error}<button aria-label="关闭错误" onClick={() => { setError(''); setSession(s => ({ ...s, error: '' })) }}><X size={13}/></button></div>}
    <div className="agent-scroll" ref={scroll} onScroll={() => { const el = scroll.current; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100 }}>
      {tab === 'chat' && <><div className="agent-chat-tools"><button className="btn btn-sm btn-ghost" onClick={newChat} disabled={busy || session?.running}><Plus size={13}/>新对话</button><button className="btn btn-sm btn-ghost" onClick={() => action(async () => setHistory(await api.get('/api/agent/sessions')))}><History size={13}/>历史</button></div>
        {history && <div className="agent-history">{history.map(s => <button key={s.id} onClick={() => { setSession(s); setHistory(null); localStorage.setItem('agent-session-' + connection.library_id, s.id) }}>{s.messages.find(m => m.role === 'user')?.text || '新对话'}</button>)}</div>}
        <div className="agent-context"><div className="agent-ref-images">{refs.slice(0, 4).map(a => <button key={a.id} title={a.name} onClick={() => setPreview({ src: img(a.id), title: a.name })}><img src={img(a.id)} alt={a.name}/></button>)}</div><span>{JSON.parse(selectedKey).length ? `已引用 ${JSON.parse(selectedKey).length} 张素材` : '选择图库素材作为参考'}</span></div>
        {!session?.messages.length && <div className="agent-welcome"><Sparkles size={28}/><h3>把想法交给灵图</h3><p>选中素材，告诉我想改哪里。<br/>我会分析图片、生成计划，先试一张再批量执行。</p>{['给所选图片更换背景，保留人物和服装，先试一张。', '分析所选素材，建议分类和标签，先给我整理计划。'].map(t => <button key={t} onClick={() => setText(t)}>{t}</button>)}{connection.state !== 'connected' && <button className="btn agent-primary" onClick={connect} disabled={busy}>连接本机 Codex</button>}</div>}
        {session?.messages.map(m => <div className={`agent-message ${m.role}`} key={m.id}><small>{m.role === 'user' ? '你' : '灵图助手'}{m.selected_ids?.length ? ` · 引用 ${m.selected_ids.length} 张` : ''}</small><div>{m.text || '…'}</div></div>)}
        {session?.running && <div className="agent-working"><Loader2 size={14} className="animate-spin"/>正在分析需求与执行工具…</div>}</>}
      {(tab === 'tasks' || tab === 'chat') && <div>{visiblePlans.map(p => <PlanCard key={p.id} plan={p} busy={busy} onAction={updatePlan} onPreview={setPreview} onAdjust={() => { setTab('chat'); setText(`调整“${p.title}”：`); }} />)}{tab === 'tasks' && !plans.length && <div className="agent-empty">还没有任务。在对话里描述需求，助手会先创建计划。</div>}</div>}
      {tab === 'skills' && <><div className="agent-skill-intro"><strong>技能库</strong><p>技能教助手如何分析和操作。启用后可在对话中选择，下次发送消息生效。</p><label className="btn btn-sm"><Upload size={14}/>导入 SKILL.md / ZIP<input type="file" accept=".md,.zip" hidden onChange={importFile}/></label><label className="btn btn-sm"><Upload size={14}/>导入目录<input type="file" webkitdirectory="" multiple hidden onChange={importFolder}/></label></div>{skills.map(s => <div className="agent-skill" key={s.id}><header><Sparkles size={17}/><strong>{s.name}</strong><label><input type="checkbox" checked={s.enabled} disabled={busy || !s.compatible} aria-label={`启用${s.name}`} onChange={e => action(async () => { await api.patch('/api/agent/skills/' + s.id, { enabled: e.target.checked, revision: s.revision }); setSkills(await api.get('/api/agent/skills')) })}/>启用</label></header><p>{s.description}</p><small>{s.source} · {s.compatible ? '声明式技能' : s.reason}</small><button className="btn btn-sm" onClick={() => setEditing({ ...s })}>查看 / 编辑</button></div>)}</>}
      <div ref={messagesEnd}/>
    </div>
    {tab === 'chat' && <div className="agent-composer"><textarea aria-label="描述助手任务" placeholder="描述你想完成的任务…" value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send() } }}/><div className="agent-composer-tools"><label className="btn btn-icon btn-ghost" title="导入本地参考图"><Paperclip size={17}/><input type="file" accept="image/*" hidden multiple onChange={e => { const files = [...e.target.files]; e.target.value = ''; action(async () => { const ids = []; for (const file of files.slice(0, 8)) { const r = await uploadFile(file, null, () => {}); if (!r.asset_id) throw new Error(r.message || '导入失败'); ids.push(r.asset_id) }; setAttached(a => [...new Set([...a, ...ids])]); onChanged() }) }}/></label><details className="agent-skill-select"><summary><Sparkles size={13}/>技能<ChevronDown size={12}/></summary><div>{skills.filter(s => s.enabled && s.compatible).map(s => <label key={s.id}><input type="checkbox" checked={skillIds.includes(s.id)} onChange={e => setSkillIds(a => e.target.checked ? [...a, s.id] : a.filter(id => id !== s.id))}/>{s.name}</label>)}</div></details><span className="agent-engine">Codex</span>{session?.running ? <button className="btn agent-send" aria-label="停止助手" onClick={() => action(async () => setSession(await api.post(`/api/agent/sessions/${session.id}/stop`)))}><Square size={15}/></button> : <button className="btn agent-send" disabled={busy || !text.trim() || connection.state !== 'connected'} onClick={send} aria-label="发送任务"><ArrowUp size={18}/></button>}</div><small>Ctrl + Enter 发送 · 生图与整理需确认具体计划</small></div>}
    {editing && createPortal(<div className="agent-edit-overlay"><section role="dialog" aria-modal="true" aria-label="编辑技能"><header><strong>{editing.name} · SKILL.md</strong><button className="btn btn-icon" aria-label="关闭技能编辑" onClick={() => setEditing(null)}><X size={17}/></button></header><textarea aria-label="技能内容" value={editing.text} onChange={e => setEditing(s => ({ ...s, text: e.target.value }))}/>{error && <p className="agent-error" role="alert">{error}</p>}<p>{editing.source} · {editing.compatible ? '保存后对下一次消息生效' : editing.reason}</p><footer>{editing.builtin && <button className="btn" disabled={busy} onClick={() => action(async () => { setEditing(await api.patch('/api/agent/skills/' + editing.id, { revision: editing.revision, reset: true })); setSkills(await api.get('/api/agent/skills')) })}>恢复内置版本</button>}<button className="btn agent-primary" disabled={busy} onClick={() => action(async () => { await api.patch('/api/agent/skills/' + editing.id, { text: editing.text, revision: editing.revision }); setSkills(await api.get('/api/agent/skills')); setEditing(null) })}>保存技能</button></footer></section></div>, document.body)}
    {preview && <FullPreview {...preview} onClose={() => setPreview(null)}/>}
  </aside>
}

function PlanCard({ plan: p, busy, onAction, onPreview, onAdjust }) {
  const done = p.items.filter(i => i.status === 'completed').length, sample = p.items.find(i => i.asset_id && i.job_id), waiting = ['awaiting_approval', 'awaiting_sample'].includes(p.status)
  return <section className="agent-plan"><header><Sparkles size={17}/><strong>{p.title}</strong><span>{STATUS[p.status] || p.status}</span></header><div className="agent-plan-meta">{p.kind === 'generation' ? `${p.profile_name} · ${p.items.length} 张 · ${p.sample_first ? '先生成样图' : '整批执行'}` : `图库整理 · ${p.items.length} 项`}</div><div className="agent-progress"><span style={{ width: `${done / p.items.length * 100}%` }}/></div><small>已完成 {done} / {p.items.length}{p.kind === 'generation' ? ' · 原图保留 · 结果待审核' : ''}</small>{p.kind === 'generation' && waiting && <p className="agent-cost">{p.cost}</p>}
    {sample && <button className="agent-sample" onClick={() => onPreview({ src: img(sample.asset_id), title: p.title + ' · 样图' })}><img src={img(sample.asset_id)} alt="样图"/><span><Check size={17}/><strong>{p.status === 'awaiting_sample' ? '样图已就绪' : '查看生成结果'}</strong><small>点击查看完整图片</small></span></button>}{p.error && <p className="agent-error">{p.error}</p>}
    <details className="agent-plan-details"><summary>查看逐项指令与结果</summary>{p.items.map((i, index) => <div key={i.id}><strong>{index + 1}. {STATUS[i.status] || i.status}</strong><p>{i.prompt || (i.changes ? JSON.stringify({ name: i.name, changes: i.changes }) : i.name)}</p>{i.error && <p className="agent-error">{i.error}</p>}{i.asset_id && i.job_id && <><button className="agent-result-thumb" onClick={() => onPreview({ src: img(i.asset_id), title: `结果 ${index + 1}` })}><img src={img(i.asset_id)} alt={`结果 ${index + 1}`}/></button><label>审核 <select className="input" value={i.review || 'pending'} onChange={e => onAction(p, 'review', { item_id: i.id, review: e.target.value })}><option value="pending">待审核</option><option value="accepted">保留</option><option value="rejected">不采用（保留文件）</option></select></label></>}{['unknown', 'failed', 'import_failed'].includes(i.status) && <button className="btn btn-sm" disabled={busy} onClick={() => onAction(p, 'recover', { item_id: i.id })}><RotateCcw size={12}/>恢复查询 / 入库</button>}</div>)}</details>
    {waiting && <div className="agent-plan-buttons"><button className="btn agent-primary" disabled={busy} onClick={() => onAction(p, 'approve', { token: p.approval_token, revision: p.revision })}><Check size={14}/>{p.status === 'awaiting_sample' ? `满意，继续 ${p.items.filter(i => i.status === 'pending').length} 张` : p.kind === 'generation' ? p.sample_first ? '批准生成首张样图' : `批准生成 ${p.items.length} 张` : '批准执行整理'}</button>{p.kind === 'generation' && <button className="btn" onClick={onAdjust}>调整要求</button>}</div>}{!['completed', 'cancelled', 'undone'].includes(p.status) && <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => onAction(p, 'cancel')}>停止此计划</button>}{['organize', 'create_folder'].includes(p.kind) && p.status === 'completed' && <button className="btn btn-sm" disabled={busy} onClick={() => onAction(p, 'undo')}><RotateCcw size={13}/>撤销本次整理</button>}
  </section>
}
