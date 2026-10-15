import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { X, CircleCheck, CircleAlert, Info } from 'lucide-react'

/* ---------- Toast ---------- */
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastHost({ children }) {
  const [toasts, setToasts] = useState([])
  const push = (msg, type = 'ok', ms = 3200) => {
    const id = Math.random()
    setToasts((t) => [...t.slice(-3), { id, msg, type }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === 'error' ? 7000 : ms)
  }
  const Icon = { ok: CircleCheck, error: CircleAlert, info: Info }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed top-3 left-1/2 -translate-x-1/2 z-[80] flex flex-col items-center gap-2 pointer-events-none" aria-live="polite">
        {toasts.map((t) => {
          const I = Icon[t.type]
          return (
            <div key={t.id} role="status" className={`anim-toast glass pop pointer-events-auto flex items-center gap-2 max-w-[560px] rounded-xl border px-3.5 py-2.5
              ${t.type === 'error' ? 'border-danger/40 text-danger' : t.type === 'ok' ? 'border-border-strong text-ok' : 'border-border-strong text-accent'}`}>
              <I size={16} className="shrink-0" />
              <span className="text-fg/90 select-text">{t.msg}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

/* ---------- Modal ---------- */
export function Modal({ title, onClose, children, width = 440, footer }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && (e.stopPropagation(), onClose())
    window.addEventListener('keydown', k, true)
    return () => window.removeEventListener('keydown', k, true)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/55 backdrop-blur-[3px] anim-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} style={{ width }}
        className="anim-dialog pop max-w-[94vw] max-h-[88vh] flex flex-col rounded-2xl border border-border-strong bg-panel">
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          <button className="btn btn-ghost btn-icon -mr-2" onClick={onClose} aria-label="关闭"><X size={16} /></button>
        </div>
        <div className="px-5 pb-4 overflow-auto">{children}</div>
        {footer && <div className="flex justify-end gap-2 px-5 py-3 border-t border-border">{footer}</div>}
      </div>
    </div>
  )
}

/* ---------- 通用询问框：await ask({title, message, input, ok, danger}) ---------- */
const AskCtx = createContext(null)
export const useAsk = () => useContext(AskCtx)

export function AskHost({ children }) {
  const [state, setState] = useState(null)
  const ask = (opts) => new Promise((resolve) => setState({ ...opts, resolve }))
  return (
    <AskCtx.Provider value={ask}>
      {children}
      {state && <AskDialog {...state} close={(v) => { state.resolve(v); setState(null) }} />}
    </AskCtx.Provider>
  )
}

function AskDialog({ title, message, input, placeholder, ok = '确定', danger, options, folders, close }) {
  const [value, setValue] = useState(input ?? '')
  const [opt, setOpt] = useState(options ? options[0].value : null)
  const [folder, setFolder] = useState(null)
  const ref = useRef()
  useEffect(() => { ref.current?.focus(); ref.current?.select?.() }, [])
  const submit = () => {
    if (input !== undefined && !value.trim()) return
    close(input !== undefined ? value.trim() : options ? opt : folders ? { folder } : true)
  }
  return (
    <Modal title={title} onClose={() => close(null)} footer={<>
      <button className="btn" onClick={() => close(null)}>取消</button>
      <button ref={input === undefined ? ref : undefined} className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={submit}>{ok}</button>
    </>}>
      {message && <div className="text-dim leading-relaxed mb-3 whitespace-pre-line">{message}</div>}
      {input !== undefined && (
        <input ref={ref} className="input" value={value} placeholder={placeholder} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()} />
      )}
      {folders && <FolderSelect folders={folders} value={folder} onChange={setFolder} inboxLabel="待整理（无分类）" />}
      {options && (
        <div className="flex flex-col gap-1">
          {options.map((o) => (
            <label key={String(o.value)} className="flex items-center gap-2 h-8 px-2 rounded-md hover:bg-muted cursor-pointer">
              <input type="radio" checked={opt === o.value} onChange={() => setOpt(o.value)} className="accent-[var(--color-accent)]" />
              {o.label}
            </label>
          ))}
        </div>
      )}
    </Modal>
  )
}

/* ---------- 文件夹 ---------- */
export function flattenFolders(folders) {
  const byParent = {}
  for (const f of folders) (byParent[f.parent_id ?? 'root'] ||= []).push(f)
  const out = []
  const walk = (pid, depth, prefix) => {
    for (const f of byParent[pid] || []) {
      const path = prefix ? `${prefix} / ${f.name}` : f.name
      out.push({ ...f, depth, path })
      walk(f.id, depth + 1, path)
    }
  }
  walk('root', 0, '')
  return out
}

export function FolderSelect({ folders, value, onChange, className = '', inboxLabel = '待整理（不选分类）' }) {
  const flat = flattenFolders(folders)
  return (
    <select className={`input ${className}`} value={value ?? ''} onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}>
      <option value="">{inboxLabel}</option>
      {flat.map((f) => (
        <option key={f.id} value={f.id}>{'\u3000'.repeat(f.depth) + f.name}</option>
      ))}
    </select>
  )
}

/* ---------- 标签输入 ---------- */
export function TagInput({ tags, onChange, suggestions = [] }) {
  const [v, setV] = useState('')
  const add = (raw) => {
    const parts = raw.split(/[,，;；\n]/).map((s) => s.trim().replace(/^#/, '')).filter(Boolean)
    const next = [...tags]
    for (const p of parts) if (!next.includes(p)) next.push(p)
    if (next.length !== tags.length) onChange(next)
    setV('')
  }
  return (
    <div className="flex flex-wrap gap-1.5 rounded-md border border-border bg-bg p-1.5 focus-within:border-accent/70">
      {tags.map((t) => (
        <span key={t} className="chip">
          {t}
          <button className="text-dim hover:text-fg cursor-pointer" aria-label={`移除标签 ${t}`} onClick={() => onChange(tags.filter((x) => x !== t))}><X size={12} /></button>
        </span>
      ))}
      <input list="tag-suggestions" className="flex-1 min-w-[80px] bg-transparent outline-none h-6 px-1 text-[13px]" value={v}
        placeholder={tags.length ? '' : '输入标签，回车添加'} onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',' || e.key === '，') { e.preventDefault(); v.trim() && add(v) }
          else if (e.key === 'Backspace' && !v && tags.length) onChange(tags.slice(0, -1))
        }}
        onBlur={() => v.trim() && add(v)} />
      <datalist id="tag-suggestions">{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
    </div>
  )
}
