import { useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { fetchIntegrations, type Integration } from '../api/integrations'
import { IntegrationCard } from '../components/IntegrationCard'
import './ConnectionsPage.css'

export function ConnectionsPage() {
  const [integrations, setIntegrations] = useState<Integration[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const rows = await fetchIntegrations()
        if (!cancelled) {
          setIntegrations(rows)
          setError(null)
        }
      } catch (err) {
        if (cancelled) return
        setIntegrations([])
        if (isAxiosError(err) && err.response?.status === 401) {
          setError(
            'Not signed in. Use “Continue as local dev user” on /login (ENABLE_DEV_LOGIN).',
          )
        } else if (isAxiosError(err) && !err.response) {
          setError('Could not reach the API. Is Flask running on :5000?')
        } else {
          setError('Could not load integrations.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="connections-page">
      <header className="connections-header">
        <h1>Connections</h1>
        <p>Manage bank and Microsoft integrations for your organization.</p>
      </header>

      {error && <p className="connections-error">{error}</p>}

      {integrations === null && !error && (
        <p className="connections-loading" role="status">
          Loading integrations…
        </p>
      )}

      {integrations && integrations.length > 0 && (
        <div className="connections-grid">
          {integrations.map((item) => (
            <IntegrationCard key={item.provider} integration={item} />
          ))}
        </div>
      )}
    </div>
  )
}
