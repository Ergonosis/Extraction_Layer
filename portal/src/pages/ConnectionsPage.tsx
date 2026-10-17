import { useCallback, useEffect, useState } from 'react'
import { userFacingApiError } from '../api/errors'
import { fetchIntegrations, type Integration } from '../api/integrations'
import { msgraphStatus } from '../api/msgraph'
import { plaidStatus } from '../api/plaid'
import { IntegrationCard } from '../components/IntegrationCard'
import { useToast } from '../context/ToastContext'
import './ConnectionsPage.css'

function shouldHealthCheck(status: string): boolean {
  return status === 'connected' || status === 'reauth_required'
}

export function ConnectionsPage() {
  const { pushToast } = useToast()
  const [integrations, setIntegrations] = useState<Integration[] | null>(null)
  const [healthChecking, setHealthChecking] = useState(false)
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
        const msgraph = rows.find((row) => row.provider === 'msgraph')
        const checks: Promise<void>[] = []

        if (plaid && shouldHealthCheck(plaid.status)) {
          checks.push(
            (async () => {
              try {
                const { integration } = await plaidStatus()
                if (!cancelled) upsertIntegration(integration)
              } catch (err) {
                if (!cancelled) {
                  pushToast({
                    kind: 'error',
                    message: userFacingApiError(err, 'Could not check Plaid connection health.'),
                  })
                }
              }
            })(),
          )
        }

        if (msgraph && shouldHealthCheck(msgraph.status)) {
          checks.push(
            (async () => {
              try {
                const { integration } = await msgraphStatus()
                if (!cancelled) upsertIntegration(integration)
              } catch (err) {
                if (!cancelled) {
                  pushToast({
                    kind: 'error',
                    message: userFacingApiError(
                      err,
                      'Could not check Microsoft Graph connection health.',
                    ),
                  })
                }
              }
            })(),
          )
        }

        if (checks.length > 0) {
          setHealthChecking(true)
          await Promise.all(checks)
          if (!cancelled) setHealthChecking(false)
        }
      } catch (err) {
        if (cancelled) return
        setIntegrations([])
        setHealthChecking(false)
        const message = userFacingApiError(err, 'Could not load integrations.')
        setError(message)
        pushToast({ kind: 'error', message })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pushToast, upsertIntegration])

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

      {integrations !== null && healthChecking && (
        <p className="connections-loading" role="status">
          Checking connection health…
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
