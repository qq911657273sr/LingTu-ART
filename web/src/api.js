export const OFFLINE = '无法连接素材库服务：启动窗口可能已关闭。请双击桌面“美术素材库”重新启动，然后点“重试”。'

async function req(method, url, body) {
  let res
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error(OFFLINE)
  }
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text()
  if (res.status === 401 && !url.startsWith('/api/auth/')) window.dispatchEvent(new Event('lingtu-auth-required'))
  if (!res.ok) throw new Error(data?.detail || data || `请求失败（${res.status}）`)
  return data
}

export const api = {
  get: (u) => req('GET', u),
  post: (u, b = {}) => req('POST', u, b),
  patch: (u, b) => req('PATCH', u, b),
  del: (u) => req('DELETE', u),
}

export const qs = (o) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false)).toString()

/** 上传单个文件（请求体即文件字节），返回服务端结果；onProgress(0..1) */
export function uploadFile(file, folderId, onProgress) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest()
    const q = qs({ name: file.name, folder_id: folderId ?? '', mtime: file.lastModified || '' })
    xhr.open('POST', `/api/import?${q}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      if (xhr.status === 401) window.dispatchEvent(new Event('lingtu-auth-required'))
      try {
        const d = JSON.parse(xhr.responseText)
        resolve(xhr.status < 300 ? d : { status: 'failed', message: d.detail || `服务器错误 ${xhr.status}` })
      } catch {
        resolve({ status: 'failed', message: `服务器错误 ${xhr.status}` })
      }
    }
    xhr.onerror = () => resolve({ status: 'failed', message: '网络错误：无法连接素材库服务（是否已关闭启动窗口？）' })
    xhr.send(file)
  })
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const t = document.createElement('textarea')
    t.value = text
    document.body.appendChild(t)
    t.select()
    document.execCommand('copy')
    t.remove()
  }
}

export const fmtSize = (n) => {
  if (n == null) return ''
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < u.length - 1) (n /= 1024), i++
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`
}

export const fmtDur = (s) => {
  if (s == null) return ''
  s = Math.round(s)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  return (h ? `${h}:${String(m).padStart(2, '0')}` : `${m}`) + `:${String(r).padStart(2, '0')}`
}

export const fmtTime = (t) => (t ? new Date(t * 1000).toLocaleString('zh-CN', { hour12: false }) : '')

export const ACCEPT = '.png,.jpg,.jpeg,.webp,.gif,.bmp,.mp4,.webm,.mov,.m4v,.mkv'
