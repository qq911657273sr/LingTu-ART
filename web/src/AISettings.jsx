import { useEffect, useState } from 'react'
import { Plus, Trash2, Save, ArrowLeft, KeyRound } from 'lucide-react'
import { api } from './api'

export const KINDS = { openai: 'GPT / OpenAI 图像接口', gemini: 'Gemini 原生接口', chat: 'Chat 兼容图像中转', runninghub: 'RunningHub · 工作流 / 应用' }
const DEFAULTS = { openai: 'https://api.openai.com/v1', gemini: 'https://generativelanguage.googleapis.com/v1beta', chat: '', runninghub: 'https://www.runninghub.ai' }
const blank = () => ({ name: '', kind: 'openai', base_url: DEFAULTS.openai, model: '', api_key: '', max_refs: 1, size: '', rh_mode: 'workflow', workflow_id: '', prompt_node: { nodeId: '', fieldName: 'text' }, image_nodes: [{ nodeId: '', fieldName: 'image' }] })
const blankPromptLLM = () => ({ provider: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini', api_key: '' })

export function AISettings({ onBack, onChanged }) {
  const [data, setData] = useState({ profiles: [] })
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [remove, setRemove] = useState(null)
  const [extraText, setExtraText] = useState('[]')
  const [promptLLM, setPromptLLM] = useState(blankPromptLLM())
  const [promptModels, setPromptModels] = useState([])
  const [modelsBusy, setModelsBusy] = useState(false)
  const [promptTestBusy, setPromptTestBusy] = useState(false)
  const load = () => api.get('/api/ai/settings').then(d => { setData(d); setPromptLLM({ ...blankPromptLLM(), ...d.prompt_llm, api_key: '' }) }).catch(e => setError(e.message))
  useEffect(() => { load() }, [])
  const change = (key, value) => setForm(f => ({ ...f, [key]: value }))
  const save = async e => {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { const payload = form.kind === 'runninghub' ? { ...form, extra_nodes: JSON.parse(extraText) } : form; const d = await api.post('/api/ai/profiles', payload); setData(d); setForm(null); setMessage('配置已保存；尚未调用付费生成接口。'); onChanged?.(d) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const savePromptLLM = async e => {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const d = await api.post('/api/ai/prompt-config', promptLLM)
      setData(d); setPromptLLM({ ...blankPromptLLM(), ...d.prompt_llm, api_key: '' })
      setMessage('提示词模型配置已保存。')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const loadPromptModels = async () => {
    setModelsBusy(true); setError(''); setMessage('')
    try {
      const d = await api.post('/api/ai/prompt-models', promptLLM)
      setPromptModels(d.models)
      setMessage(`已加载 ${d.models.length} 个可用模型，请在列表中选择。`)
    } catch (e) { setError(e.message) } finally { setModelsBusy(false) }
  }
  const testPromptLLM = async () => {
    setPromptTestBusy(true); setError(''); setMessage('')
    try {
      const d = await api.post('/api/ai/prompt-test', promptLLM)
      setMessage(`${d.message}（${d.model}）`)
    } catch (e) { setError(e.message) } finally { setPromptTestBusy(false) }
  }
  return <section className="ai-settings">
    <div className="ai-section-title">{onBack && <button className="btn btn-icon btn-ghost" onClick={onBack} aria-label="返回编辑"><ArrowLeft size={16} /></button>}<h2>AI 服务配置</h2></div>
    <p className="ai-muted">配置自己的图像编辑服务。密钥由 Windows 加密保存，读取设置时不会返回完整密钥。</p>
    {error && <div className="ai-error" role="alert">{error}</div>}
    {message && <p className="ai-success" role="status">{message}</p>}
    <details className="ai-llm-settings" open={!data.prompt_llm?.has_key}>
      <summary>提示词 LLM 设置 · {data.prompt_llm?.has_key ? '已配置' : '未配置'}</summary>
      <form onSubmit={savePromptLLM} className="ai-form">
        <label>提示词模型<select className="input" value={promptLLM.provider} onChange={e => { setPromptModels([]); setPromptLLM(v => ({ ...v, provider: e.target.value, base_url: e.target.value === 'gemini' ? 'https://generativelanguage.googleapis.com/v1beta' : 'https://api.openai.com/v1', model: e.target.value === 'gemini' ? 'gemini-2.5-flash' : 'gpt-4o-mini' })) }}><option value="openai">GPT / OpenAI 兼容接口</option><option value="gemini">Gemini</option></select></label>
        <label>接口地址<input className="input" required value={promptLLM.base_url} onChange={e => { setPromptModels([]); setPromptLLM(v => ({ ...v, base_url: e.target.value })) }} /></label>
        <label>从已加载模型中选择<select className="input" value={promptModels.some(m => m.id === promptLLM.model) ? promptLLM.model : ''} onChange={e => { if (e.target.value) setPromptLLM(v => ({ ...v, model: e.target.value })) }}><option value="">请先点击“加载模型”</option>{promptModels.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label>模型名称<input className="input" required value={promptLLM.model} onChange={e => setPromptLLM(v => ({ ...v, model: e.target.value }))} placeholder={promptLLM.provider === 'gemini' ? 'gemini-2.5-flash' : 'gpt-4o-mini'} /></label>
        <div className="ai-row ai-prompt-model-actions"><button className="btn btn-sm" type="button" disabled={modelsBusy} onClick={loadPromptModels}>{modelsBusy ? '加载中…' : '加载模型'}</button><button className="btn btn-sm" type="button" disabled={promptTestBusy || !promptLLM.model.trim()} onClick={testPromptLLM}>{promptTestBusy ? '测试中…' : '测试连接'}</button></div>
        <label><span><KeyRound size={12} />提示词 API Key</span><input type="password" className="input" autoComplete="new-password" value={promptLLM.api_key} onChange={e => setPromptLLM(v => ({ ...v, api_key: e.target.value }))} placeholder={data.prompt_llm?.has_key ? '留空保留已保存密钥' : '填写 GPT 或 Gemini 密钥'} /></label>
        <button className="btn ai-lime" type="submit" disabled={busy}><Save size={14} />{busy ? '保存中…' : '保存提示词模型'}</button>
      </form>
    </details>
    {!form ? <>
      {data.profiles.map(p => <div className="ai-profile-row" key={p.id}>
        <button onClick={() => { setForm({ ...blank(), ...p, api_key: '' }); setExtraText(JSON.stringify(p.extra_nodes || [], null, 2)); setError(''); setMessage('') }}><strong>{p.name}</strong><small>{KINDS[p.kind]} · {p.has_key ? '已保存密钥' : '未填密钥'}</small></button>
        <button className="btn btn-icon btn-ghost" aria-label={`删除配置 ${p.name}`} onClick={() => setRemove(p.id)}><Trash2 size={14} /></button>
        {remove === p.id && <div className="ai-delete-confirm"><span>删除这项服务配置？</span><button className="btn btn-sm" onClick={() => setRemove(null)}>取消</button><button className="btn btn-sm btn-danger" onClick={async () => { try { const d = await api.del(`/api/ai/profiles/${p.id}`); setData(d); setRemove(null); onChanged?.(d) } catch (e) { setError(e.message) } }}>删除</button></div>}
      </div>)}
      {!data.profiles.length && <p className="ai-muted">尚未添加服务。生成前需要填写接口地址、模型和密钥。</p>}
      <button className="btn" onClick={() => { setForm(blank()); setExtraText('[]'); setError(''); setMessage('') }}><Plus size={14} />添加服务</button>
    </> : <form onSubmit={save} className="ai-form">
      <label>配置名称<input className="input" required value={form.name} onChange={e => change('name', e.target.value)} placeholder="例如：我的 Gemini" /></label>
      <label>接口类型<select className="input" value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value, base_url: DEFAULTS[e.target.value], model: '', size: '' }))}>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>接口基础地址<input className="input" required value={form.base_url} onChange={e => change('base_url', e.target.value)} placeholder="https://…/v1" /></label>
      <small className="ai-muted">{form.kind === 'runninghub' ? '填写国际站根地址 https://www.runninghub.ai，节点参数需与实际应用或工作流一致。' : form.kind === 'gemini' ? '原生接口通常以 /v1beta 结尾；不支持原生协议的中转请改选兼容接口。' : '通常以 /v1 结尾，无需附加 /images/edits 或 /chat/completions。'}</small>
      <label><span><KeyRound size={12} /> API Key</span><input type="password" className="input" autoComplete="new-password" value={form.api_key} onChange={e => change('api_key', e.target.value)} placeholder={form.has_key ? '留空保留已保存密钥' : '填写服务密钥'} /></label>
      {form.has_key && <label className="ai-checkbox"><input type="checkbox" checked={!!form.clear_key} onChange={e => change('clear_key', e.target.checked)} />清除已保存密钥</label>}
      {form.kind !== 'runninghub' ? <>
        <label>图像编辑模型<input className="input" required value={form.model} onChange={e => change('model', e.target.value)} placeholder="填写服务文档中的模型 ID" /></label>
        <label>服务支持的参考图上限<select className="input" value={form.max_refs} onChange={e => change('max_refs', +e.target.value)}>{[1, 2, 3, 4, 5, 6, 7, 8].map(n => <option key={n} value={n}>{n} 张</option>)}</select></label>
        {form.kind === 'openai' && <label>输出尺寸（可选）<input className="input" value={form.size} onChange={e => change('size', e.target.value)} placeholder="留空使用模型默认；例如 1024x1024" /></label>}
        {form.kind === 'chat' && <p className="ai-muted">用于支持图片输出的中转模型，普通文字聊天模型无法生成图片。</p>}
      </> : <>
        <label>任务类型<select className="input" value={form.rh_mode} onChange={e => change('rh_mode', e.target.value)}><option value="workflow">ComfyUI 工作流</option><option value="app">AI 应用</option></select></label>
        <label>接口协议<select className="input" value={form.rh_version || 'v1'} onChange={e => change('rh_version', e.target.value)}><option value="v1">传统 OpenAPI</option><option value="v2">OpenAPI V2</option></select></label>
        <label>运行机型<select className="input" value={form.instance_type || 'default'} onChange={e => change('instance_type', e.target.value)}><option value="default">Standard · 24 GB</option><option value="plus">Plus · 48 GB</option><option value="ultra">Ultra · 84 GB</option></select></label>
        <label className="ai-checkbox"><input type="checkbox" checked={!form.image_nodes.length} onChange={e => change('image_nodes', e.target.checked ? [] : [{ nodeId: '', fieldName: 'image' }])} />纯文生图（无参考图输入）</label>
        <label>应用 / 工作流 ID<input className="input" required value={form.workflow_id} onChange={e => change('workflow_id', e.target.value)} /></label>
        <label>提示词节点</label><NodeFields node={form.prompt_node} onChange={n => change('prompt_node', n)} />
        <label>参考图节点（按图 1、图 2 顺序填写）</label>
        {form.image_nodes.map((node, i) => <div key={i} className="ai-node-row"><span>{i + 1}</span><NodeFields node={node} onChange={n => change('image_nodes', form.image_nodes.map((v, j) => i === j ? n : v))} /><button type="button" className="btn btn-icon" disabled={form.image_nodes.length === 1} aria-label={`删除图 ${i + 1} 节点`} onClick={() => change('image_nodes', form.image_nodes.filter((_, j) => j !== i))}><Trash2 size={13} /></button></div>)}
        <button type="button" className="btn btn-sm" disabled={form.image_nodes.length >= 8} onClick={() => change('image_nodes', [...form.image_nodes, { nodeId: '', fieldName: 'image' }])}><Plus size={13} />参考图节点</button>
        {!!form.image_nodes.length && <label className="ai-checkbox"><input type="checkbox" checked={!!form.repeat_main} onChange={e => change('repeat_main', e.target.checked)} />不足的图片节点复用主参考图</label>}
        <details><summary>固定工作流参数</summary><textarea className="input" aria-label="固定节点参数 JSON" rows={5} value={extraText} onChange={e => setExtraText(e.target.value)} /><small className="ai-muted">节点数组，每项包含 nodeId、fieldName、fieldValue。用于固定尺寸、比例等参数。</small></details>
        <p className="ai-muted">按实际工作流填写节点。纯文生图只发送文字；其他模式按参考图顺序输入。取第一个图片输出。</p>
      </>}
      <div className="ai-row"><button className="btn" type="button" disabled={busy} onClick={() => setForm(null)}>取消</button><button className="btn ai-lime" type="submit" disabled={busy}><Save size={14} />{busy ? '保存中…' : '保存配置'}</button></div>
    </form>}
  </section>
}

function NodeFields({ node, onChange }) {
  return <div className="ai-node-fields"><input className="input" aria-label="节点 ID" required placeholder="节点 ID" value={node.nodeId} onChange={e => onChange({ ...node, nodeId: e.target.value })} /><input className="input" aria-label="节点字段名" required placeholder="字段名" value={node.fieldName} onChange={e => onChange({ ...node, fieldName: e.target.value })} /></div>
}
