import { useState } from 'react'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import { setOperator, getOperator } from '../services/operator'
import { Card, ErrorState, PageHeader, Spinner } from '../components/ui'

export default function Login() {
  const config = useQuery('/api/auth/config')
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const active = getOperator()
  async function submit(e) {
    e.preventDefault(); if (busy) return
    const u=username.trim().toLowerCase(), n=name.trim()
    if (mode !== 'change' && !/^[a-z0-9_.-]{3,32}$/.test(u)) { setError('Use 3-32 letters, numbers, dots, dashes or underscores for the username.'); return }
    if (mode === 'register' && n.length < 2) { setError('Display name must have at least 2 characters.'); return }
    if (mode === 'register' && (password.length < 12 || password.length > 128)) { setError('Use a password between 12 and 128 characters.'); return }
    if (mode === 'change' && (password.length < 12 || password.length > 128)) { setError('New password must have 12-128 characters.'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      if (mode === 'change') { await api.post('/api/auth/change-password', { current_password: currentPassword, new_password: password }); setMessage('Password updated. Sign out and use the new password next time.'); setPassword(''); setCurrentPassword(''); return }
      const result = await api.post(mode === 'register' ? '/api/auth/register' : '/api/auth/login/password', mode === 'register' ? { username: u, display_name: n, password } : { username: u, password })
      setOperator({ token: result.token, name: result.name, username: result.username, role: result.role })
      window.location.hash = '#/dashboard'
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const title = mode === 'register' ? 'Create team account' : mode === 'change' ? 'Secure your account' : 'Welcome back'
  return <section className="login-page">
    <PageHeader title={title} subtitle="Secure, individual access for your response team." />
    {!config.data && !config.error && <Spinner label="Checking sign-in settings…" />}
    {config.error && <ErrorState error={config.error} onRetry={config.reload} />}
    {config.data && <Card title={mode === 'register' ? 'Create an operator account' : mode === 'change' ? 'Change password' : 'Sign in to ReliefSync'}>
      <p className="muted">Team members use individual accounts. Passwords are salted and hashed by the backend; sessions expire after 8 hours and stay in this browser tab.</p>
      {mode === 'login' && config.data.demo_login && <p className="notice">Demo admin · username <strong>admin</strong> · password <strong>ReliefSync-admin-2026!</strong>. Change this password before sharing the app.</p>}
      <form onSubmit={submit} noValidate>
        {mode === 'register' && <div className="field"><label htmlFor="login-name">Display name</label><input id="login-name" autoComplete="name" required minLength={2} maxLength={80} value={name} onChange={e=>{setName(e.target.value);setError('')}} /></div>}
        {mode !== 'change' && <div className="field"><label htmlFor="login-user">Username</label><input id="login-user" autoComplete="username" required minLength={3} maxLength={32} pattern="[A-Za-z0-9_.-]+" value={username} onChange={e=>{setUsername(e.target.value);setError('')}} /><small className="muted">3-32 letters, numbers, dots, dashes or underscores.</small></div>}
        {mode === 'change' && <div className="field"><label htmlFor="current-password">Current password</label><input id="current-password" type="password" autoComplete="current-password" required value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} /></div>}
        {mode !== 'change' && <div className="field"><label htmlFor="login-password">Password</label><input id="login-password" type="password" autoComplete={mode==='register'?'new-password':'current-password'} required minLength={mode==='register'?12:1} maxLength={128} value={password} onChange={e=>{setPassword(e.target.value);setError('')}} /><small className="muted">{mode === 'register' ? 'At least 12 characters.' : 'Enter your account password.'}</small></div>}
        {mode === 'change' && <div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={e=>{setPassword(e.target.value);setError('')}} /><small className="muted">At least 12 characters.</small></div>}
        {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : mode === 'change' ? 'Save new password' : 'Sign in'}</button>
      </form>
      <p className="muted">{mode === 'login' ? 'Joining your team for the first time?' : 'Already have an account?'} <button type="button" className="link-button" onClick={()=>{setMode(mode==='register'?'login':'register');setError('');setMessage('')}}>{mode==='register'?'Sign in':'Create an account'}</button></p>
      {active.token && <p><button type="button" className="link-button" onClick={()=>{setMode(mode==='change'?'login':'change');setError('');setMessage('')}}>{mode==='change'?'Back to sign in':'Change your current password'}</button></p>}
    </Card>}
  </section>
}
