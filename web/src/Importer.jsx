import { useRef, useState } from 'react'
import { Upload, RotateCw, X, CircleCheck, CircleAlert, Copy, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { uploadFile, fmtSize, ACCEPT } from './api'
import { FolderSelect } from './ui'

const CONCURRENCY = 3
const MEDIA_RE = /\.(png|jpe?g|webp|gif|bmp|mp4|webm|mov|m4v|mkv)$/i

/** 导入队列：拖放/选择 → 逐个上传（3 并发），单个失败不影响其余，可重试。 */
export function useImporter(onImported) {
  const [jobs, setJobs] = useState([])
  const queue = useRef([])
  const active = useRef(0)
  const files = useRef({})

  const update = (id, patch) => setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...patch } : j)))

  const pump = () => {
    while (active.current < CONCURRENCY && queue.current.length) {
      const job = queue.current.shift()
      active.current++
      update(job.id, { status: 'uploading', progress: 0 })
      uploadFile(files.current[job.id], job.folderId, (p) => update(job.id, { progress: p })).then((r) => {
        active.current--
        update(job.id, { status: r.status, message: r.message || '', progress: 1, assetId: r.asset_id })
        if (r.status !== 'failed') delete files.current[job.id]
        if (r.status === 'ok') onImported()
        pump()
      })
    }
  }

  const add = (fileList, folderId) => {
    const list = [...fileList]
    const added = []
    for (const f of list) {
      const id = Math.random().toString(36).slice(2)
      if (!MEDIA_RE.test(f.name)) {
        added.push({ id, name: f.name, size: f.size, status: 'failed', message: '不支持的文件类型（仅支持 PNG/JPEG/WebP/GIF/BMP 图片和 MP4/WebM/MOV/MKV 视频）', folderId })
        continue
      }
      files.current[id] = f
      const job = { id, name: f.name, size: f.size, status: 'queued', progress: 0, folderId }
      added.push(job)
      queue.current.push(job)
    }
    setJobs((js) => [...js, ...added])
    pump()
  }

  const retry = (job) => {
    if (!files.current[job.id]) return
    update(job.id, { status: 'queued', message: '' })
    queue.current.push(job)
    pump()
  }
  const retryAll = () => jobs.filter((j) => j.status === 'failed' && files.current[j.id]).forEach(retry)
  const clearDone = () => setJobs((js) => js.filter((j) => j.status === 'queued' || j.status === 'uploading'))

  const canRetry = (job) => (job ? !!files.current[job.id] : jobs.some((j) => j.status === 'failed' && files.current[j.id]))
  return { jobs, add, retry, retryAll, clearDone, canRetry }
}

