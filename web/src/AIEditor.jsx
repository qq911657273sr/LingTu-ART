import { useEffect, useRef, useState } from 'react'
import { X, Sparkles, Plus, Settings2, ArrowRight, Download, FolderPlus, Loader2, History, ImagePlus, RotateCcw, Save, Trash2, ChevronLeft, ChevronRight, FileUp } from 'lucide-react'
import { api, fmtTime } from './api'
import { AISettings } from './AISettings'
import './ai.css'

const imageURL = r => r?.type === 'asset' ? `/file/${r.id}` : r?.type === 'job' ? `/api/ai/jobs/${r.id}/result` : r ? `/api/ai/references/${r.id}` : ''
const statusName = { running: '生成中', completed: '已完成', failed: '失败', interrupted: '已中断' }
const id = () => crypto.randomUUID().replaceAll('-', '')

export function AIEditor({ open, source, onClose, onSaved }) {
  const [config, setConfig] = useState({ profiles: [], presets: [] })
  const [refs, setRefs] = useState([])
  const [prompt, setPrompt] = useState('')
  const [profileId, setProfileId] = useState('')
  const [jobs, setJobs] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [tab, setTab] = useState('edit')
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [picker, setPicker] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [llmPresetName, setLlmPresetName] = useState('')
  const [llmPresetText, setLlmPresetText] = useState('')
  const [promptPresetIndex, setPromptPresetIndex] = useState('')
  const [promptIdea, setPromptIdea] = useState('')
  const [promptHelpOpen, setPromptHelpOpen] = useState(false)
  const [promptBusy, setPromptBusy] = useState(false)
  const [view, setView] = useState('compare')
  const [zoomImage, setZoomImage] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const upload = useRef()
  const presetUpload = useRef()
  const llmPresetUpload = useRef()
  const submitLock = useRef(false)
  const pendingRequest = useRef(null)
  const active = jobs.find(j => j.id === activeId)
  const profile = config.profiles.find(p => p.id === profileId)
  const updateConfig = d => { setConfig(d); setProfileId(p => d.profiles.some(x => x.id === p) ? p : d.profiles[0]?.id || '') }
  const loadJobs = () => api.get('/api/ai/jobs').then(setJobs)
  useEffect(() => { if (open) { api.get('/api/ai/settings').then(updateConfig).catch(e => setError(e.message)); loadJobs().catch(e => setError(e.message)) } }, [open])
  useEffect(() => {
    if (source) { setRefs([{ type: 'asset', id: source.id, name: source.name }]); setPrompt(''); setActiveId(null); setTab('edit'); setError(''); setNotice(''); pendingRequest.current = null }
  }, [source])
  useEffect(() => {
    if (!open) return
    const siblings = [...document.querySelectorAll('.workbench > *:not(.ai-overlay)')]
    siblings.forEach(el => el.inert = true)
    return () => siblings.forEach(el => el.inert = false)
  }, [open])
  useEffect(() => {
    if (!open) return
    const t = setInterval(() => loadJobs().catch(e => setError(e.message)), 2500)
    return () => clearInterval(t)
  }, [open])
  useEffect(() => {
    if (!open) return
    const key = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (zoomImage) setZoomImage(null); else if (picker) setPicker(false); else if (tab === 'settings') setTab('edit'); else onClose() } }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  }, [open, picker, tab, zoomImage, onClose])
  if (!open) return null
  const addRefs = list => { setRefs(old => [...old, ...list].slice(0, 8)); setPicker(false); setError('') }
  const uploadFiles = async files => {
    const remaining = 8 - refs.length
    if (files.length > remaining) { setError(`最多 8 张参考图，目前还可以添加 ${remaining} 张`); return }
    setUploading(true); setError('')
    try {
      const list = []
      for (const file of files) {
        const response = await fetch('/api/ai/references', { method: 'POST', body: file })
        if (response.status === 401) window.dispatchEvent(new Event('lingtu-auth-required'))
        const d = await response.json()
        if (!response.ok) throw new Error(d.detail || '上传失败')
        list.push({ ...d, name: file.name })
      }
      addRefs(list)
    } catch (e) { setError(e.message) } finally { setUploading(false); if (upload.current) upload.current.value = '' }
  }
  const generate = async () => {
    if (submitLock.current) return
    if (!profile?.has_key) { setError('请先配置服务及 API Key'); setTab('settings'); return }
    if (!prompt.trim() || (profile.max_refs !== 0 && !refs.length)) { setError('请添加主参考图并输入修改指令'); return }
    if (profile.max_refs !== 0 && refs.length > profile.max_refs) { setError(`所选服务配置最多支持 ${profile.max_refs} 张参考图，请移除多余图片或更换配置`); return }
    submitLock.current = true; setBusy(true); setError(''); setNotice('')
    const payload = { profile_id: profileId, prompt: prompt.trim(), references: profile.max_refs === 0 ? [] : refs }
    const fingerprint = JSON.stringify(payload)
    if (pendingRequest.current?.fingerprint !== fingerprint) pendingRequest.current = { fingerprint, id: id() }
    try {
      const job = await api.post('/api/ai/jobs', { ...payload, request_id: pendingRequest.current.id })
      setActiveId(job.id); setJobs(old => [job, ...old.filter(j => j.id !== job.id)]); pendingRequest.current = null
    } catch (e) { setError(e.message) } finally { setBusy(false); submitLock.current = false }
  }
  const saveResult = async () => {
    if (!active || saving) return
    setSaving(true); setError('')
    try { await api.post(`/api/ai/jobs/${active.id}/save`); await loadJobs(); onSaved?.(); setNotice('已保存到素材库，可在“待整理”中查看。') }
    catch (e) { setError(e.message) } finally { setSaving(false) }
  }
  const deleteJob = async job => {
    if (job.status === 'running') return
    setError(''); setNotice('')
    try {
      await api.del(`/api/ai/jobs/${job.id}`)
      setJobs(old => old.filter(j => j.id !== job.id))
      setRefs(old => old.filter(r => !(r.type === 'job' && r.id === job.id)))
      if (activeId === job.id) { setActiveId(null); setTab('edit') }
      setDeleteTarget(null)
    } catch (e) { setDeleteTarget(null); setError(e.message) }
  }
  const continueEdit = () => {
    setRefs([{ type: 'job', id: active.id, name: `修改结果 ${active.id.slice(0, 6)}` }]); setPrompt(''); setActiveId(null); setNotice('已将结果设为图 1，请输入下一步修改指令。'); setTab('edit')
  }
  const presetSave = async () => {
    if (!presetName.trim() || !prompt.trim()) { setError('请填写预设名称和修改指令'); return }
    try { updateConfig(await api.post('/api/ai/presets', { presets: [...config.presets, { name: presetName.trim(), text: prompt }] })); setPresetName(''); setNotice('提示词预设已保存') } catch (e) { setError(e.message) }
  }
  const helpWritePrompt = async () => {
    if (!promptIdea.trim()) { setError('先简单描述你想怎么修改'); return }
    setPromptBusy(true); setError(''); setNotice('')
    try {
      const selectedPreset = config.prompt_presets?.[Number(promptPresetIndex)]
      const result = await api.post('/api/ai/prompt', { instruction: promptIdea.trim(), draft: prompt, preset: selectedPreset?.text || '' })
      setPrompt(result.prompt); setPromptHelpOpen(false); setPromptIdea(''); setNotice('提示词已生成，可以继续手动修改。')
    } catch (e) { setError(e.message) } finally { setPromptBusy(false) }
  }
  const importPresets = async file => {
    if (!file) return
    setError('')
    try {
      if (file.size > 1024 * 1024) throw new Error('预设文件不能超过 1 MB')
      const contents = (await file.text()).replace(/^\uFEFF/, '')
      const parsed = file.name.toLowerCase().endsWith('.json') ? JSON.parse(contents) : null
      const entries = parsed ? (Array.isArray(parsed) ? parsed : parsed.presets || [parsed]) : [{ name: file.name.replace(/\.(txt|md)$/i, ''), text: contents }]
      const incoming = entries.filter(p => p && typeof p === 'object').map((p, i) => ({ name: String(p.name || `导入预设 ${i + 1}`).trim(), text: String(p.text || p.prompt || p.content || '').trim() })).filter(p => p.name && p.text)
      if (incoming.some(p => p.name.length > 80 || p.text.length > 8000)) throw new Error('预设名称最多 80 字，提示词最多 8000 字')
      if (!incoming.length) throw new Error('文件里没有有效预设。JSON 请使用 [{"name":"名称","text":"提示词"}] 格式；TXT/MD 每个文件作为一条预设。')
      const merged = [...config.presets, ...incoming].slice(0, 50)
      updateConfig(await api.post('/api/ai/presets', { presets: merged }))
      setNotice(`已导入 ${Math.min(incoming.length, 50 - config.presets.length)} 条提示词预设。`)
    } catch (e) { setError(e.message === 'Unexpected end of JSON input' ? 'JSON 文件格式有误。' : e.message) }
    finally { if (presetUpload.current) presetUpload.current.value = '' }
  }
  const importLlmPresets = async file => {
    if (!file) return
    setError('')
    try {
      if (file.size > 1024 * 1024) throw new Error('预设文件不能超过 1 MB')
      const contents = (await file.text()).replace(/^\uFEFF/, '')
      const parsed = file.name.toLowerCase().endsWith('.json') ? JSON.parse(contents) : null
      const entries = parsed ? (Array.isArray(parsed) ? parsed : parsed.presets || [parsed]) : [{ name: file.name.replace(/\.(txt|md)$/i, ''), text: contents }]
      const incoming = entries.filter(p => p && typeof p === 'object').map((p, i) => ({ name: String(p.name || `LLM 预设 ${i + 1}`).trim(), text: String(p.text || p.prompt || p.content || '').trim() })).filter(p => p.name && p.text)
      if (incoming.some(p => p.name.length > 80 || p.text.length > 8000)) throw new Error('预设名称最多 80 字，生成规则最多 8000 字')
      if (!incoming.length) throw new Error('文件里没有有效 LLM 预设。每条需要包含 name（名称）和 text（给 LLM 的生成规则）。')
      const current = config.prompt_presets || []
      if (current.length + incoming.length > 50) throw new Error('LLM 预设最多保存 50 条，请先删除部分预设再导入')
      const merged = [...current, ...incoming]
      updateConfig(await api.post('/api/ai/prompt-presets', { presets: merged }))
      setPromptPresetIndex(String(current.length))
      setNotice(`已导入 ${incoming.length} 条 LLM 提示词生成预设。`)
    } catch (e) { setError(e.message === 'Unexpected end of JSON input' ? 'JSON 文件格式有误。' : e.message) }
    finally { if (llmPresetUpload.current) llmPresetUpload.current.value = '' }
  }
  const saveLlmPreset = async () => {
    if (!llmPresetName.trim() || !llmPresetText.trim()) { setError('请填写 LLM 预设名称和生成规则'); return }
    const current = config.prompt_presets || []
    if (current.length >= 50) { setError('LLM 预设最多保存 50 条'); return }
    try {
      updateConfig(await api.post('/api/ai/prompt-presets', { presets: [...current, { name: llmPresetName.trim(), text: llmPresetText.trim() }] }))
      setPromptPresetIndex(String(current.length)); setLlmPresetName(''); setLlmPresetText(''); setNotice('LLM 提示词生成预设已保存。')
    } catch (e) { setError(e.message) }
  }
  const leftURL = active ? (active.references.length ? `/api/ai/jobs/${active.id}/input/0` : '') : imageURL(refs[0])
  const running = jobs.filter(j => j.status === 'running').length
  return <div className="ai-overlay" role="dialog" aria-modal="true" aria-label="AI 图生图" onDragOver={e => e.stopPropagation()} onDrop={e => { e.stopPropagation(); e.preventDefault() }}>
    <div className="ai-window">
      <header className="ai-header"><div className="ai-brand"><Sparkles size={20} /></div><div><h1>AI 图生图</h1><small>文字描述，让素材生长出新的可能</small></div><span className="ai-header-space" /><span className="ai-muted">{running ? `${running} 个任务生成中` : '灵图 ART · 图片编辑'}</span><button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="关闭 AI 图生图"><X size={18} /></button></header>
      <div className="ai-layout">
        <section className="ai-preview">
          <div className="ai-preview-toolbar"><div className="ai-row"><button className={`btn btn-sm ${view === 'compare' ? 'ai-active' : ''}`} onClick={() => setView('compare')}>对比</button><button className={`btn btn-sm ${view === 'result' ? 'ai-active' : ''}`} onClick={() => setView('result')}>结果</button></div><span className="ai-muted">{active ? `${active.provider} · ${statusName[active.status]}` : '参考图预览'}</span></div>
          <div className={`ai-images ${view === 'result' ? 'ai-result-only' : ''}`}>
            {view === 'compare' && <figure><div className="ai-image-frame">{leftURL ? <button className="ai-zoom-trigger" onClick={() => setZoomImage({ src: leftURL, alt: '主参考图' })} aria-label="放大查看主参考图"><img src={leftURL} alt="主参考图" /></button> : <div className="ai-empty"><ImagePlus size={32} /><p>从素材预览进入，或添加参考图</p></div>}</div><figcaption>图 1 · {active?.references[0]?.name || refs[0]?.name || '主参考图'}</figcaption></figure>}
            <figure><div className="ai-image-frame ai-output-frame">{active?.status === 'completed' ? <button className="ai-zoom-trigger" onClick={() => setZoomImage({ src: `/api/ai/jobs/${active.id}/result`, alt: 'AI 生成结果' })} aria-label="放大查看 AI 生成结果"><img src={`/api/ai/jobs/${active.id}/result`} alt="AI 生成结果" /></button> : <div className="ai-empty">{active?.status === 'running' ? <Loader2 className="animate-spin" size={32} /> : <Sparkles size={32} />}<h3>{active?.stage || '你的下一版灵感'}</h3><p>{active?.error || (active?.status === 'running' ? '可以关闭面板，任务会继续运行' : '输入修改指令，结果将在这里显示')}</p>{active?.remote_id && <small>平台任务 ID：{active.remote_id}</small>}</div>}</div><figcaption>{active?.status === 'completed' ? '生成结果 · 原图未覆盖' : '生成结果'}</figcaption></figure>
          </div>
          {active && <div className="ai-result-actions"><span title={active.prompt} className="ai-prompt-summary">{active.prompt}</span>{active.status === 'completed' && <><a className="btn btn-sm" href={`/api/ai/jobs/${active.id}/result?download=true`} download><Download size={14} />下载</a><button className="btn btn-sm" onClick={continueEdit}><RotateCcw size={14} />继续修改</button><button className="btn ai-lime" disabled={saving || !!active.asset_id} onClick={saveResult}><FolderPlus size={14} />{active.asset_id ? '已入库' : saving ? '保存中…' : '保存到素材库'}</button></>}</div>}
          <div className="ai-history"><div className="ai-history-title"><History size={14} /><span>生成记录</span><small>结果保存在本机</small></div><div className="ai-history-list">{!jobs.length && <span className="ai-muted">还没有生成记录。每次生成都会保留原图、提示词和结果。</span>}{jobs.map(j => <div className="ai-history-item" key={j.id}><button className={`ai-history-card ${activeId === j.id ? 'selected' : ''}`} onClick={() => { setActiveId(j.id); setError(''); setNotice('') }} title={`${j.prompt}\n${fmtTime(j.created)}`}>
            {j.status === 'completed' ? <img src={`/api/ai/jobs/${j.id}/result`} alt="历史结果" /> : <div className="ai-history-placeholder">{j.status === 'running' ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}</div>}<span>{j.prompt}</span></button><small className="ai-history-status">{statusName[j.status]}</small><button className="ai-history-delete" disabled={j.status === 'running'} onClick={() => setDeleteTarget(j)} aria-label={`删除生成记录 ${j.prompt}`} title={j.status === 'running' ? '任务生成中，暂不能删除' : '删除此生成记录'}><Trash2 size={13} /></button></div>)}</div></div>
        </section>
        <aside className="ai-controls">
          {tab === 'settings' ? <AISettings onBack={() => setTab('edit')} onChanged={updateConfig} /> : <>
            <div className="ai-section-title"><h2>编辑设置</h2><button className="btn btn-icon btn-ghost" title="服务配置" aria-label="服务配置" onClick={() => setTab('settings')}><Settings2 size={16} /></button></div>
            <div className="ai-form">
              <label>生成服务<select className="input" value={profileId} onChange={e => setProfileId(e.target.value)}><option value="">选择服务配置</option>{config.profiles.map(p => <option key={p.id} value={p.id}>{p.name}{p.has_key ? '' : ' · 未填密钥'}</option>)}</select></label>
              {profile ? <p className="ai-muted">{profile.model || `RunningHub ${profile.workflow_id}`} · {profile.max_refs === 0 ? '纯文生图，只发送文字，不使用参考图' : `${profile.kind === 'runninghub' && !profile.repeat_main ? '需要' : '最多'} ${profile.max_refs} 张参考图`}</p> : <button className="btn" onClick={() => setTab('settings')}><Plus size={14} />添加 GPT / Gemini / RunningHub</button>}
              <div className="ai-reference-title"><label>参考图片 <small>{refs.length}/8</small></label><span className="ai-muted">图 1 为主图</span></div>
              <div className="ai-reference-list">{refs.map((r, i) => <div className="ai-reference" key={`${i}-${r.id}`}><img src={imageURL(r)} alt={`图 ${i + 1}`} /><div><strong>图 {i + 1}{i === 0 ? ' · 主图' : ''}</strong><small title={r.name}>{r.name}</small></div><div className="ai-reference-buttons"><button className="btn btn-icon btn-sm btn-ghost" disabled={i === 0} aria-label={`前移图 ${i + 1}`} onClick={() => setRefs(old => { const n = [...old]; [n[i-1], n[i]] = [n[i], n[i-1]]; return n })}><ChevronLeft size={12} /></button><button className="btn btn-icon btn-sm btn-ghost" aria-label={`移除图 ${i + 1}`} onClick={() => setRefs(old => old.filter((_, j) => j !== i))}><X size={13} /></button></div></div>)}</div>
              <div className="ai-row"><button className="btn btn-sm" disabled={refs.length >= 8 || uploading} onClick={() => setPicker(true)}><Plus size={13} />素材库</button><button className="btn btn-sm" disabled={refs.length >= 8 || uploading} onClick={() => upload.current.click()}><ImagePlus size={13} />{uploading ? '上传中…' : '本地图片'}</button></div>
              <input hidden ref={upload} type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/bmp" multiple onChange={e => uploadFiles([...e.target.files])} />
              <label><span className="ai-prompt-label"><span>修改指令</span><button className="btn btn-sm" type="button" onClick={() => { if (!config.prompt_llm?.has_key) { setTab('settings'); setError('请先在 AI 服务配置中设置提示词 LLM'); return } setPromptHelpOpen(v => !v); setError('') }}><Sparkles size={12} />AI 帮写</button></span><textarea className="input ai-prompt" rows={5} maxLength={8000} value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="例如：把图 1 的背景换成雪山，保留人物；参考图 2 的光影和颜色。" /></label>
              {promptHelpOpen && <div className="ai-prompt-helper"><label>LLM 生成预设<select className="input" value={promptPresetIndex} onChange={e => setPromptPresetIndex(e.target.value)}><option value="">通用图生图提示词规则</option>{(config.prompt_presets || []).map((p, i) => <option key={`${i}-${p.name}`} value={String(i)}>{p.name}</option>)}</select></label><textarea className="input" rows={2} maxLength={3000} value={promptIdea} onChange={e => setPromptIdea(e.target.value)} placeholder="用自然语言描述想怎么改，例如：把背景换成雨夜街道，人物和衣服保持不变" /><div className="ai-row"><small className="ai-muted">LLM 会按所选预设把描述整理成生图提示词。</small><button className="btn ai-lime" disabled={promptBusy || !promptIdea.trim()} onClick={helpWritePrompt}>{promptBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}{promptBusy ? '正在生成…' : '生成提示词'}</button></div><details className="ai-presets"><summary>管理 LLM 预设 · {(config.prompt_presets || []).length}</summary>{(config.prompt_presets || []).map((p, i) => <div className="ai-row" key={`${i}-${p.name}`}><button type="button" className="btn btn-sm" onClick={() => setPromptPresetIndex(String(i))}>{p.name}</button><button type="button" className="btn btn-icon btn-sm btn-ghost" aria-label={`删除 LLM 预设 ${p.name}`} onClick={async () => { try { const next = config.prompt_presets.filter((_, j) => j !== i); updateConfig(await api.post('/api/ai/prompt-presets', { presets: next })); setPromptPresetIndex('') } catch (e) { setError(e.message) } }}><Trash2 size={12} /></button></div>)}<input className="input" aria-label="LLM 预设名称" placeholder="预设名称" value={llmPresetName} onChange={e => setLlmPresetName(e.target.value)} /><textarea className="input" rows={3} aria-label="LLM 生成规则" placeholder="写给 LLM 的规则：如何把自然语言整理成生图提示词" value={llmPresetText} onChange={e => setLlmPresetText(e.target.value)} /><div className="ai-row"><input hidden ref={llmPresetUpload} type="file" accept=".json,.txt,.md,application/json,text/plain,text/markdown" onChange={e => importLlmPresets(e.target.files?.[0])} /><button type="button" className="btn btn-sm" disabled={(config.prompt_presets || []).length >= 50} onClick={() => llmPresetUpload.current?.click()}><FileUp size={13} />导入 LLM 预设</button><button type="button" className="btn btn-sm" onClick={saveLlmPreset}><Save size={13} />保存规则</button></div></details></div>}
              <div className="ai-preset-chips">{['更换背景', '修改风格', '调整光影'].map(t => <button className="btn btn-sm" key={t} onClick={() => setPrompt(p => p ? `${p}\n${t}：` : `${t}，保持主体和构图不变：`)}>{t}</button>)}</div>
              <details className="ai-presets"><summary>直接应用到生图的文本预设 · {config.presets.length}</summary>{config.presets.map((p, i) => <div className="ai-row" key={i}><button className="btn btn-sm" onClick={() => setPrompt(p.text)}>{p.name}</button><button className="btn btn-icon btn-sm btn-ghost" aria-label={`删除预设 ${p.name}`} onClick={async () => { try { updateConfig(await api.post('/api/ai/presets', { presets: config.presets.filter((_, j) => j !== i) })) } catch (e) { setError(e.message) } }}><Trash2 size={12} /></button></div>)}<div className="ai-row"><input className="input" aria-label="预设名称" placeholder="预设名称" value={presetName} onChange={e => setPresetName(e.target.value)} /><button className="btn btn-icon" title="保存当前指令为预设" aria-label="保存提示词预设" onClick={presetSave}><Save size={14} /></button></div><input hidden ref={presetUpload} type="file" accept=".json,.txt,.md,application/json,text/plain,text/markdown" onChange={e => importPresets(e.target.files?.[0])} /><button className="btn btn-sm" type="button" disabled={config.presets.length >= 50} onClick={() => presetUpload.current?.click()}><FileUp size={13} />导入文本预设</button></details>
              <p className="ai-muted">描述希望修改的内容及需要保留的部分。文字修图可能同时改变其他细节。</p>
              <button className="btn ai-generate" disabled={busy || uploading || active?.status === 'running' || !prompt.trim() || (profile?.max_refs !== 0 && !refs.length)} onClick={generate}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}{busy ? '正在提交…' : '生成新版本'}<ArrowRight size={16} /></button>
              <small className="ai-muted">点击生成会将参考图和指令发送给所选服务。</small>
            </div>
          </>}
          {error && <div className="ai-error" role="alert">{error}</div>}{notice && <div className="ai-success" role="status">{notice}</div>}
        </aside>
      </div>
    </div>
    {deleteTarget && <div className="ai-job-delete-overlay"><section className="ai-job-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ai-job-delete-title"><h2 id="ai-job-delete-title">删除生成记录？</h2><p>将删除这条记录、本地生成结果和参考图副本。{deleteTarget.asset_id ? '已保存到素材库的图片会保留。' : '此操作无法撤销。'}</p><div><button className="btn" onClick={() => setDeleteTarget(null)}>取消</button><button className="btn btn-danger" onClick={() => deleteJob(deleteTarget)}><Trash2 size={14} />确认删除</button></div></section></div>}
    {zoomImage && <div className="ai-lightbox" role="dialog" aria-modal="true" aria-label="图片预览" onClick={() => setZoomImage(null)}>
      <div className="ai-lightbox-toolbar"><span>{zoomImage.alt}</span><span>点击空白处或按 Esc 关闭</span><button className="btn btn-icon btn-ghost" onClick={() => setZoomImage(null)} aria-label="关闭图片预览"><X size={20} /></button></div>
      <div className="ai-lightbox-image" onClick={e => e.stopPropagation()}><img src={zoomImage.src} alt={zoomImage.alt} /></div>
    </div>}
    {picker && <AssetPicker remaining={8 - refs.length} onSelect={addRefs} onClose={() => setPicker(false)} />}
  </div>
}

