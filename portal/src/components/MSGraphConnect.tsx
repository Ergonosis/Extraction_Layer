import { useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import {
  msgraphCancel,
  msgraphConnect,
  msgraphDisconnect,
} from '../api/msgraph'
import type { Integration } from '../api/integrations'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
  /** Scopes chosen in PermissionSelector for the initial Connect redirect. */
  connectScopes?: string[]
}

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const apiError = err.response?.data?.error
    if (typeof apiError === 'string' && apiError) return apiError
    if (!err.response) return 'Could not reach the API. Is Flask running on :5000?'
    if (err.response.status === 404) {
      return 'MS Graph API route missing. Restart Flask on this branch.'
    }
    if (err.response.status === 503) {
      return 'Microsoft Graph is not configured. Set MS_CLIENT_ID and MS_CLIENT_SECRET.'
    }
  }
  return fallback
}

export function MSGraphConnect({ integration, onUpdated, connectScopes }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isConnecting = integration.status === 'connecting'

  // Do not auto-cancel `connecting` on mount — an in-flight Microsoft redirect
  // must survive remounts / StrictMode. User can Cancel explicitly.

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('msgraph_error') === '1') {
      setError('Microsoft Graph consent failed or was cancelled.')
      params.delete('msgraph_error')
      const next = params.toString()
      const url = next ? `${window.location.pathname}?${next}` : window.location.pathname
      window.history.replaceState({}, '', url)
    }
  }, [])

  const beginConnect = async (mode: 'connect' | 'reconnect') => {
    setBusy(true)
    setError(null)
    try {
      if (mode === 'reconnect' && (isConnected || needsReauth)) {
        const { integration: cleared } = await msgraphDisconnect()
        onUpdated(cleared)
      }
      const scopes =
        mode === 'connect' && connectScopes && connectScopes.length > 0
          ? connectScopes
          : undefined
      const { authorize_url, integration: next } = await msgraphConnect(scopes)
      onUpdated(next)
      window.location.assign(authorize_url)
    } catch (err) {
      setError(
        errorMessage(
          err,
          mode === 'reconnect'
            ? 'Could not reconnect Microsoft Graph.'
            : 'Could not start Microsoft Graph connect.',
        ),
      )
      setBusy(false)
      try {
        const { integration: next } = await msgraphCancel()
        onUpdated(next)
      } catch {
        // ignore
      }
    }
  }

  const onDisconnect = async () => {
    setBusy(true)
    setError(null)
    try {
      const { integration: next } = await msgraphDisconnect()
      onUpdated(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not disconnect Microsoft Graph.'))
    } finally {
      setBusy(false)
    }
  }

  const onCancel = async () => {
    setBusy(true)
    setError(null)
    try {
      const { integration: next } = await msgraphCancel()
      onUpdated(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not cancel Microsoft Graph connect.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="plaid-connect">
      <div className="integration-card-actions">
        {!isConnected && !needsReauth && !isConnecting && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void beginConnect('connect')}
          >
            {busy ? 'Working…' : 'Connect'}
          </button>
        )}
        {!isConnected && !needsReauth && isConnecting && (
          <>
            <button
              type="button"
              className="btn-primary"
              disabled={busy}
              onClick={() => void beginConnect('connect')}
            >
              {busy ? 'Working…' : 'Try again'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void onCancel()}
            >
              Cancel
            </button>
          </>
        )}
        {needsReauth && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void beginConnect('reconnect')}
          >
            {busy ? 'Working…' : 'Reconnect'}
          </button>
        )}
        {isConnected && (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void beginConnect('reconnect')}
            >
              {busy ? 'Working…' : 'Reconnect'}
            </button>
            <button
              type="button"
              className="btn-danger"
              disabled={busy}
              onClick={() => void onDisconnect()}
            >
              Disconnect
            </button>
          </>
        )}
      </div>
      {error && <p className="plaid-connect-error">{error}</p>}
    </div>
  )
}
