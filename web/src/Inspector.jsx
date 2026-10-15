import { useEffect, useState } from 'react'
import { Star, Copy, Download, FolderOpen, FileJson, ChevronDown, ChevronRight, Trash2, RotateCcw, Maximize2, ClipboardCopy, PanelRightClose, CircleAlert, Play, Sparkles } from 'lucide-react'
import { api, copyText, fmtDur, fmtSize, fmtTime } from './api'
import { FolderSelect, TagInput, useToast, useAsk } from './ui'

const FIELD_LABELS = {
  tool: '生成平台', prompt: '提示词', negative_prompt: '反向提示词', model: '模型', model_hash: '模型哈希', seed: 'Seed',
  sampler: '采样器', scheduler: '调度器', steps: '步数', cfg_scale: 'CFG', denoise: '重绘幅度', size: '生成尺寸', lora: 'LoRA',
  vae: 'VAE', description: '描述', credit: '来源声明', ai_source_type: 'AI 标记', creator_tool: '创建工具', feature: '附加功能',
  input_image: '输入图', upscale_factor: '放大倍数', source_size: '原始尺寸', video_codec: '视频编码', video_profile: '编码档次',
  pixel_format: '像素格式', job_id: '任务 ID', claim_generator: 'C2PA 生成器', software_agent: 'C2PA 工具', rating: '评分',
  topaz_version: 'Topaz 版本', topaz_model: 'Topaz 模型', topaz_settings: 'Topaz 设置',
}
const MAIN = ['prompt', 'negative_prompt', 'model', 'seed']
const TOOL_NAMES = { a1111: 'A1111 / Forge', comfyui: 'ComfyUI' }

function groupFields(fields) {
  const g = {}
  for (const f of fields) {
    const arr = (g[f.field] ||= [])
    if (!arr.includes(f.value)) arr.push(f.value)
  }
  return g
}

