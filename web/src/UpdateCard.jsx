import { useEffect, useState } from 'react'
import { RefreshCw, Download, ExternalLink, CircleCheck, Loader2, CircleAlert } from 'lucide-react'
import { api, fmtSize, fmtTime } from './api'

export function UpdateCard() {
  const [info, setInfo] = useState(null), [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  useEffect(() => { api.get('/api/update').then(setInfo).catch(e => setError(e.message)) }, [])
  const check = async () => {
    setBusy(true); setError('')
    try { const data = await api.post('/api/update/check'); setResult(data); setInfo(data) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  return <section className="rounded-2xl border border-border bg-panel/70 p-5 space-y-3.5" aria-label="软件更新">
    <div className="flex items-center gap-3 flex-wrap"><div className="flex-1"><h2 className="font-semibold text-[14px]">软件更新</h2><p className="text-dim text-xs mt-1">灵图 ART {info ? `v${info.current_version}` : '读取版本中…'} · GitHub 正式版</p></div>
      <button className="btn btn-primary" disabled={busy || !info} onClick={check}>{busy ? <Loader2 size={14} className="animate-spin"/> : <RefreshCw size={14}/>} {busy ? '正在检查…' : '检查更新'}</button>
      {info && <a className="btn" href={info.releases_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14}/>GitHub 发布页</a>}
    </div>
    {error && <p role="alert" className="text-danger text-xs flex gap-2"><CircleAlert size={14} className="shrink-0"/>{error}</p>}
    {result && <div className="rounded-xl bg-bg/70 border border-border p-3 space-y-3" role="status">
      <div className="flex items-center gap-2 text-xs"><CircleCheck size={15} className="text-ok shrink-0"/><strong>{result.state === 'available' ? `发现新版本 v${result.latest_version}` : result.state === 'preparing' ? `新版本 v${result.latest_version} 已发布，安装包准备中` : result.state === 'unpublished' ? result.message : result.state === 'ahead' ? '当前版本高于 GitHub 最新发布版' : '当前已是最新正式版本'}</strong></div>
      {result.state === 'available' && <div className="flex items-center gap-2 flex-wrap"><a className="btn bg-accent border-transparent text-[#202126]" href={result.download_url} target="_blank" rel="noopener noreferrer"><Download size={14}/>下载 Windows 安装包</a>{!!result.size && <span className="text-dim text-xs">{fmtSize(result.size)}</span>}<p className="w-full text-dim text-xs">下载后关闭灵图并安装新版，现有素材库与个人配置保留。</p></div>}
      {result.latest_version && <details className="text-xs"><summary className="cursor-pointer text-dim">查看 v{result.latest_version} 更新说明{result.published_at ? ` · ${new Date(result.published_at).toLocaleDateString('zh-CN')}` : ''}</summary><div className="whitespace-pre-wrap select-text leading-relaxed pt-3 max-h-60 overflow-auto break-words">{result.notes}</div>{result.release_url && <a className="inline-flex gap-1 items-center text-dim mt-3 underline" href={result.release_url} target="_blank" rel="noopener noreferrer">查看完整发布说明 <ExternalLink size={11}/></a>}</details>}
      <p className="text-faint text-[10px]">检查时间：{fmtTime(result.checked_at)}</p>
    </div>}
  </section>
}