export function ImportPanel({ importer, onClose }) {
  const { jobs, retry, retryAll, clearDone } = importer
  const [collapsed, setCollapsed] = useState(false)
  if (!jobs.length) return null
  const n = (s) => jobs.filter((j) => j.status === s).length
  const running = n('queued') + n('uploading')
  const failed = n('failed')
  return (
    <div className="anim-dialog glass pop fixed right-5 bottom-5 z-50 w-[400px] rounded-2xl border border-border-strong flex flex-col max-h-[60vh] overflow-hidden">
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-border">
        {running ? <Loader2 size={15} className="animate-spin text-accent" /> : <CircleCheck size={15} className="text-emerald-400" />}
        <div className="flex-1 min-w-0">
          <div className="font-medium">{running ? `正在导入 ${jobs.length - running}/${jobs.length}` : '导入完成'}</div>
          <div className="text-xs text-dim">成功 {n('ok')} · 已存在 {n('duplicate')} · 失败 {failed}</div>
        </div>
        {failed > 0 && importer.canRetry() && <button className="btn btn-sm" onClick={retryAll}><RotateCw size={13} />重试失败</button>}
        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? '展开' : '收起'}>
          {collapsed ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
        {!running && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => { clearDone(); onClose?.() }} aria-label="关闭"><X size={15} /></button>}
      </div>
      {!collapsed && (
        <div className="overflow-auto py-1">
          {jobs.map((j) => (
            <div key={j.id} className="px-3.5 py-1.5 flex items-start gap-2">
              <StatusIcon s={j.status} />
              <div className="flex-1 min-w-0">
                <div className="flex gap-2">
                  <span className="truncate flex-1" title={j.name}>{j.name}</span>
                  <span className="text-xs text-dim shrink-0">{fmtSize(j.size)}</span>
                </div>
                {j.status === 'uploading' && (
                  <div className="h-1 mt-1.5 rounded-full bg-muted overflow-hidden"><div className="h-full rounded-full transition-[width] bg-gradient-to-r from-accent to-accent-2" style={{ width: `${j.progress * 100}%` }} /></div>
                )}
                {j.message && <div className={`text-xs mt-0.5 select-text ${j.status === 'failed' ? 'text-danger' : 'text-dim'}`}>{j.message}</div>}
              </div>
              {j.status === 'failed' && importer.canRetry(j) && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => retry(j)} title="重试" aria-label="重试"><RotateCw size={13} /></button>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusIcon({ s }) {
  if (s === 'ok') return <CircleCheck size={15} className="text-emerald-400 mt-0.5 shrink-0" />
  if (s === 'duplicate') return <Copy size={15} className="text-star mt-0.5 shrink-0" />
  if (s === 'failed') return <CircleAlert size={15} className="text-danger mt-0.5 shrink-0" />
  if (s === 'uploading') return <Loader2 size={15} className="animate-spin text-accent mt-0.5 shrink-0" />
  return <span className="w-[15px] h-[15px] mt-0.5 rounded-full border border-dim/40 shrink-0" />
}

/** 选择文件 + 目标文件夹的弹层内容 / 空库引导 */
export function ImportChooser({ folders, folderId, setFolderId, onFiles, big }) {
  const input = useRef()
  const [over, setOver] = useState(false)
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); e.stopPropagation(); setOver(false); onFiles(e.dataTransfer.files) }}
      className={`rounded-2xl border-2 border-dashed transition-all flex flex-col items-center justify-center text-center gap-4
        ${over ? 'border-accent bg-accent/8 scale-[1.01]' : 'border-border-strong bg-bg/40 hover:border-accent/40'} ${big ? 'p-12' : 'p-9'}`}>
      <div className={`w-14 h-14 rounded-2xl grid place-items-center transition-transform ${over ? 'scale-110' : ''}`}
        style={{ background: 'linear-gradient(135deg, color-mix(in oklch, var(--color-accent) 30%, transparent), color-mix(in oklch, var(--color-accent-2) 20%, transparent))' }}>
        <Upload size={24} className="text-accent" />
      </div>
      <div>
        <div className="text-[16px] font-semibold tracking-tight">拖放图片或视频到这里</div>
        <div className="flex flex-wrap justify-center gap-1 mt-2.5">
          {['PNG', 'JPEG', 'WebP', 'GIF', 'MP4', 'WebM'].map((t) => <span key={t} className="chip h-5 text-[10.5px] text-dim">{t}</span>)}
        </div>
        <div className="text-faint text-xs mt-2.5 leading-relaxed">MOV / MKV 也能入库，但浏览器可能无法播放<br />文件会复制进素材库，外部原文件保持不变</div>
      </div>
      <div className="flex items-center gap-2 mt-1 p-1.5 pl-3 rounded-xl bg-card/70 border border-border">
        <span className="text-dim text-xs shrink-0">导入到</span>
        <FolderSelect folders={folders} value={folderId} onChange={setFolderId} className="w-52" />
        <button className="btn btn-primary" onClick={() => input.current.click()}>选择文件</button>
      </div>
      <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { onFiles(e.target.files); e.target.value = '' }} />
    </div>
  )
}