export function Inspector({ id, version, sidebar, onChanged, onOpen, onCollapse, trash }) {
  const [a, setA] = useState(null)
  const [err, setErr] = useState(null)
  const [draft, setDraft] = useState({})
  const [genOpen, setGenOpen] = useState(true)
  const [rawOpen, setRawOpen] = useState(false)
  const toast = useToast()
  const ask = useAsk()

  const load = () => api.get(`/api/assets/${id}`).then((d) => { setA(d); setDraft({}); setErr(null) }).catch((e) => setErr(e.message))
  useEffect(() => { setA(null); load() }, [id]) // eslint-disable-line
  useEffect(() => { if (version) load() }, [version]) // eslint-disable-line

  if (err) return <Pane onCollapse={onCollapse}><div className="p-4 text-danger">{err}</div></Pane>
  if (!a) return <Pane onCollapse={onCollapse}><div className="p-4 space-y-3"><div className="skeleton aspect-video rounded-lg" /><div className="skeleton h-5 rounded" /></div></Pane>

  const save = async (patch) => {
    try {
      const d = await api.patch(`/api/assets/${a.id}`, patch)
      setA(d)
      setDraft({})
      onChanged()
    } catch (e) { toast(e.message, 'error') }
  }
  const val = (k) => (k in draft ? draft[k] : a[k])
  const field = (k) => ({
    value: val(k) ?? '',
    onChange: (e) => setDraft({ ...draft, [k]: e.target.value }),
    onBlur: () => k in draft && draft[k] !== a[k] && save({ [k]: draft[k] }),
  })

  const g = groupFields(a.fields.filter((f) => f.parser !== 'video' || ['video_codec', 'video_profile', 'pixel_format'].includes(f.field)))
  const prompt = g.prompt?.[0] || a.manual_prompt
  const others = Object.keys(g).filter((k) => !MAIN.includes(k) && k !== 'tool')

  const copy = async (text, what) => { await copyText(text); toast(`已复制${what}`) }
  const reveal = async () => {
    try {
      const r = await api.post(`/api/assets/${a.id}/reveal`)
      if (r.ok) toast('已在资源管理器中打开')
      else { await copyText(r.path); toast(`${r.message}（已复制完整路径）`, 'info', 6000) }
    } catch (e) {
      await copyText(a.path)
      toast(`无法打开资源管理器：${e.message}。已复制完整路径。`, 'error')
    }
  }
  const exportOne = async () => {
    try {
      const r = await api.post('/api/export', { ids: [a.id] })
      if (r.failed.length) toast(`导出失败：${r.failed.join('；')}`, 'error')
      else toast(`已导出到 ${r.dir}\\${r.exported[0]}`, 'ok', 6000)
    } catch (e) { toast(e.message, 'error') }
  }
  const act = async (action, msg) => {
    await api.post('/api/batch', { ids: [a.id], action })
    toast(msg)
    onChanged(true)
  }
  const purge = async () => {
    if (await ask({ title: '彻底删除', message: `将永久删除“${a.name}”的原文件，无法恢复。确定吗？`, ok: '彻底删除', danger: true })) act('purge', '已彻底删除')
  }

  return (
    <Pane onCollapse={onCollapse}>
      <div className="inspector-body space-y-4 anim-fade" key={a.id}>
        <button className="inspector-preview block w-full overflow-hidden checker relative group cursor-zoom-in" onClick={onOpen} title="打开大预览（空格）">
          {a.thumb_state === 1
            ? <img src={`/thumb/${a.id}`} alt="" className="w-full max-h-[300px] min-h-[140px] object-contain transition-transform duration-300 group-hover:scale-[1.02]" />
            : <div className="aspect-video grid place-items-center text-dim text-xs">{a.thumb_state === 2 ? '无法生成预览' : '预览生成中…'}</div>}
          {a.kind === 'video' && <span className="absolute inset-0 grid place-items-center"><span className="w-12 h-12 rounded-full bg-black/55 text-white backdrop-blur grid place-items-center border border-white/15 group-hover:scale-110 transition-transform"><Play size={18} className="fill-white ml-0.5" /></span></span>}
          <span className="absolute right-2 bottom-2 opacity-0 group-hover:opacity-100 transition flex items-center gap-1 h-7 px-2.5 rounded-lg text-xs font-medium bg-black/65 text-white backdrop-blur border border-white/10"><Maximize2 size={12} />大预览</span>
        </button>
        {(a.note_sys || a.warnings.length > 0 || (a.kind === 'video' && a.playable && a.playable !== 'ok')) && (
          <div className="text-xs rounded-lg border border-star/25 bg-star/8 text-star p-2.5 space-y-1 leading-relaxed">
            {a.kind === 'video' && a.playable === 'none' && <div className="flex gap-1.5"><CircleAlert size={13} className="shrink-0 mt-px" />该视频编码浏览器不支持播放，可导出后用本机播放器查看。</div>}
            {a.kind === 'video' && a.playable === 'limited' && <div className="flex gap-1.5"><CircleAlert size={13} className="shrink-0 mt-px" />该视频格式在部分浏览器中可能无法播放。</div>}
            {a.note_sys && <div>{a.note_sys}</div>}
            {a.warnings.map((w, i) => <div key={i}>{w}</div>)}
          </div>
        )}

        <div>
          <div className="flex items-start gap-1.5">
            <input className="flex-1 min-w-0 bg-transparent text-[15px] font-semibold tracking-tight rounded-md px-1.5 -mx-1.5 py-1 outline-none hover:bg-card focus:bg-bg focus:ring-2 focus:ring-accent/25 transition"
              aria-label="名称" title="点击修改名称" {...field('name')} onKeyDown={(e) => e.key === 'Enter' && e.target.blur()} />
            <button className={`btn btn-icon shrink-0 ${a.favorite ? 'text-star border-star/30 bg-star/10 hover:bg-star/15' : 'btn-ghost'}`} onClick={() => save({ favorite: !a.favorite })}
              aria-label={a.favorite ? '取消收藏' : '收藏'} title={a.favorite ? '取消收藏' : '收藏'}>
              <Star size={16} className={a.favorite ? 'fill-star' : ''} />
            </button>
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            <span className="chip h-5 text-[11px]">{a.kind === 'video' ? '视频' : '图片'} · {a.ext.slice(1).toUpperCase()}</span>
            {a.width ? <span className="chip h-5 text-[11px] tabular-nums">{a.width}×{a.height}</span> : null}
            {a.duration != null && <span className="chip h-5 text-[11px] tabular-nums">{fmtDur(a.duration)}{a.fps ? ` · ${a.fps} fps` : ''}</span>}
            <span className="chip h-5 text-[11px] tabular-nums">{fmtSize(a.size)}</span>
          </div>
        </div>

        <div className="inspector-tags"><TagInput tags={a.tags} onChange={(tags) => save({ tags })} suggestions={sidebar.tags} /></div>
        <dl className="inspector-properties">
          <div><dt>文件类型</dt><dd>{a.ext.slice(1).toUpperCase()}</dd></div>
          {a.width > 0 && <div><dt>分辨率</dt><dd>{a.width} × {a.height}</dd></div>}
          <div><dt>文件大小</dt><dd>{fmtSize(a.size)}</dd></div>
          <div><dt>导入时间</dt><dd>{fmtTime(a.imported_at)}</dd></div>
        </dl>
        <div className="inspector-path"><div className="label mb-1">文件位置</div>{a.path}</div>
        {/* 操作 */}
        <div className="inspector-actions grid grid-cols-2 gap-1.5">
          {trash ? (
            <>
              <button className="btn" onClick={() => act('restore', '已恢复')}><RotateCcw size={14} />恢复</button>
              <button className="btn btn-danger" onClick={purge}><Trash2 size={14} />彻底删除</button>
            </>
          ) : (
            <>
              <button className="btn btn-primary" onClick={exportOne}><Download size={14} />导出原文件</button>
              <button className="btn reveal-button" onClick={reveal}><FolderOpen size={14} />在文件夹中显示</button>
              <button className="btn" onClick={() => prompt ? copy(prompt, '提示词') : toast('没有提示词', 'info')} disabled={!prompt}><Copy size={14} />复制提示词</button>
              <a className="btn" href={`/file/${a.id}?download=1`} download><Download size={14} />浏览器下载</a>
              <button className="btn" onClick={() => copy(a.path, '完整路径')}><ClipboardCopy size={14} />复制路径</button>
              <button className="btn" onClick={() => act('trash', '已移到回收站')}><Trash2 size={14} />删除</button>
            </>
          )}
        </div>

        {/* 基本信息 */}
        <section className="space-y-3">
          <Row label="分类">
            <FolderSelect folders={sidebar.folders} value={a.folder_id} onChange={(v) => save({ folder_id: v })} inboxLabel="待整理" />
          </Row>
          <Row label="备注"><textarea className="input" rows={2} placeholder="添加备注…" {...field('note')} /></Row>
          <div className="text-[11px] text-faint leading-relaxed pt-0.5">
            原文件名 <span className="text-dim select-text break-all">{a.original_name}</span><br />
            导入于 <span className="text-dim">{fmtTime(a.imported_at)}</span>
          </div>
        </section>

        {/* 生成信息 */}
        <section className="section">
          <button className="flex items-center gap-1.5 w-full font-medium cursor-pointer" onClick={() => setGenOpen(!genOpen)} aria-expanded={genOpen}>
            <Sparkles size={14} className="text-accent" />生成信息
            {g.tool && <span className="chip h-5 text-[11px] text-accent border-accent/25 bg-accent/10">{g.tool.map((t) => TOOL_NAMES[t] || t).join(' / ')}</span>}
            <span className="ml-auto text-faint">{genOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</span>
          </button>
          {genOpen && (
            <div className="mt-2.5 space-y-2.5">
              {!a.fields.some((f) => f.parser !== 'video') && <div className="text-xs text-faint">文件中没有可识别的生成参数，可在下方手动补充。</div>}
              <div className="grid grid-cols-2 gap-x-3 gap-y-3">
                {MAIN.map((k) => g[k] && <Gen key={k} label={FIELD_LABELS[k]} values={g[k]} onCopy={(v) => copy(v, FIELD_LABELS[k])} long={k.includes('prompt')} />)}
                {others.map((k) => <Gen key={k} label={FIELD_LABELS[k] || k} values={g[k]} onCopy={(v) => copy(v, FIELD_LABELS[k] || k)} long={g[k].some((v) => v.length > 40)} />)}
              </div>
              {a.workflows.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {a.workflows.includes('workflow') && <a className="btn btn-sm" href={`/api/assets/${a.id}/workflow?key=workflow`}><FileJson size={13} />导出工作流 JSON</a>}
                  {a.workflows.includes('prompt') && <a className="btn btn-sm" href={`/api/assets/${a.id}/workflow?key=prompt`}><FileJson size={13} />导出 API 格式</a>}
                </div>
              )}
              <div className="pt-2 space-y-2 border-t border-border">
                <div className="label pt-1">手动补充 <span className="text-faint/70">· 不修改原始元数据</span></div>
                <textarea className="input" rows={3} placeholder="提示词" {...field('manual_prompt')} />
                <input className="input" placeholder="生成平台，如 即梦、可灵、Midjourney" {...field('manual_platform')} />
              </div>
              <button className="flex items-center gap-1 text-xs text-dim hover:text-fg cursor-pointer" onClick={() => setRawOpen(!rawOpen)}>
                {rawOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}原始元数据（{a.raw.length} 项）
              </button>
              {rawOpen && (
                <div className="space-y-1.5">
                  {a.raw.length === 0 && <div className="text-xs text-dim">无</div>}
                  {a.raw.map((r, i) => (
                    <div key={i} className="text-[11px] rounded-lg bg-bg border border-border p-2">
                      <div className="text-dim">{r.source}{r.keyword ? ` · ${r.keyword}` : ''}</div>
                      <div className="font-mono break-all max-h-24 overflow-auto select-text">{r.text != null ? r.text.slice(0, 2000) : `（二进制 ${fmtSize(r.bytes)}）`}</div>
                    </div>
                  ))}
                  <a className="btn btn-sm" href={`/api/assets/${a.id}/raw`} target="_blank" rel="noreferrer"><FileJson size={13} />查看完整 JSON</a>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </Pane>
  )
}

function Pane({ children, onCollapse }) {
  return (
    <aside className="asset-inspector shrink-0 bg-panel flex flex-col min-h-0">
      <div className="inspector-heading flex items-center shrink-0">
        <span className="panel-title">素材详情</span>
        <button className="btn btn-ghost btn-icon ml-auto" onClick={onCollapse} title="收起右栏" aria-label="收起右栏"><PanelRightClose size={16} /></button>
      </div>
      <div className="overflow-y-auto flex-1 min-h-0">{children}</div>
    </aside>
  )
}

const Row = ({ label, children }) => <div className="space-y-1"><div className="label">{label}</div>{children}</div>

function Gen({ label, values, onCopy, long }) {
  return (
    <div className={`group min-w-0 ${long ? 'col-span-2' : ''}`}>
      <div className="flex items-center gap-1"><span className="label">{label}</span>
        <button className="ml-auto opacity-0 group-hover:opacity-100 text-faint hover:text-fg cursor-pointer transition-opacity" onClick={() => onCopy(values.join('\n'))} aria-label={`复制${label}`} title={`复制${label}`}><Copy size={12} /></button>
      </div>
      {values.map((v, i) => (
        <div key={i} className={`mt-1 select-text break-words ${long ? 'text-[12.5px] leading-relaxed bg-bg/80 rounded-lg border border-border p-2.5 max-h-44 overflow-auto whitespace-pre-wrap' : 'text-[12.5px] text-fg/90'}`}>{v}</div>
      ))}
    </div>
  )
}
