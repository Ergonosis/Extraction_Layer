import { useEffect, useState } from 'react'
import './App.css'

type HealthState = 'loading' | 'ok' | 'error'

function App() {
  const [health, setHealth] = useState<HealthState>('loading')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => {
        setHealth(data.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => setHealth('error'))
  }, [])

  return (
    <main className="portal">
      <h1>Ergonosis Portal</h1>
      <p>Scaffold placeholder — SSO and connections come in later issues.</p>
      <p>
        API health:{' '}
        <strong>
          {health === 'loading' && 'checking…'}
          {health === 'ok' && 'ok (Vite proxy → Flask)'}
          {health === 'error' && 'unreachable (is Flask running on :5000?)'}
        </strong>
      </p>
    </main>
  )
}

export default App
