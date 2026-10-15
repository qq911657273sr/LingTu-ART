import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, CircleAlert, MoreHorizontal, Sparkles } from 'lucide-react'
import { fmtDur, fmtSize } from './api'

/** 大预览：图片可缩放拖动，视频可播放拖动进度；←/→ 切换，Esc 关闭。 */
export function Viewer({ items, index, total, onIndex, onClose, onNeedMore, onAIEdit, suspended }) {
  const a = items[index]
  const [more, setMore] = useState(false)
  const menu = useRef(null)
  useEffect(() => { setMore(false) }, [index])
  useEffect(() => {
    const close = e => { if (!menu.current?.contains(e.target)) setMore(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  useEffect(() => {
    if (suspended) return
    const k = (e) => {
      if (e.target.closest?.('input,textarea,select')) return
      if (e.key === 'Escape') { e.stopPropagation(); if (more) setMore(false); else onClose() }
      else if (e.key === 'ArrowLeft' && index > 0) { e.preventDefault(); onIndex(index - 1) }
      else if (e.key === 'ArrowRight' && index < items.length - 1) { e.preventDefault(); onIndex(index + 1) }
    }
    window.addEventListener('keydown', k, true)
    return () => window.removeEventListener('keydown', k, true)
  }, [index, items.length, onIndex, onClose, suspended, more])
  useEffect(() => { if (index >= items.length - 3) onNeedMore() }, [index, items.length, onNeedMore])
  if (!a) return null
  return (
    <div className="fixed inset-0 z-[55] bg-[oklch(0.1_0.005_270/0.97)] backdrop-blur-sm anim-overlay flex flex-col" role="dialog" aria-modal="true" aria-label="大预览">
      <div className="flex items-center gap-3 h-14 px-5 shrink-0 text-sm border-b border-white/5">
        <span className="font-medium truncate">{a.name}</span>
        <span className="text-dim text-xs">
          {a.width && `${a.width}×${a.height}`} {a.kind === 'video' && a.duration != null && `· ${fmtDur(a.duration)}`} · {fmtSize(a.size)}
        </span>
        <span className="flex-1" />
        <span className="chip h-6 text-[11px] tabular-nums">{index + 1} / {total}</span>
        <span className="text-faint text-xs hidden md:inline"><kbd>←</kbd> <kbd>→</kbd> 切换 · <kbd>Esc</kbd> 关闭</span>
        {a.kind === 'image' && <div className="relative" ref={menu}>
          <button className="btn btn-icon" aria-label="预览更多选项" aria-haspopup="menu" aria-expanded={more} onClick={() => setMore(v => !v)}><MoreHorizontal size={18} /></button>
          {more && <div role="menu" className="absolute right-0 top-10 z-20 bg-panel border border-border rounded-xl shadow-xl p-1.5 w-44">
            <button role="menuitem" className="btn btn-ghost w-full justify-start" onClick={() => { setMore(false); onAIEdit?.(a) }}><Sparkles size={15} />AI 图生图</button>
          </div>}
        </div>}
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="关闭预览"><X size={18} /></button>
      </div>
      <div className="relative flex-1 min-h-0">
        {a.kind === 'video' ? <VideoView key={a.id} a={a} /> : <ImageView key={a.id} a={a} suspended={suspended} />}
        {index > 0 && (
          <button className="absolute left-3 top-1/2 -translate-y-1/2 btn btn-icon h-12 w-12 rounded-full glass border-white/10 hover:scale-105" onClick={() => onIndex(index - 1)} aria-label="上一个"><ChevronLeft /></button>
        )}
        {index < items.length - 1 && (
          <button className="absolute right-3 top-1/2 -translate-y-1/2 btn btn-icon h-12 w-12 rounded-full glass border-white/10 hover:scale-105" onClick={() => onIndex(index + 1)} aria-label="下一个"><ChevronRight /></button>
        )}
      </div>
    </div>
  )
}

function Failure({ msg }) {
  return (
    <div className="absolute inset-0 grid place-items-center">
      <div className="flex flex-col items-center gap-2 text-center max-w-md">
        <CircleAlert className="text-danger" size={32} />
        <div className="whitespace-pre-line text-fg/90">{msg}</div>
        <div className="text-dim text-xs">可在右侧信息栏使用“导出原文件”或“打开所在位置”，用本机播放器查看。</div>
      </div>
    </div>
  )
}

function ImageView({ a, suspended }) {
  const [scale, setScale] = useState(null) // null = 适应窗口
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [err, setErr] = useState(false)
  const drag = useRef(null)
  const box = useRef()
  const [boxSize, setBoxSize] = useState({ width: 0, height: 0 })
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      setBoxSize({ width: r.width, height: r.height })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const fit = () => {
    if (!a.width || !a.height || !boxSize.width || !boxSize.height) return 1
    return Math.min(1, (boxSize.width - 40) / a.width, (boxSize.height - 40) / a.height)
  }
  const cur = scale ?? fit()
  const zoom = (f) => { setScale(Math.max(0.05, Math.min(16, cur * f))) }
  useEffect(() => {
    const k = (e) => {
      if (suspended || e.target.closest?.('input,textarea,select')) return
      if (e.key === '+' || e.key === '=') zoom(1.25)
      else if (e.key === '-') zoom(0.8)
      else if (e.key === '0') { setScale(null); setPos({ x: 0, y: 0 }) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })
  if (err) return <Failure msg="图片加载失败：原文件可能已丢失或格式无法被浏览器显示。" />
  return (
    <div ref={box} className="absolute inset-0 overflow-hidden cursor-grab active:cursor-grabbing"
      onWheel={(e) => zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15)}
      onDoubleClick={() => { if (scale == null) setScale(1); else { setScale(null); setPos({ x: 0, y: 0 }) } }}
      onPointerDown={(e) => { drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }; e.currentTarget.setPointerCapture(e.pointerId) }}
      onPointerMove={(e) => drag.current && setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y })}
      onPointerUp={() => (drag.current = null)}>
      <img src={`/file/${a.id}`} alt={a.name} draggable={false} onError={() => setErr(true)}
        className="absolute left-1/2 top-1/2 max-w-none checker rounded-sm shadow-2xl shadow-black/60"
        style={{ width: a.width ? a.width * cur : undefined, transform: `translate(calc(-50% + ${pos.x}px), calc(-50% + ${pos.y}px))` }} />
      <div className="absolute bottom-5 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-xl glass pop border border-white/10 p-1">
        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => zoom(0.8)} aria-label="缩小"><ZoomOut size={15} /></button>
        <span className="w-14 text-center text-xs tabular-nums">{Math.round(cur * 100)}%</span>
        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => zoom(1.25)} aria-label="放大"><ZoomIn size={15} /></button>
        <button className="btn btn-ghost btn-sm" onClick={() => { setScale(null); setPos({ x: 0, y: 0 }) }}><Maximize size={13} />适应</button>
        <button className="btn btn-ghost btn-sm" onClick={() => { setScale(1); setPos({ x: 0, y: 0 }) }}>1:1</button>
      </div>
    </div>
  )
}

function VideoView({ a }) {
  const [err, setErr] = useState(null)
  if (err) return <Failure msg={err} />
  return (
    <div className="absolute inset-0 grid place-items-center p-4">
      {a.playable && a.playable !== 'ok' && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 text-xs rounded-md bg-star/15 text-star border border-star/30 px-3 py-1.5">
          {a.playable === 'none' ? '该视频编码浏览器通常不支持，可能无法播放。' : '该视频格式在部分浏览器中可能无法播放。'}
        </div>
      )}
      <video src={`/file/${a.id}`} controls autoPlay className="max-w-full max-h-full outline-none"
        onError={() => setErr(`视频无法在浏览器中播放（${a.ext.replace('.', '').toUpperCase()}）。\n浏览器一般只支持 H.264/VP9/AV1 编码的 MP4、WebM。`)} />
    </div>
  )
}
