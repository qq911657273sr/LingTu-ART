import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Images, Inbox, Star, Trash2, Settings as SettingsIcon, Search, X, Upload, Plus, Folder, FolderOpen, ChevronRight, ChevronDown,
  MoreHorizontal, Pencil, ArrowUp, ArrowDown, FolderPlus, Film, Image as ImageIcon, ArrowDownWideNarrow, ArrowUpNarrowWide, Moon, Sun,
  PanelRightOpen, Check, Tag, TagsIcon, Download, RotateCcw, FolderInput, CircleAlert, Play, FilterX, Maximize, Minimize, Sparkles, HardDrive, CircleCheck, ClipboardCopy,
} from 'lucide-react'
import { api, qs, fmtDur, fmtSize, copyText, OFFLINE } from './api'
import { AskHost, ToastHost, Modal, useAsk, useToast, flattenFolders, FolderSelect } from './ui'
import { useImporter, ImportPanel, ImportChooser } from './Importer'
import { Viewer } from './Viewer'
import { Inspector } from './Inspector'
import { Settings, Offline } from './Settings'
import { AIEditor } from './AIEditor'
import { AgentPanel, AgentResults } from './agent/AgentPanel'

const PAGE = 120
const LS = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }

export default function App() {
  return <ToastHost><AskHost><div className="desktop-shell"><div className="desktop-workbench"><Workbench /></div></div></AskHost></ToastHost>
}

