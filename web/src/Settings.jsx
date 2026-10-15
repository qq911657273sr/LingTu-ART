import { useEffect, useState } from 'react'
import { FolderOpen, HardDriveDownload, RotateCcw, ImageUp, CircleCheck, CircleAlert, Loader2, ClipboardCopy } from 'lucide-react'
import { api, copyText, fmtSize, fmtTime } from './api'
import { useAsk, useToast } from './ui'
import { AISettings } from './AISettings'

export function Settings({ onLibraryChanged }) {
  const [s, setS] = useState(null)
  const [exportDir, setExportDir] = useState('')
  const [backupDir, setBackupDir] = useState('')
  const toast = useToast()
  const ask = useAsk()

  const [err, setErr] = useState(null)
  const load = () => api.get('/api/settings').then((d) => { setS(d); setErr(null); return d })
  const init = () => { setErr(null); load().then((d) => { setExportDir(d.export_dir); setBackupDir(d.backup_dir) }).catch((e) => setErr(e.message)) }
  useEffect(init, [])
  useEffect(() => {
    if (!s?.task?.running) return
    const t = setInterval(() => load().catch((e) => setErr(e.message)), 700)
    return () => clearInterval(t)
  }, [s?.task?.running])

  if (err && !s) return <Offline msg={err} onRetry={init} />
  if (!s) return <div className="p-8 text-dim">加载中…</div>
  const task = s.task

  const reveal = async (which, path) => {
    try {
      const r = await api.post(`/api/reveal/${which}`)
      if (!r.ok) { await copyText(path); toast(`${r.message}（已复制路径）`, 'info') }
    } catch (e) { toast(e.message, 'error') }
  }
  const saveDirs = async () => {
    try { const d = await api.patch('/api/settings', { export_dir: exportDir, backup_dir: backupDir }); setS(d); toast('设置已保存') }
    catch (e) { toast(e.message, 'error') }
  }
  const run = async (fn) => { try { await fn(); await load() } catch (e) { toast(e.message, 'error') } }
  const restore = (b) => run(async () => {
    const target = await ask({
      title: '从备份恢复',
      message: `将“${b.name}”解压到一个新的目录并校验每个文件。\n当前素材库不会被修改或覆盖。恢复完成后可选择切换到恢复出的素材库。`,
      input: `${s.backup_dir}\\恢复-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}`,
      ok: '开始恢复',
    })
    if (target) await api.post('/api/restore', { path: b.path, target })
  })
  const switchTo = (dir) => run(async () => {
    if (!(await ask({ title: '切换素材库', message: `切换到：\n${dir}\n\n原素材库目录保持不变，之后可在这里切换回去：\n${s.data_dir}`, ok: '切换' }))) return
    await api.post('/api/library/switch', { dir })
    toast('已切换素材库')
    onLibraryChanged()
  })

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5 anim-rise">
      <div><h1 className="text-[22px] font-semibold tracking-tight">设置与备份</h1><p className="text-dim text-xs mt-1">存储位置、完整备份、视频支持与缩略图</p></div>

      <Card title="AI 图生图"><AISettings /></Card>

      <Card title="存储位置">
        <Line label="素材库目录" value={s.data_dir} hint="原文件（originals）、缩略图（thumbs）和数据库（library.db）都在此目录中，整个目录可以整体搬移。"
          action={<button className="btn btn-sm" onClick={() => reveal('data', s.data_dir)}><FolderOpen size={13} />打开</button>} />
        <Line label="配置文件" value={s.config_path} />
        <div className="grid gap-3">
          <label className="space-y-1"><span className="label">导出目录</span>
            <div className="flex gap-2"><input className="input" value={exportDir} onChange={(e) => setExportDir(e.target.value)} />
              <button className="btn btn-sm h-8" onClick={() => reveal('export', s.export_dir)}><FolderOpen size={13} />打开</button></div></label>
          <label className="space-y-1"><span className="label">备份目录</span>
            <div className="flex gap-2"><input className="input" value={backupDir} onChange={(e) => setBackupDir(e.target.value)} />
              <button className="btn btn-sm h-8" onClick={() => reveal('backup', s.backup_dir)}><FolderOpen size={13} />打开</button></div></label>
          <div><button className="btn btn-primary" onClick={saveDirs} disabled={exportDir === s.export_dir && backupDir === s.backup_dir}>保存</button></div>
        </div>
      </Card>

      <Card title="备份与恢复">
        <p className="text-dim text-xs leading-relaxed">完整备份包含数据库、原文件、AI 生成记录、参考图和服务配置。缩略图恢复后自动重建。恢复总是写入新目录；密钥由 Windows 加密，换电脑或用户后需重新填写。</p>
        <div className="flex items-center gap-2">
          <button className="btn btn-primary" disabled={task.running} onClick={() => run(() => api.post('/api/backup'))}><HardDriveDownload size={14} />立即完整备份</button>
          {task.running && <span className="flex items-center gap-1.5 text-dim text-xs"><Loader2 size={13} className="animate-spin" />{task.kind === 'backup' ? '正在备份' : '正在恢复'} {task.done}/{task.total}</span>}
        </div>
        {!task.running && task.error && <div className="text-danger text-xs flex gap-1.5"><CircleAlert size={13} />{task.kind === 'backup' ? '备份' : '恢复'}失败：{task.error}</div>}
        {!task.running && task.result && task.kind === 'backup' && (
          <div className="text-xs text-emerald-400 flex gap-1.5"><CircleCheck size={13} />备份完成：{task.result.files} 个原文件，{fmtSize(task.result.bytes)}。{task.result.missing.length > 0 && <span className="text-star">有 {task.result.missing.length} 个原文件丢失未能备份。</span>}</div>
        )}
        {!task.running && task.result && task.kind === 'restore' && (
          <div className="text-xs rounded-md border border-emerald-400/30 bg-emerald-400/10 p-2.5 space-y-1.5">
            <div className="text-emerald-400 flex gap-1.5"><CircleCheck size={13} />恢复完成，已校验 {task.result.files} 个文件，共 {task.result.assets} 条素材记录。</div>
            <div className="select-text">位置：{task.result.dir}</div>
            <button className="btn btn-sm" onClick={() => switchTo(task.result.dir)}>切换到恢复出的素材库</button>
          </div>
        )}
        <div className="divide-y divide-border rounded-xl border border-border overflow-hidden">
          {s.backups.length === 0 && <div className="p-3 text-dim text-xs">还没有备份。</div>}
          {s.backups.map((b) => (
            <div key={b.path} className="flex items-center gap-3 p-2.5">
              <div className="flex-1 min-w-0"><div className="truncate">{b.name}</div><div className="text-xs text-dim">{fmtTime(b.mtime)} · {fmtSize(b.bytes)}</div></div>
              <button className="btn btn-sm" onClick={() => copyText(b.path).then(() => toast('已复制备份路径'))}><ClipboardCopy size={13} />复制路径</button>
              <button className="btn btn-sm" disabled={task.running} onClick={() => restore(b)}><RotateCcw size={13} />恢复到新目录</button>
            </div>
          ))}
        </div>
      </Card>

      <Card title="视频支持（FFmpeg）">
        {s.tools.ffmpeg && s.tools.ffprobe
          ? <div className="text-xs flex items-start gap-1.5 text-emerald-400"><CircleCheck size={13} className="shrink-0 mt-px" /><span className="shrink-0">已找到 FFmpeg：</span><span className="text-dim select-text break-all">{s.tools.ffmpeg}</span></div>
          : <div className="text-xs text-star leading-relaxed">未找到 FFmpeg。图片功能不受影响；视频将无法读取时长、尺寸，也无法生成封面。<br />安装方法：关闭素材库，双击运行“安装.bat”（会通过 winget 安装 FFmpeg），或在命令行执行 <code className="select-text">winget install Gyan.FFmpeg</code>，然后重新启动素材库。</div>}
      </Card>

      <Card title="缩略图">
        <div className="flex items-center gap-3">
          <button className="btn" onClick={() => run(async () => { const r = await api.post('/api/thumbs/rebuild'); toast(`已加入后台队列：${r.count} 个`) })}><ImageUp size={14} />重建全部缩略图</button>
          <span className="text-xs text-dim">缩略图丢失或安装 FFmpeg 后，可用此功能重新生成。</span>
        </div>
      </Card>
    </div>
  )
}

export const Offline = ({ msg, onRetry }) => (
  <div className="p-8 pt-16 flex flex-col items-start gap-3 max-w-xl">
    <div className="flex gap-2 text-danger"><CircleAlert size={16} className="shrink-0 mt-0.5" />{msg}</div>
    <button className="btn" onClick={onRetry}><RotateCcw size={14} />重试</button>
  </div>
)

const Card = ({ title, children }) => (
  <section className="rounded-2xl border border-border bg-panel/70 p-5 space-y-3.5"><h2 className="font-semibold text-[14px]">{title}</h2>{children}</section>
)

const Line = ({ label, value, hint, action }) => (
  <div className="space-y-1">
    <div className="label">{label}</div>
    <div className="flex items-center gap-2"><code className="flex-1 min-w-0 truncate select-text rounded-lg bg-bg/70 border border-border px-2.5 py-2 text-xs" title={value}>{value}</code>{action}</div>
    {hint && <div className="text-xs text-dim">{hint}</div>}
  </div>
)
