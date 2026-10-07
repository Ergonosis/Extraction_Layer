import type { Integration } from '../api/integrations'
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
}

export function IntegrationCard({ integration, onPlaidUpdated }: Props) {
  const statusClass = `status-badge status-${integration.status}`
  const statusText = STATUS_LABELS[integration.status] || integration.status
  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isPlaid = integration.provider === 'plaid'

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

        {integration.provider === 'msgraph' && integration.permissions.length > 0 && (
          <ul className="integration-permissions">
            {integration.permissions.map((perm) => (
              <li key={perm.scope}>
                <span>{perm.label}</span>
                <span className={perm.is_active ? 'perm-on' : 'perm-off'}>
                  {perm.is_active ? 'Active' : 'Off'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {isPlaid && onPlaidUpdated ? (
        <PlaidConnect integration={integration} onUpdated={onPlaidUpdated} />
      ) : (
        <footer className="integration-card-actions">
          {/* MS Graph connect flows land in a later issue. */}
          {!isConnected && !needsReauth && (
            <button type="button" className="btn-primary" disabled title="Coming in a later issue">
              Connect
            </button>
          )}
          {needsReauth && (
            <button type="button" className="btn-primary" disabled title="Coming in a later issue">
              Reconnect
            </button>
          )}
          {isConnected && (
            <>
              <button type="button" className="btn-secondary" disabled title="Coming in a later issue">
                Reconnect
              </button>
              <button type="button" className="btn-danger" disabled title="Coming in a later issue">
                Disconnect
              </button>
            </>
          )}
        </footer>
      )}
    </article>
  )
}