function Workbench() {
  const toast = useToast()
  const ask = useAsk()
  const [sidebar, setSidebar] = useState(null)
  const [scope, setScope] = useState('all')
  const [q, setQ] = useState('')
  const [qLive, setQLive] = useState('')
  const [kind, setKind] = useState('')
  const [favOnly, setFavOnly] = useState(false)
  const [sort, setSort] = useState(LS('sort', 'imported'))
  const [order, setOrder] = useState(LS('order', 'desc'))
  const [size, setSize] = useState(LS('thumbSize', 180))
  const [fit, setFit] = useState(LS('thumbFit', 'cover'))
  const [showInspector, setShowInspector] = useState(LS('inspector', true))
  const [theme, setTheme] = useState(() => LS('theme', 'light'))
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadErr, setLoadErr] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [focus, setFocus] = useState(null)
  const [viewer, setViewer] = useState(null)
  const [aiOpen, setAIOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)
  const [agentPlan, setAgentPlan] = useState(null)
  const [agentTab, setAgentTab] = useState(null)
  const [aiSource, setAISource] = useState(null)
  const openAI = a => { setAISource(a ? { ...a } : null); setAIOpen(true) }
  const [importOpen, setImportOpen] = useState(false)
  const [importFolder, setImportFolder] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const reqId = useRef(0)
  const [version, setVersion] = useState(0)
  const anchor = useRef(null)

  useEffect(() => localStorage.setItem('sort', JSON.stringify(sort)), [sort])
  useEffect(() => localStorage.setItem('order', JSON.stringify(order)), [order])
  useEffect(() => localStorage.setItem('thumbSize', JSON.stringify(size)), [size])
  useEffect(() => localStorage.setItem('thumbFit', JSON.stringify(fit)), [fit])
  useEffect(() => localStorage.setItem('inspector', JSON.stringify(showInspector)), [showInspector])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme === 'night' ? 'dark' : 'light'
    localStorage.setItem('theme', JSON.stringify(theme))
  }, [theme])
  useEffect(() => { const t = setTimeout(() => setQ(qLive.trim()), 250); return () => clearTimeout(t) }, [qLive])

  const [offline, setOffline] = useState(false)
  const loadSidebar = useCallback(() => api.get('/api/sidebar').then((d) => { setSidebar(d); setOffline(false) })
    .catch((e) => (e.message === OFFLINE ? setOffline(true) : toast(e.message, 'error'))), [toast])
  // 服务窗口被关掉时明确提示，恢复后自动重连
  useEffect(() => {
    const t = setInterval(() => fetch('/api/ping').then(() => offline && (loadSidebar(), loadPage(0, false))).catch(() => setOffline(true)), 5000)
    return () => clearInterval(t)
  }, [offline, loadSidebar]) // eslint-disable-line
  const filters = { scope, q, kind, favorite: favOnly }
  const filterKey = JSON.stringify([scope, q, kind, favOnly, sort, order])

  const loadPage = useCallback(async (offset, keep) => {
    const id = ++reqId.current
    setLoading(true)
    try {
      const d = await api.get(`/api/assets?${qs({ scope, q, kind, favorite: favOnly, sort, order, offset, limit: PAGE })}`)
      if (id !== reqId.current) return
      setTotal(d.total)
      setItems((prev) => (keep ? [...prev.slice(0, offset), ...d.items] : d.items))
      setLoadErr(null)
    } catch (e) {
      if (id === reqId.current) setLoadErr(e.message)
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [filterKey]) // eslint-disable-line

  useEffect(() => { loadSidebar() }, [loadSidebar])
  useEffect(() => { setSelected(new Set()); setFocus(null); loadPage(0, false) }, [loadPage])

  const loadMore = useCallback(() => { if (!loading && items.length < total) loadPage(items.length, true) }, [loading, items.length, total, loadPage])
  /** 刷新当前已加载范围（保持滚动位置） */
  const refresh = useCallback(async (dropFocus) => {
    loadSidebar()
    setVersion((v) => v + 1)
    const id = ++reqId.current
    try {
      const want = Math.max(PAGE, items.length)
      let d = { items: [], total: 0 }
      for (let off = 0; off < want; off += 500) {
        const part = await api.get(`/api/assets?${qs({ scope, q, kind, favorite: favOnly, sort, order, offset: off, limit: Math.min(500, want - off) })}`)
        d = { items: [...d.items, ...part.items], total: part.total }
        if (off + 500 >= part.total) break
      }
      if (id !== reqId.current) return
      setItems(d.items)
      setTotal(d.total)
      if (dropFocus) {
        const alive = new Set(d.items.map((i) => i.id))
        setSelected((s) => new Set([...s].filter((x) => alive.has(x))))
        setFocus((f) => (alive.has(f) ? f : null))
      }
    } catch (e) { toast(e.message, 'error') }
  }, [filterKey, items.length, loadSidebar, toast]) // eslint-disable-line

  // 后台缩略图：轮询未生成的
  useEffect(() => {
    const pending = items.filter((i) => i.thumb_state === 0).map((i) => i.id).slice(0, 500)
    if (!pending.length) return
    const t = setTimeout(async () => {
      try {
        const st = await api.post('/api/thumb-states', pending)
        setItems((prev) => prev.map((i) => (st[i.id] !== undefined && st[i.id] !== i.thumb_state ? { ...i, thumb_state: st[i.id] } : i)))
        loadSidebar()
      } catch { /* 下次再试 */ }
    }, 1200)
    return () => clearTimeout(t)
  }, [items, loadSidebar])

  const importer = useImporter(useMemo(() => {
    let t
    return () => { clearTimeout(t); t = setTimeout(() => refreshRef.current(), 400) }
  }, []))
  const refreshRef = useRef(refresh)
  refreshRef.current = refresh

  const currentFolder = scope.startsWith('folder:') ? Number(scope.slice(7)) : null
  const startImport = (files, folderId) => {
    if (!files?.length) return
    importer.add(files, folderId)
    setImportOpen(false)
  }

  // 整窗拖放导入
  useEffect(() => {
    const isFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files')
    const over = (e) => { if (isFiles(e)) { e.preventDefault(); setDragOver(true) } }
    const leave = (e) => { if (!e.relatedTarget) setDragOver(false) }
    const drop = (e) => { if (isFiles(e)) { e.preventDefault(); setDragOver(false); startImport(e.dataTransfer.files, currentFolder) } }
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => { window.removeEventListener('dragover', over); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop) }
  })

  // 选择
  const click = (e, idx) => {
    const id = items[idx].id
    if (e.shiftKey && anchor.current != null) {
      const [a, b] = [Math.min(anchor.current, idx), Math.max(anchor.current, idx)]
      setSelected(new Set(items.slice(a, b + 1).map((i) => i.id)))
    } else if (e.ctrlKey || e.metaKey) {
      const s = new Set(selected)
      s.has(id) ? s.delete(id) : s.add(id)
      setSelected(s)
      anchor.current = idx
    } else {
      setSelected(new Set([id]))
      anchor.current = idx
    }
    setFocus(id)
  }
  const toggle = (idx) => {
    const id = items[idx].id
    const s = new Set(selected)
    s.has(id) ? s.delete(id) : s.add(id)
    setSelected(s)
    anchor.current = idx
    setFocus(id)
  }
  const selectAll = async () => {
    try { setSelected(new Set(await api.get(`/api/asset-ids?${qs(filters)}`))) } catch (e) { toast(e.message, 'error') }
  }

  // 快捷键
  useEffect(() => {
    const k = (e) => {
      if (aiOpen || viewer != null || e.target.closest?.('input,textarea,select,[role=dialog]')) return
      const idx = items.findIndex((i) => i.id === focus)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); selectAll() }
      else if (e.key === 'Escape') setSelected(new Set())
      else if ((e.key === ' ' || e.key === 'Enter') && idx >= 0) { e.preventDefault(); setViewer(idx) }
      else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && items.length) {
        e.preventDefault()
        const n = Math.max(0, Math.min(items.length - 1, idx + (e.key === 'ArrowRight' ? 1 : -1)))
        setFocus(items[n].id); setSelected(new Set([items[n].id])); anchor.current = n
        document.getElementById(`card-${items[n].id}`)?.scrollIntoView({ block: 'nearest' })
        if (n >= items.length - 6) loadMore()
      } else if (e.key === 'Delete' && selected.size) {
        e.preventDefault(); batch(scope === 'trash' ? 'purge' : 'trash')
      }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })

  const ids = [...selected]
  async function batch(action, extra = {}) {
    if (!ids.length) return
    try {
      if (action === 'purge' && !(await ask({ title: '彻底删除', message: `将永久删除 ${ids.length} 个素材的原文件，无法恢复。确定吗？`, ok: '彻底删除', danger: true }))) return
      if (action === 'move') {
        const r = await ask({ title: `移动 ${ids.length} 个素材`, message: '选择目标分类（只修改分类，不搬动文件）：', folders: sidebar.folders, ok: '移动' })
        if (!r) return
        extra.folder_id = r.folder
      }
      if (action === 'tag_add' || action === 'tag_remove') {
        const t = await ask({ title: action === 'tag_add' ? `为 ${ids.length} 个素材添加标签` : `从 ${ids.length} 个素材移除标签`, message: '多个标签用逗号分隔', input: '', placeholder: '例如：沈青, 白衣', ok: action === 'tag_add' ? '添加' : '移除' })
        if (!t) return
        extra.tags = t.split(/[,，;；]/).map((s) => s.trim()).filter(Boolean)
      }
      if (action === 'export') {
        const r = await api.post('/api/export', { ids })
        toast(r.failed.length ? `导出 ${r.exported.length} 个，失败 ${r.failed.length} 个：${r.failed.join('；')}` : `已导出 ${r.exported.length} 个文件到 ${r.dir}`, r.failed.length ? 'error' : 'ok', 7000)
        return
      }
      const r = await api.post('/api/batch', { ids, action, ...extra })
      const msg = { move: '已移动', tag_add: '已添加标签', tag_remove: '已移除标签', favorite: extra.value ? '已收藏' : '已取消收藏', trash: '已移到回收站', restore: '已恢复', purge: '已彻底删除' }[action]
      toast(`${msg}（${r.count} 个）`)
      if (['trash', 'restore', 'purge'].includes(action)) setSelected(new Set())
      refresh(true)
    } catch (e) { toast(e.message, 'error') }
  }

  const clearFilters = () => { setQLive(''); setQ(''); setKind(''); setFavOnly(false) }
  async function cardAction(a, action) {
    try {
      if (action === 'ai_edit') {
        setFocus(a.id)
        openAI(a)
        return
      }
      if (action === 'preview') {
        setFocus(a.id); setViewer(items.findIndex((i) => i.id === a.id)); return
      }
      if (action === 'rename') {
        const name = await ask({ title: '重命名素材', input: a.name, ok: '保存' })
        if (!name || name === a.name) return
        await api.patch(`/api/assets/${a.id}`, { name })
        toast('已重命名')
      } else if (action === 'favorite') {
        await api.patch(`/api/assets/${a.id}`, { favorite: !a.favorite })
        toast(a.favorite ? '已取消收藏' : '已收藏')
      } else if (action === 'move') {
        const r = await ask({ title: `移动“${a.name}”`, message: '选择目标分类：', folders: sidebar.folders, ok: '移动' })
        if (!r) return
        await api.post('/api/batch', { ids: [a.id], action: 'move', folder_id: r.folder })
        toast('已移动')
      } else if (action === 'tag_add') {
        const value = await ask({ title: '添加标签', message: '多个标签用逗号分隔', input: '', placeholder: '例如：场景, 自然', ok: '添加' })
        if (!value) return
        const tags = value.split(/[,，;；]/).map((s) => s.trim()).filter(Boolean)
        if (!tags.length) return
        await api.post('/api/batch', { ids: [a.id], action, tags })
        toast('已添加标签')
      } else if (action === 'export') {
        const r = await api.post('/api/export', { ids: [a.id] })
        if (r.failed.length) throw new Error(r.failed.join('；'))
        toast(`已导出到 ${r.dir}`, 'ok', 6000); return
      } else if (action === 'copy_path') {
        const detail = await api.get(`/api/assets/${a.id}`)
        await copyText(detail.path); toast('已复制完整路径'); return
      } else if (action === 'reveal') {
        const r = await api.post(`/api/assets/${a.id}/reveal`)
        if (r.ok) toast('已在资源管理器中打开')
        else { await copyText(r.path); toast(`${r.message}（已复制完整路径）`, 'info', 6000) }
        return
      } else if (['trash', 'restore', 'purge'].includes(action)) {
        if (action !== 'restore' && !(await ask({ title: action === 'purge' ? '彻底删除' : '移入回收站',
          message: action === 'purge' ? `将永久删除“${a.name}”的原文件，无法恢复。确定吗？` : `将“${a.name}”移入回收站？之后可以恢复。`,
          ok: action === 'purge' ? '彻底删除' : '移入回收站', danger: true }))) return
        await api.post('/api/batch', { ids: [a.id], action })
        toast({ trash: '已移入回收站', restore: '已恢复', purge: '已彻底删除' }[action])
      }
      await refresh(true)
    } catch (e) { toast(e.message, 'error') }
  }
  const hasFilter = !!(qLive || kind || favOnly)
  const focusIndex = items.findIndex((i) => i.id === focus)
  const scopeTitle = scope === 'all' ? '素材库' : scope === 'inbox' ? '待整理' : scope === 'favorites' ? '我的收藏' : scope === 'trash' ? '回收站'
    : flattenFolders(sidebar?.folders || []).find((f) => `folder:${f.id}` === scope)?.path || '素材库'

  if (!sidebar) return offline ? <Offline msg={OFFLINE} onRetry={loadSidebar} /> : <div className="h-full grid place-items-center text-dim">正在连接素材库…</div>
  const libraryEmpty = sidebar.counts.all === 0 && sidebar.counts.trash === 0

  return (
    <div className={`workbench h-full flex ${agentOpen ? 'with-agent' : ''}`}>
      {offline && (
        <div role="alert" className="fixed top-0 inset-x-0 z-[90] flex items-center justify-center gap-3 bg-danger text-white text-[13px] py-2 px-4">
          <CircleAlert size={15} />{OFFLINE}
          <button className="btn btn-sm bg-white/15 border-white/30 text-white hover:bg-white/25" onClick={() => { loadSidebar(); loadPage(0, false) }}>重试</button>
        </div>
      )}
      <Sidebar sidebar={sidebar} scope={scope} setScope={(s) => { setScope(s) }} reload={() => { loadSidebar(); refresh(true) }} theme={theme} onToggleTheme={() => setTheme((v) => v === 'night' ? 'light' : 'night')} onAgent={() => { if (scope === 'settings') setScope('all'); setAgentOpen(true) }}
        onDropAssets={async (folderId, dragIds) => {
          try { const r = await api.post('/api/batch', { ids: dragIds, action: 'move', folder_id: folderId }); toast(`已移动 ${r.count} 个素材`); refresh(true) } catch (e) { toast(e.message, 'error') }
        }} />

      {scope === 'settings' ? (
        <main className="library-main settings-main flex-1 min-w-0" tabIndex={0} aria-label="设置与备份"><Settings onLibraryChanged={() => { setScope('all'); loadSidebar(); loadPage(0, false) }} /></main>
      ) : (
        <main className="library-main flex-1 min-w-0 flex flex-col relative">
          {/* 工具栏 */}
          <div className="library-toolbar flex items-center gap-2 shrink-0 relative z-10">
            <div className="library-heading"><h1 title={scopeTitle}>{scopeTitle}</h1><span>{total.toLocaleString()} 个素材</span></div>
            <div className="library-search relative flex-1 max-w-[420px] min-w-[160px] group/s">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint group-focus-within/s:text-accent transition-colors" />
              <input className="input h-9 pl-9 pr-8 rounded-xl" placeholder="搜索素材、标签、提示词…" value={qLive} onChange={(e) => setQLive(e.target.value)} aria-label="搜索" />
              {qLive && <button className="absolute right-1.5 top-1/2 -translate-y-1/2 text-dim hover:text-fg p-1 cursor-pointer" onClick={() => setQLive('')} aria-label="清空搜索"><X size={14} /></button>}
            </div>
            <button className="btn btn-primary import-button" onClick={() => { setImportFolder(currentFolder); setImportOpen(true) }}><Upload size={15} />导入素材</button>
            <button className="btn" onClick={() => openAI(null)} title="查看 AI 生成任务与结果"><Sparkles size={15} />AI 任务</button>
            {!agentOpen && <button className="btn" onClick={() => setAgentOpen(true)}><Sparkles size={15}/>AI 助手</button>}
            {!showInspector && <button className="btn btn-icon" onClick={() => setShowInspector(true)} title="展开右栏" aria-label="展开右栏"><PanelRightOpen size={16} /></button>}
          </div>

          <ScopeHeader scope={scope} sidebar={sidebar} total={total} loading={loading} q={q}
            kind={kind} setKind={setKind} favOnly={favOnly} setFavOnly={setFavOnly} hasFilter={hasFilter} clearFilters={clearFilters}
            onEmptyTrash={async () => {
              if (await ask({ title: '清空回收站', message: `将永久删除回收站中的 ${sidebar.counts.trash} 个素材及其原文件，无法恢复。`, ok: '清空回收站', danger: true })) {
                const r = await api.post('/api/trash/empty'); toast(`已彻底删除 ${r.count} 个`); refresh(true)
              }
            }}
            onSelectAll={selectAll}>
            <div className="flex items-center gap-1.5">
            <select className="input w-auto h-8" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="排序">
              <option value="imported">最近添加</option>
              <option value="name">名称</option>
              <option value="size">文件大小</option>
            </select>
            <button className="btn btn-icon" onClick={() => setOrder(order === 'asc' ? 'desc' : 'asc')} title={order === 'asc' ? '升序' : '降序'} aria-label={order === 'asc' ? '升序' : '降序'}>
              {order === 'asc' ? <ArrowUpNarrowWide size={15} /> : <ArrowDownWideNarrow size={15} />}
            </button>
            <div className="flex items-center gap-1.5 h-8 pl-2.5 pr-1 rounded-lg border border-border bg-bg/60">
              <input type="range" min={120} max={380} step={10} value={size} onChange={(e) => setSize(+e.target.value)} className="w-20" aria-label="缩略图大小" title="缩略图大小" />
              <button className="btn btn-ghost btn-icon btn-sm w-6 h-6" onClick={() => setFit(fit === 'cover' ? 'contain' : 'cover')}
                title={fit === 'cover' ? '显示完整画面' : '填满卡片'} aria-label={fit === 'cover' ? '显示完整画面' : '填满卡片'}>
                {fit === 'cover' ? <Minimize size={13} /> : <Maximize size={13} />}
              </button>
            </div>
            </div>
          </ScopeHeader>

          {libraryEmpty ? (
            <div className="flex-1 grid place-items-center p-8">
              <div className="w-full max-w-xl anim-rise">
                <div className="inline-flex items-center gap-1.5 chip mb-3 text-accent border-accent/25 bg-accent/10"><Sparkles size={12} />第一步</div>
                <h2 className="text-[22px] font-semibold tracking-tight mb-1.5">开始建立你的素材库</h2>
                <p className="text-dim mb-5 leading-relaxed">把生成的人物、场景、道具图片和视频拖进来。导入时会自动读取尺寸、时长以及 ComfyUI / A1111 的生成参数。</p>
                <ImportChooser big folders={sidebar.folders} folderId={importFolder} setFolderId={setImportFolder} onFiles={(f) => startImport(f, importFolder)} />
              </div>
            </div>
          ) : (
            <Grid items={items} total={total} size={size} fit={fit} selected={selected} focus={focus} loading={loading} loadErr={loadErr}
              onClick={click} onToggle={toggle} onOpen={(i) => setViewer(i)} onMore={loadMore} onAction={cardAction} trash={scope === 'trash'}
              empty={<EmptyResult scope={scope} hasFilter={hasFilter} clear={clearFilters} />} />
          )}

          {agentOpen && agentPlan && <AgentResults plan={agentPlan} onTasks={() => setAgentTab({ tab: 'tasks', id: Date.now() })}/>}
          {selected.size > 1 && !agentOpen && (
            <BatchBar count={selected.size} trash={scope === 'trash'} onAction={batch} onClear={() => setSelected(new Set())} />
          )}
          {dragOver && (
            <div className="absolute inset-3 z-40 rounded-2xl border-2 border-dashed border-accent/70 bg-accent/10 backdrop-blur-[2px] grid place-items-center pointer-events-none anim-fade">
              <div className="text-center"><Upload className="mx-auto mb-2" /><div className="text-[15px] font-medium">松开即可导入</div>
                <div className="text-dim text-xs mt-1">导入到：{currentFolder ? flattenFolders(sidebar.folders).find((f) => f.id === currentFolder)?.path : '待整理'}</div></div>
            </div>
          )}
        </main>
      )}

      {scope !== 'settings' && agentOpen && <AgentPanel selectedIds={[...selected]} scope={scope} onClose={() => setAgentOpen(false)} onChanged={() => refresh(false)} onPlan={setAgentPlan} requestedTab={agentTab}/>}
      {scope !== 'settings' && !agentOpen && showInspector && (
        focus && items.some((i) => i.id === focus)
          ? <Inspector id={focus} version={version} sidebar={sidebar} trash={scope === 'trash'} onChanged={(drop) => refresh(drop)} onOpen={() => setViewer(focusIndex)} onCollapse={() => setShowInspector(false)} />
          : <aside className="asset-inspector shrink-0 bg-panel flex flex-col">
            <div className="inspector-heading flex items-center px-4"><span className="panel-title">素材详情</span>
              <button className="btn btn-ghost btn-icon ml-auto" onClick={() => setShowInspector(false)} aria-label="收起右栏" title="收起右栏"><PanelRightOpen size={16} className="rotate-180" /></button></div>
            <div className="flex-1 grid place-items-center p-8 text-center">
              <div className="anim-rise">
                <div className="mx-auto mb-3 w-12 h-12 rounded-2xl bg-card border border-border grid place-items-center"><ImageIcon size={20} className="text-faint" /></div>
                {selected.size > 1
                  ? <div className="text-dim text-xs leading-relaxed">已选择 <span className="text-fg font-medium">{selected.size}</span> 个素材<br />使用底部操作栏批量处理</div>
                  : <div className="text-dim text-xs leading-relaxed">点击素材查看预览和信息<br /><span className="text-faint">双击或按空格打开大预览</span></div>}
              </div>
            </div>
          </aside>
      )}

      {viewer != null && items[viewer] && (
        <Viewer items={items} index={viewer} total={total} onIndex={(i) => { setViewer(i); setFocus(items[i].id); setSelected(new Set([items[i].id])) }}
          onClose={() => setViewer(null)} onNeedMore={loadMore} onAIEdit={openAI} suspended={aiOpen} />
      )}
      <AIEditor open={aiOpen} source={aiSource} onClose={() => setAIOpen(false)} onSaved={() => refresh(false)} />
      {importOpen && (
        <Modal title="导入素材" width={620} onClose={() => setImportOpen(false)}>
          <ImportChooser folders={sidebar.folders} folderId={importFolder} setFolderId={setImportFolder} onFiles={(f) => startImport(f, importFolder)} />
        </Modal>
      )}
      <ImportPanel importer={importer} />
    </div>
  )
}

