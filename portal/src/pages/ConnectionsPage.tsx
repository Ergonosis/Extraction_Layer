import { useCallback, useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { fetchIntegrations, type Integration } from '../api/integrations'
import { msgraphStatus } from '../api/msgraph'
import { plaidStatus } from '../api/plaid'
import { IntegrationCard } from '../components/IntegrationCard'
import './ConnectionsPage.css'

export function ConnectionsPage() {
  const [integrations, setIntegrations] = useState<Integration[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const upsertIntegration = useCallback((next: Integration) => {
    setIntegrations((prev) => {
      if (!prev) return [next]
      const idx = prev.findIndex((row) => row.provider === next.provider)
      if (idx === -1) return [...prev, next]
      const copy = [...prev]
      copy[idx] = next
      return copy
    })
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const rows = await fetchIntegrations()
        if (cancelled) return
        setIntegrations(rows)
        setError(null)

        const plaid = rows.find((row) => row.provider === 'plaid')
        if (plaid?.status === 'connected') {
          try {
            const { integration } = await plaidStatus()
            if (!cancelled) upsertIntegration(integration)
          } catch {
            // Status check is best-effort.
          }
        }

        const msgraph = rows.find((row) => row.provider === 'msgraph')
        if (msgraph?.status === 'connected') {
          try {
            const { integration } = await msgraphStatus()
            if (!cancelled) upsertIntegration(integration)
          } catch {
            // Status check is best-effort.
          }
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
  }, [upsertIntegration])

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
            <IntegrationCard
              key={item.provider}
              integration={item}
              onPlaidUpdated={item.provider === 'plaid' ? upsertIntegration : undefined}
              onMsGraphUpdated={
                item.provider === 'msgraph' ? upsertIntegration : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}