function AssetPicker({ remaining, onSelect, onClose }) {
  const [q, setQ] = useState(''), [items, setItems] = useState([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0), [error, setError] = useState('')
  useEffect(() => {
    let live = true
    const t = setTimeout(() => api.get(`/api/assets?kind=image&q=${encodeURIComponent(q)}&limit=36&offset=${offset}`).then(d => { if (live) { setItems(d.items); setTotal(d.total); setError('') } }).catch(e => live && setError(e.message)), 180)
    return () => { live = false; clearTimeout(t) }
  }, [q, offset])
  return <div className="ai-picker-overlay"><section className="ai-picker" role="dialog" aria-modal="true" aria-label="选择参考素材"><header><h2>选择参考素材</h2><button className="btn btn-icon" onClick={onClose} aria-label="关闭素材选择"><X size={16} /></button></header><input className="input" autoFocus placeholder="搜索素材、标签…" aria-label="搜索参考素材" value={q} onChange={e => { setQ(e.target.value); setOffset(0) }} />{error && <div className="ai-error">{error}</div>}<div className="ai-picker-grid">{items.map(a => <button key={a.id} disabled={!remaining} onClick={() => onSelect([{ type: 'asset', id: a.id, name: a.name }])}><img src={`/file/${a.id}`} loading="lazy" decoding="async" alt={a.name} /><span>{a.name}</span></button>)}{!items.length && <p className="ai-muted">没有符合条件的图片</p>}</div><footer><span>{total} 张图片 · 点击添加参考</span><button className="btn btn-icon" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n-36))} aria-label="上一页参考素材"><ChevronLeft size={15} /></button><button className="btn btn-icon" disabled={offset+36 >= total} onClick={() => setOffset(n => n+36)} aria-label="下一页参考素材"><ChevronRight size={15} /></button></footer></section></div>
}