function ScopeHeader({ scope, sidebar, total, onEmptyTrash, onSelectAll, children, kind, setKind, favOnly, setFavOnly, hasFilter, clearFilters }) {
  return (
    <div className="library-filters flex items-center gap-2 shrink-0 text-xs text-dim">
      <div className="seg" role="group" aria-label="类型">
        <button data-on={kind === ''} aria-pressed={kind === ''} onClick={() => setKind('')}>全部</button>
        <button data-on={kind === 'image'} aria-pressed={kind === 'image'} onClick={() => setKind('image')}><ImageIcon size={13} />图片</button>
        <button data-on={kind === 'video'} aria-pressed={kind === 'video'} onClick={() => setKind('video')}><Film size={13} />视频</button>
      </div>
      {scope !== 'favorites' && <button className={`btn filter-favorite ${favOnly ? 'is-active' : ''}`} onClick={() => setFavOnly(!favOnly)} aria-pressed={favOnly}><Star size={14} className={favOnly ? 'fill-star' : ''} />收藏</button>}
      {hasFilter && <button className="btn btn-ghost" onClick={clearFilters} title="清空筛选" aria-label="清空筛选"><FilterX size={14} /></button>}
      <span className="flex-1" />
      {total > 0 && <button className="btn btn-ghost btn-sm text-dim" onClick={onSelectAll}>全选 <kbd>Ctrl A</kbd></button>}
      {children}
      {scope === 'trash' && sidebar.counts.trash > 0 && <button className="btn btn-sm btn-danger" onClick={onEmptyTrash}><Trash2 size={13} />清空回收站</button>}
    </div>
  )
}

