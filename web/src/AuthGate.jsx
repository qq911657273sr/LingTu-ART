import { useEffect, useState } from 'react'
import { LockKeyhole, LogOut, LoaderCircle, Images } from 'lucide-react'
import App from './App.jsx'
import './auth.css'

export default function AuthGate() {
  const [state, setState] = useState('checking')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [required, setRequired] = useState(false)

  const check = async () => {
    setState('checking')
    try {
      const response = await fetch('/api/auth/status', { cache: 'no-store' })
      const data = await response.json()
      setRequired(!!data.required)
      setState(data.required && !data.authenticated ? 'login' : 'ready')
      setError('')
    } catch {
      setState('offline')
    }
  }

  useEffect(() => {
    check()
    const expired = () => { setState('login'); setPassword(''); setError('登录状态已失效，请重新登录') }
    window.addEventListener('lingtu-auth-required', expired)
    return () => window.removeEventListener('lingtu-auth-required', expired)
  }, [])

  const submit = async event => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }), cache: 'no-store',
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '登录失败')
      setPassword(''); setState('ready')
    } catch (e) { setError(e.message || '登录失败') }
    finally { setBusy(false) }
  }

  const logout = async () => {
    try { await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', cache: 'no-store' }) }
    finally { setState('login'); setPassword(''); setError('') }
  }

  if (state === 'checking') return <div className="auth-screen"><LoaderCircle className="animate-spin" size={26} /><span>正在验证登录状态…</span></div>
  if (state === 'offline') return <div className="auth-screen"><section className="auth-card"><Images size={30} /><h1>无法连接灵图 ART</h1><p>请检查服务器服务是否运行，然后重试。</p><button className="auth-submit" onClick={check}>重试</button></section></div>
  if (state === 'login') return <div className="auth-screen"><form className="auth-card" onSubmit={submit}>
    <span className="auth-mark"><Images size={22} /></span><p className="auth-brand">灵图 ART</p><h1>登录素材库</h1><p className="auth-subtitle">输入管理员密码，继续访问你的私人素材库。</p>
    <label htmlFor="admin-password">管理员密码</label><input id="admin-password" type="password" autoComplete="current-password" autoFocus required value={password} onChange={e => setPassword(e.target.value)} />
    {error && <p className="auth-error" role="alert">{error}</p>}<button className="auth-submit" disabled={busy || !password}>{busy ? '正在登录…' : <><LockKeyhole size={16} />登录</>}</button>
  </form></div>

  return <><App />{required && <button className="auth-logout" onClick={logout} title="退出登录"><LogOut size={14} />退出登录</button>}</>
}
