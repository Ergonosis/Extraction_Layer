import { useEffect, useState } from 'react'
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
      } catch {
        if (!cancelled) {
          setError('Could not load integrations. Is the API running?')
          setIntegrations([])
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