function EmptyResult({ scope, hasFilter, clear }) {
  const text = hasFilter ? '没有符合条件的素材' : { inbox: '待整理中没有素材', favorites: '还没有收藏的素材', trash: '回收站是空的' }[scope] || '这个分类中还没有素材'
  return (
    <div className="flex-1 grid place-items-center text-center text-dim pb-16">
      <div className="anim-rise">
        <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-card border border-border grid place-items-center">{hasFilter ? <Search size={22} className="text-faint" /> : scope === 'trash' ? <Trash2 size={22} className="text-faint" /> : <Images size={22} className="text-faint" />}</div>
        <div className="mb-3 text-[14px] text-fg/90">{text}</div>
        {hasFilter && <button className="btn" onClick={clear}><FilterX size={14} />清空筛选</button>}
        {!hasFilter && scope.startsWith('folder:') && <div className="text-xs">可以把文件拖到窗口中导入到此分类，或把网格中的素材拖到左侧文件夹上。</div>}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- 网格 */

function Grid({ items, total, size, fit, selected, focus, loading, loadErr, onClick, onToggle, onOpen, onMore, empty, onAction, trash }) {
  const sentinel = useRef()
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver((es) => es[0].isIntersecting && onMore(), { rootMargin: '800px' })
    io.observe(el)
    return () => io.disconnect()
  }, [onMore, items.length])
  if (!loading && !loadErr && items.length === 0) return empty
  return (
    <div className="asset-scroll flex-1 overflow-y-auto">
      {loadErr && <div className="mb-3 flex items-center gap-2 text-danger text-xs"><CircleAlert size={14} />加载失败：{loadErr}</div>}
      <div className="asset-grid grid gap-4" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${size}px), 1fr))` }}>
        {items.map((a, i) => (
          <Card key={a.id} a={a} idx={i} fit={fit} sel={selected.has(a.id)} focus={focus === a.id} selected={selected}
            onClick={onClick} onToggle={onToggle} onOpen={onOpen} onAction={onAction} trash={trash} />
        ))}
        {loading && Array.from({ length: items.length ? 6 : 18 }).map((_, i) => <div key={`s${i}`} className="rounded-xl overflow-hidden bg-card"><div className="skeleton aspect-square" /><div className="p-2.5 space-y-1.5"><div className="skeleton h-3 w-3/4 rounded" /><div className="skeleton h-2.5 w-1/2 rounded" /></div></div>)}
      </div>
      {items.length < total && <div ref={sentinel} className="h-10" />}
      {items.length > 0 && <div className="grid-status">已显示 {items.length.toLocaleString()} / {total.toLocaleString()} 个素材</div>}
    </div>
  )
}

function Card({ a, idx, sel, focus, selected, fit, onClick, onToggle, onOpen, onAction, trash }) {
  const [imgErr, setImgErr] = useState(false)
  const [menu, setMenu] = useState(null)
  const [savingFavorite, setSavingFavorite] = useState(false)
  const menuButton = useRef()
  const bad = a.kind === 'video' && a.playable && a.playable !== 'ok'
  return (
    <div id={`card-${a.id}`} role="button" tabIndex={-1} aria-selected={sel} data-sel={sel} data-focus={focus}
      draggable onDragStart={(e) => {
        const ids = sel ? [...selected] : [a.id]
        e.dataTransfer.setData('application/x-asset-ids', JSON.stringify(ids))
        e.dataTransfer.effectAllowed = 'move'
      }}
      onClick={(e) => onClick(e, idx)} onDoubleClick={() => onOpen(idx)}
      className="card group relative rounded-xl overflow-hidden bg-card cursor-pointer [content-visibility:auto] [contain-intrinsic-size:auto_240px]">
      <div className={`card-thumbnail relative overflow-hidden ${fit === 'contain' ? 'checker' : 'thumb-bg'}`}>
        {a.thumb_state === 1 && !imgErr ? (
          <img src={`/thumb/${a.id}`} alt="" loading="lazy" decoding="async" draggable={false} onError={() => setImgErr(true)}
            className={`main absolute inset-0 w-full h-full anim-fade ${fit === 'contain' ? 'object-contain' : 'object-cover'}`} />
        ) : a.thumb_state === 0 ? (
          <div className="absolute inset-0 skeleton grid place-items-center text-[11px] text-faint">生成预览中…</div>
        ) : (
          <div className="absolute inset-0 grid place-items-center text-center p-2 text-[11px] text-faint">
            <div>{a.kind === 'video' ? <Film className="mx-auto mb-1.5 opacity-60" size={24} /> : <ImageIcon className="mx-auto mb-1.5 opacity-60" size={24} />}无法生成预览<br /><span className="text-dim">{a.ext.slice(1).toUpperCase()}</span></div>
          </div>
        )}
        <button className="card-preview-trigger" onClick={(e) => { e.stopPropagation(); onOpen(idx) }} aria-label={`预览 ${a.name}`} title="点击预览">
          <span className="card-preview-hint"><Maximize size={14} />点击预览</span>
        </button>
        <div className="absolute inset-x-0 top-0 h-12 bg-gradient-to-b from-black/45 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        <button className={`absolute left-2 top-2 grid place-items-center w-6 h-6 rounded-md transition-all cursor-pointer
          z-10 ${sel ? 'bg-accent text-fg opacity-100 scale-100' : 'bg-black/45 backdrop-blur text-white/85 opacity-0 scale-90 group-hover:opacity-100 group-hover:scale-100 hover:bg-black/65'}`}
          onClick={(e) => { e.stopPropagation(); onToggle(idx) }} aria-label={sel ? '取消选择' : '选择'}>
          {sel ? <Check size={14} strokeWidth={3} /> : <span className="w-3 h-3 rounded-[3px] border-[1.5px] border-white/80" />}
        </button>
        {a.kind === 'video' && (
          <span className="absolute left-2 bottom-2 z-10 flex items-center gap-1 rounded-md bg-black/60 text-white backdrop-blur px-1.5 h-5 text-[11px] font-medium tabular-nums">
            <Play size={9} className="fill-white" />{a.duration != null ? fmtDur(a.duration) : '视频'}
          </span>
        )}
        {bad && <span className="absolute right-2 bottom-2 z-10 rounded-md bg-black/60 backdrop-blur px-1.5 h-5 leading-5 text-[10px] font-medium text-star" title="浏览器可能无法播放">{a.ext.slice(1).toUpperCase()}</span>}
      </div>
      <div className="card-caption">
        <div className="card-actions" onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
          <button className={`card-action favorite-action ${a.favorite ? 'is-favorite' : ''}`} disabled={savingFavorite}
            title={a.favorite ? '取消收藏' : '收藏'} aria-label={`${a.favorite ? '取消收藏' : '收藏'} ${a.name}`} aria-pressed={!!a.favorite}
            onClick={async () => { setSavingFavorite(true); try { await onAction(a, 'favorite') } finally { setSavingFavorite(false) } }}>
            <Star size={16} className={a.favorite ? 'fill-current' : ''} />
          </button>
          <button ref={menuButton} className="card-action more-action" title="更多操作" aria-label={`更多操作 ${a.name}`} aria-haspopup="menu" aria-expanded={!!menu}
            onClick={() => setMenu(menu ? null : menuButton.current.getBoundingClientRect())}><MoreHorizontal size={16} /></button>
        </div>
        <div className="truncate text-[12.5px] font-medium leading-tight" title={a.name}>{a.name}</div>
        <div className="mt-1 text-[11px] text-faint tabular-nums truncate">
          <span className="mr-2">{a.ext.slice(1).toUpperCase()}</span>{a.width ? `${a.width} × ${a.height}` : fmtSize(a.size)}
        </div>
      </div>
      {menu && <CardMenu a={a} rect={menu} anchor={menuButton} trash={trash} onClose={() => setMenu(null)} onAction={onAction} />}
    </div>
  )
}

function CardMenu({ a, rect, anchor, trash, onClose, onAction }) {
  const ref = useRef()
  useEffect(() => {
    const outside = (e) => { if (!ref.current?.contains(e.target) && !anchor.current?.contains(e.target)) onClose() }
    const scroll = (e) => { if (!ref.current?.contains(e.target)) onClose() }
    const resize = () => onClose()
    document.addEventListener('pointerdown', outside)
    window.addEventListener('scroll', scroll, true)
    window.addEventListener('resize', resize)
    ref.current?.querySelector('[role="menuitem"]')?.focus()
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('scroll', scroll, true)
      window.removeEventListener('resize', resize)
    }
  }, [anchor, onClose])
  const entries = [
    ['preview', Maximize, '打开预览'], ['favorite', Star, a.favorite ? '取消收藏' : '收藏素材'],
    ...(!trash && a.kind === 'image' ? [['ai_edit', Sparkles, 'AI 修图']] : []),
    ...(!trash ? [['rename', Pencil, '重命名'], ['move', FolderInput, '移动到分类'], ['tag_add', Tag, '添加标签']] : []),
    ['export', Download, '导出原文件'], ['download', Download, '浏览器下载'], ['reveal', FolderOpen, '在文件夹中显示'], ['copy_path', ClipboardCopy, '复制完整路径'],
    ...(trash ? [['restore', RotateCcw, '恢复素材'], ['purge', Trash2, '彻底删除']] : [['trash', Trash2, '移入回收站']]),
  ]
  const height = Math.min(entries.length * 34 + 16, window.innerHeight - 24)
  const left = Math.max(12, Math.min(rect.right - 200, window.innerWidth - 212))
  const top = rect.bottom + 6 + height <= window.innerHeight - 12 ? rect.bottom + 6 : Math.max(12, rect.top - height - 6)
  const keyboard = (e) => {
    e.stopPropagation()
    if (e.key === 'Escape') { e.preventDefault(); onClose(); anchor.current?.focus() }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
      e.preventDefault()
      const buttons = [...ref.current.querySelectorAll('[role="menuitem"]')]
      const i = buttons.indexOf(document.activeElement)
      const next = e.key === 'Home' ? 0 : e.key === 'End' ? buttons.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
      buttons[next]?.focus()
    }
  }
  return createPortal(<div ref={ref} role="menu" aria-label={`${a.name}的更多操作`} className="card-menu pop" style={{ left, top, maxHeight: height }}
    onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()} onKeyDown={keyboard}>
    {entries.map(([action, Icon, label]) => action === 'download'
      ? <a key={action} role="menuitem" className="card-menu-item" href={`/file/${a.id}?download=1`} download onClick={onClose}><Icon size={15} />{label}</a>
      : <button key={action} role="menuitem" className={`card-menu-item ${['trash', 'purge'].includes(action) ? 'danger' : ''}`}
        onClick={() => { onClose(); onAction(a, action) }}><Icon size={15} />{label}</button>)}
  </div>, document.body)
}

/* ---------------------------------------------------------------- 批量栏 */

function BatchBar({ count, trash, onAction, onClear }) {
  return (
    <div className="anim-bar glass pop absolute left-1/2 bottom-6 z-30 w-max max-w-[calc(100%-2rem)] flex flex-wrap items-center justify-center gap-1 whitespace-nowrap rounded-2xl border border-border-strong px-2 py-2" style={{ transform: 'translateX(-50%)' }}>
      <span className="flex items-center gap-2 pl-1.5 pr-2 font-medium"><span className="grid place-items-center min-w-6 h-6 px-1.5 rounded-lg bg-accent text-fg text-xs tabular-nums">{count}</span>已选</span>
      <span className="w-px h-5 bg-border mx-1" />
      {trash ? (
        <>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('restore')}><RotateCcw size={13} />恢复</button>
          <button className="btn btn-sm btn-danger" onClick={() => onAction('purge')}><Trash2 size={13} />彻底删除</button>
        </>
      ) : (
        <>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('move')}><FolderInput size={13} />移动到</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('tag_add')}><Tag size={13} />加标签</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('tag_remove')}><TagsIcon size={13} />去标签</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('favorite', { value: true })}><Star size={13} />收藏</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('favorite', { value: false })}>取消收藏</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('export')}><Download size={13} />导出</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onAction('trash')}><Trash2 size={13} />删除</button>
        </>
      )}
      <button className="btn btn-sm btn-ghost btn-icon" onClick={onClear} aria-label="取消选择" title="取消选择 (Esc)"><X size={14} /></button>
    </div>
  )
}

/* ---------------------------------------------------------------- 左栏 */

function Sidebar({ sidebar, scope, setScope, reload, onDropAssets, theme, onToggleTheme, onAgent }) {
  const c = sidebar.counts
  const ask = useAsk()
  const toast = useToast()
  const [open, setOpen] = useState(() => LS('openFolders', {}))
  useEffect(() => localStorage.setItem('openFolders', JSON.stringify(open)), [open])
  const byParent = useMemo(() => {
    const m = {}
    for (const f of sidebar.folders) (m[f.parent_id ?? 'root'] ||= []).push(f)
    return m
  }, [sidebar.folders])
  const total = useMemo(() => {
    const t = {}
    const sum = (f) => (t[f.id] = f.count + (byParent[f.id] || []).reduce((s, x) => s + sum(x), 0))
    ;(byParent.root || []).forEach(sum)
    return t
  }, [byParent])

  const run = async (fn) => { try { await fn(); reload() } catch (e) { toast(e.message, 'error') } }
  const create = (parent) => run(async () => {
    const name = await ask({ title: parent ? `在“${parent.name}”下新建文件夹` : '新建分类', input: '', placeholder: '名称，例如：沈青', ok: '创建' })
    if (!name) return
    await api.post('/api/folders', { name, parent_id: parent?.id ?? null })
    if (parent) setOpen((o) => ({ ...o, [parent.id]: true }))
  })
  const rename = (f) => run(async () => {
    const name = await ask({ title: '重命名', input: f.name, ok: '保存' })
    if (name && name !== f.name) await api.patch(`/api/folders/${f.id}`, { name })
  })
  const move = (f, d) => run(() => api.patch(`/api/folders/${f.id}`, { move: d }))
  const remove = (f) => run(async () => {
    const u = await api.get(`/api/folders/${f.id}/usage`)
    if (u.assets || u.subfolders) {
      const ok = await ask({
        title: `删除“${f.name}”`,
        message: `该文件夹${u.subfolders ? `包含 ${u.subfolders} 个子文件夹，` : ''}共有 ${u.assets} 个素材。\n删除后这些素材会移到“待整理”，素材本身不会被删除。`,
        ok: '删除文件夹，素材移至待整理', danger: true,
      })
      if (!ok) return
    } else if (!(await ask({ title: `删除“${f.name}”`, message: '这是一个空文件夹。', ok: '删除', danger: true }))) return
    await api.del(`/api/folders/${f.id}?move_to_inbox=true`)
    if (scope === `folder:${f.id}`) setScope('inbox')
    toast('文件夹已删除')
  })

  const Item = ({ s, icon: I, label, n }) => (
    <div className="nav-item" data-on={scope === s} onClick={() => setScope(s)} role="button">
      <I size={16} strokeWidth={1.8} /><span className="flex-1 truncate">{label}</span>{n != null && <span className="count">{n.toLocaleString()}</span>}
    </div>
  )
  const Node = ({ f, depth }) => {
    const kids = byParent[f.id] || []
    const isOpen = open[f.id]
    const [menu, setMenu] = useState(false)
    const [drop, setDrop] = useState(false)
    const sibs = byParent[f.parent_id ?? 'root']
    const pos = sibs.indexOf(f)
    return (
      <>
        <div className={`nav-item group relative ${drop ? 'ring-1 ring-accent bg-accent/10' : ''}`} data-on={scope === `folder:${f.id}`} style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => setScope(`folder:${f.id}`)} role="button"
          onDragOver={(e) => { if ([...e.dataTransfer.types].includes('application/x-asset-ids')) { e.preventDefault(); setDrop(true) } }}
          onDragLeave={() => setDrop(false)}
          onDrop={(e) => { const d = e.dataTransfer.getData('application/x-asset-ids'); setDrop(false); if (d) { e.preventDefault(); e.stopPropagation(); onDropAssets(f.id, JSON.parse(d)) } }}>
          <button className={`-ml-1 p-0.5 rounded hover:bg-fg/10 cursor-pointer ${kids.length ? '' : 'invisible'}`} onClick={(e) => { e.stopPropagation(); setOpen({ ...open, [f.id]: !isOpen }) }} aria-label={isOpen ? '折叠' : '展开'}>
            {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {isOpen && kids.length ? <FolderOpen size={15} strokeWidth={1.8} /> : <Folder size={15} strokeWidth={1.8} />}
          <span className="flex-1 truncate">{f.name}</span>
          <span className="count group-hover:hidden">{total[f.id] || ''}</span>
          <button className="hidden group-hover:block p-0.5 rounded hover:bg-fg/10 cursor-pointer" onClick={(e) => { e.stopPropagation(); setMenu(!menu) }} aria-label="文件夹操作"><MoreHorizontal size={14} /></button>
          {menu && (
            <>
              <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setMenu(false) }} />
              <div className="anim-dialog pop absolute right-1 top-8 z-50 w-40 rounded-xl border border-border-strong bg-panel p-1 text-fg" onClick={(e) => { e.stopPropagation(); setMenu(false) }}>
                <MenuItem icon={FolderPlus} onClick={() => create(f)}>新建子文件夹</MenuItem>
                <MenuItem icon={Pencil} onClick={() => rename(f)}>重命名</MenuItem>
                <MenuItem icon={ArrowUp} disabled={pos === 0} onClick={() => move(f, -1)}>上移</MenuItem>
                <MenuItem icon={ArrowDown} disabled={pos === sibs.length - 1} onClick={() => move(f, 1)}>下移</MenuItem>
                <MenuItem icon={Trash2} danger onClick={() => remove(f)}>删除文件夹</MenuItem>
              </div>
            </>
          )}
        </div>
        {isOpen && kids.map((k) => <Node key={k.id} f={k} depth={depth + 1} />)}
      </>
    )
  }

  return (
    <nav className="library-sidebar shrink-0 bg-panel flex flex-col min-h-0" aria-label="导航">
      <div className="brand flex items-center gap-3 shrink-0">
        <div className="brand-mark" aria-hidden="true"><img src="/lingtu-art.png" alt="" /></div>
        <div className="leading-tight">
          <div className="font-bold text-[21px] tracking-tight">灵图 ART</div>
          <div className="text-[12px] text-dim mt-1">本地美术素材库</div>
        </div>
        <button className="theme-toggle ml-auto" onClick={onToggleTheme} title={theme === 'night' ? '切换到日间模式' : '切换到夜间模式'} aria-label={theme === 'night' ? '切换到日间模式' : '切换到夜间模式'}>
          {theme === 'night' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
      <button className="library-location" onClick={() => setScope('settings')} title="查看素材库位置与设置"><HardDrive size={21} /><span><strong>本地素材库</strong><small>个人创作空间</small></span><ChevronDown size={15} /></button>
      <div className="flex-1 overflow-y-auto px-2.5 pb-2 pt-1 space-y-0.5">
        <Item s="all" icon={Images} label="全部素材" n={c.all} />
        <Item s="inbox" icon={Inbox} label="待整理" n={c.inbox} />
        <Item s="favorites" icon={Star} label="我的收藏" n={c.favorites} />
        <div className="flex items-center justify-between pt-5 pb-1.5 pl-2.5 pr-1">
          <span className="panel-title">素材分类</span>
          <button className="btn btn-ghost btn-icon btn-sm w-6 h-6 text-faint hover:text-fg" onClick={() => create(null)} title="新建分类" aria-label="新建分类"><Plus size={14} /></button>
        </div>
        {(byParent.root || []).map((f) => <Node key={f.id} f={f} depth={0} />)}
      </div>
      <div className="sidebar-footer space-y-0.5">
        <button className="agent-entry" onClick={onAgent}><Sparkles size={23}/><span><strong>AI 助手</strong><small>智能修图 · 文生图 · 批量处理</small></span><ChevronRight size={16} className="ml-auto"/></button>
        <button className="library-summary" onClick={() => setScope('settings')}><HardDrive size={22} /><span><strong>你的创作素材</strong><small>{c.all.toLocaleString()} 个素材 · {sidebar.folders.length} 个分类</small></span><ChevronRight size={17} /></button>
        <div className="local-status"><CircleCheck size={18} /><span>本地素材库已连接<small>素材保存在本机</small></span><i /></div>
        {sidebar.pending_thumbs > 0 && (
          <div className="mx-1 mb-1.5 px-2.5 py-2 rounded-lg bg-card/60 border border-border text-[11px] text-dim flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />后台生成预览 · 剩余 {sidebar.pending_thumbs}
          </div>
        )}
        <Item s="trash" icon={Trash2} label="回收站" n={c.trash} />
        <Item s="settings" icon={SettingsIcon} label="设置与备份" />
      </div>
    </nav>
  )
}

const MenuItem = ({ icon: I, children, onClick, disabled, danger }) => (
  <button disabled={disabled} onClick={onClick} className={`w-full flex items-center gap-2 h-8 px-2 rounded-lg text-left disabled:opacity-40 disabled:pointer-events-none cursor-pointer ${danger ? 'text-danger hover:bg-danger/12' : 'hover:bg-muted'}`}>
    <I size={14} />{children}
  </button>
)
