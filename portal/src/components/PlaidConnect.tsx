import { useCallback, useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { usePlaidLink, type PlaidLinkOnSuccess } from 'react-plaid-link'
import {
  plaidConnect,
  plaidDisconnect,
  plaidExchange,
} from '../api/plaid'
import type { Integration } from '../api/integrations'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
}

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const apiError = err.response?.data?.error
    if (typeof apiError === 'string' && apiError) return apiError
    if (!err.response) return 'Could not reach the API. Is Flask running on :5000?'
    if (err.response.status === 404) {
      return 'Plaid API route not found. Restart Flask on the issue-24 branch.'
    }
    if (err.response.status === 503) {
      return 'Plaid is not configured. Set PLAID_CLIENT_ID, PLAID_SECRET, and FERNET_KEY in .env, then restart Flask.'
    }
  }
  return fallback
}

export function PlaidConnect({ integration, onUpdated }: Props) {
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingOpen, setPendingOpen] = useState(false)

  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isConnecting = integration.status === 'connecting'

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (publicToken) => {
      setBusy(true)
      setError(null)
      try {
        if (!publicToken) {
          setError('Plaid did not return a public token.')
          return
        }
        const { integration: next } = await plaidExchange(publicToken)
        onUpdated(next)
      } catch (err) {
        setError(errorMessage(err, 'Could not finish Plaid connection.'))
      } finally {
        setLinkToken(null)
        setPendingOpen(false)
        setBusy(false)
      }
    },
    [onUpdated],
  )

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    onExit: () => {
      setPendingOpen(false)
      setLinkToken(null)
      setBusy(false)
    },
  })

  useEffect(() => {
    if (pendingOpen && ready && linkToken) {
      open()
      setPendingOpen(false)
    }
  }, [pendingOpen, ready, linkToken, open])

  const startLink = async () => {
    setBusy(true)
    setError(null)
    try {
      const { link_token, integration: next } = await plaidConnect()
      onUpdated(next)
      setLinkToken(link_token)
      setPendingOpen(true)
    } catch (err) {
      setError(errorMessage(err, 'Could not start Plaid Link.'))
      setBusy(false)
    }
  }

  const onDisconnect = async () => {
    setBusy(true)
    setError(null)
    try {
      const { integration: next } = await plaidDisconnect()
      onUpdated(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not disconnect Plaid.'))
    } finally {
      setBusy(false)
    }
  }

  const onReconnect = async () => {
    setBusy(true)
    setError(null)
    try {
      // Reconnect = remove old credential, then fresh Link flow.
      if (isConnected || needsReauth) {
        const { integration: cleared } = await plaidDisconnect()
        onUpdated(cleared)
      }
      const { link_token, integration: next } = await plaidConnect()
      onUpdated(next)
      setLinkToken(link_token)
      setPendingOpen(true)
    } catch (err) {
      setError(errorMessage(err, 'Could not reconnect Plaid.'))
      setBusy(false)
    }
  }

  return (
    <div className="plaid-connect">
      <div className="integration-card-actions">
        {!isConnected && !needsReauth && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy || isConnecting}
            onClick={() => void startLink()}
          >
            {busy ? 'Connecting…' : 'Connect'}
          </button>
        )}
        {needsReauth && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void onReconnect()}
          >
            {busy ? 'Reconnecting…' : 'Reconnect'}
          </button>
        )}
        {isConnected && (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void onReconnect()}
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
