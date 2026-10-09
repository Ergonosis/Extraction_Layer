import { useCallback, useState } from 'react'
import type { Integration } from '../api/integrations'
import { MSGraphConnect } from './MSGraphConnect'
import { PermissionSelector } from './PermissionSelector'
import { PlaidConnect } from './PlaidConnect'
import './IntegrationCard.css'

const STATUS_LABELS: Record<string, string> = {
  not_connected: 'Not connected',
  connecting: 'Connecting…',
  connected: 'Connected',
  reauth_required: 'Reauth required',
  error: 'Error',
}

type Props = {
  integration: Integration
  onPlaidUpdated?: (next: Integration) => void
  onMsGraphUpdated?: (next: Integration) => void
}

export function IntegrationCard({
  integration,
  onPlaidUpdated,
  onMsGraphUpdated,
}: Props) {
  const statusClass = `status-badge status-${integration.status}`
  const statusText = STATUS_LABELS[integration.status] || integration.status
  const isPlaid = integration.provider === 'plaid'
  const isMsGraph = integration.provider === 'msgraph'
  const [connectScopes, setConnectScopes] = useState<string[] | undefined>(undefined)

  const onSelectionChange = useCallback((scopes: string[]) => {
    setConnectScopes(scopes)
  }, [])

  return (
    <article className="integration-card">
      <header className="integration-card-header">
        <h2>{integration.label}</h2>
        <span className={statusClass}>{statusText}</span>
      </header>

      <div className="integration-card-body">
        {integration.connected_account ? (
          <p>
            Account: <strong>{integration.connected_account}</strong>
          </p>
        ) : (
          <p className="integration-muted">No account connected yet.</p>
        )}
        {integration.connected_at && (
          <p className="integration-muted">
            Connected {new Date(integration.connected_at).toLocaleString()}
          </p>
        )}

        {isMsGraph && onMsGraphUpdated && (
          <PermissionSelector
            integration={integration}
            onUpdated={onMsGraphUpdated}
            onSelectionChange={onSelectionChange}
          />
        )}
      </div>

      {isPlaid && onPlaidUpdated ? (
        <PlaidConnect integration={integration} onUpdated={onPlaidUpdated} />
      ) : isMsGraph && onMsGraphUpdated ? (
        <MSGraphConnect
          integration={integration}
          onUpdated={onMsGraphUpdated}
          connectScopes={connectScopes}
        />
      ) : null}
    </article>
  )
}
