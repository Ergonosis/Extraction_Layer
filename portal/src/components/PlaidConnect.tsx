import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { usePlaidLink, type PlaidLinkOnSuccess } from 'react-plaid-link'
import {
  plaidCancel,
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
      return 'Plaid API route missing. Restart Flask on this branch.'
    }
    if (err.response.status === 503) {
      return 'Plaid is not configured. Set PLAID_CLIENT_ID, PLAID_SECRET, and FERNET_KEY in .env, then restart Flask.'
    }
  }
  return fallback
}

/**
 * Keeps usePlaidLink mounted for one link_token. Does NOT auto-open —
 * React StrictMode remounts destroy handlers, which races auto-open and
 * leaves the UI stuck. Opening from a click is reliable.
 */
function PlaidLinkControls({
  token,
  onSuccess,
  onExit,
  disabled,
}: {
  token: string
  onSuccess: PlaidLinkOnSuccess
  onExit: () => void
  disabled: boolean
}) {
  const { open, ready, error } = usePlaidLink({
    token,
    onSuccess,
    onExit,
  })

  return (
    <>
      <button
        type="button"
        className="btn-primary"
        disabled={disabled || !ready}
        onClick={() => open()}
      >
        {!ready ? 'Loading Plaid…' : 'Continue to Plaid'}
      </button>
      {error && (
        <p className="plaid-connect-error">
          Could not load Plaid Link. Check network access to cdn.plaid.com and try again.
        </p>
      )}
    </>
  )
}

export function PlaidConnect({ integration, onUpdated }: Props) {
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const exchangeSucceededRef = useRef(false)
  const clearedStuckRef = useRef(false)

  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isConnecting = integration.status === 'connecting'
  const awaitingLink = Boolean(linkToken)

  const clearLocalLink = useCallback(() => {
    setLinkToken(null)
    setBusy(false)
  }, [])

  const resetToNotConnected = useCallback(async () => {
    clearLocalLink()
    try {
      const { integration: next } = await plaidCancel()
      onUpdated(next)
      return
    } catch (err) {
      if (!(isAxiosError(err) && err.response?.status === 404)) {
        return
      }
    }
    try {
      const { integration: next } = await plaidDisconnect()
      onUpdated(next)
    } catch {
      // Best-effort.
    }
  }, [clearLocalLink, onUpdated])

  // Clear abandoned connecting on load (no active token in this session).
  useEffect(() => {
    if (clearedStuckRef.current) return
    if (isConnected || needsReauth) return
    if (integration.status !== 'connecting') return
    if (linkToken || busy) return

    clearedStuckRef.current = true
    void resetToNotConnected()
  }, [
    busy,
    integration.status,
    isConnected,
    linkToken,
    needsReauth,
    resetToNotConnected,
  ])

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (publicToken) => {
      exchangeSucceededRef.current = true
      setBusy(true)
      setError(null)
      try {
        if (!publicToken) {
          setError('Plaid did not return a public token.')
          exchangeSucceededRef.current = false
          await resetToNotConnected()
          return
        }
        const { integration: next } = await plaidExchange(publicToken)
        onUpdated(next)
        clearLocalLink()
      } catch (err) {
        exchangeSucceededRef.current = false
        setError(errorMessage(err, 'Could not finish Plaid connection.'))
        await resetToNotConnected()
      } finally {
        setBusy(false)
      }
    },
    [clearLocalLink, onUpdated, resetToNotConnected],
  )

  const onLinkExit = useCallback(() => {
    if (exchangeSucceededRef.current) {
      exchangeSucceededRef.current = false
      clearLocalLink()
      return
    }
    void resetToNotConnected()
  }, [clearLocalLink, resetToNotConnected])

  const beginLink = async (mode: 'connect' | 'reconnect') => {
    setBusy(true)
    setError(null)
    exchangeSucceededRef.current = false
    clearedStuckRef.current = true
    setLinkToken(null)
    try {
      if (mode === 'reconnect' && (isConnected || needsReauth)) {
        const { integration: cleared } = await plaidDisconnect()
        onUpdated(cleared)
      }
      const { link_token, integration: next } = await plaidConnect()
      onUpdated(next)
      setLinkToken(link_token)
      setBusy(false)
    } catch (err) {
      setError(
        errorMessage(
          err,
          mode === 'reconnect' ? 'Could not reconnect Plaid.' : 'Could not start Plaid Link.',
        ),
      )
      setBusy(false)
      await resetToNotConnected()
    }
  }

  const onDisconnect = async () => {
    setBusy(true)
    setError(null)
    clearLocalLink()
    try {
      const { integration: next } = await plaidDisconnect()
      onUpdated(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not disconnect Plaid.'))
    } finally {
      setBusy(false)
    }
  }

  const onCancel = () => {
    setError(null)
    void resetToNotConnected()
  }

  return (
    <div className="plaid-connect">
      <div className="integration-card-actions">
        {/* Step 1: mint link_token */}
        {!awaitingLink && !isConnected && !needsReauth && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void beginLink('connect')}
          >
            {busy ? 'Working…' : isConnecting ? 'Try again' : 'Connect'}
          </button>
        )}
        {!awaitingLink && needsReauth && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void beginLink('reconnect')}
          >
            {busy ? 'Working…' : 'Reconnect'}
          </button>
        )}
        {!awaitingLink && isConnected && (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void beginLink('reconnect')}
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

        {/* Step 2: open Link from a real click once the handler is ready */}
        {linkToken && (
          <PlaidLinkControls
            key={linkToken}
            token={linkToken}
            onSuccess={onSuccess}
            onExit={onLinkExit}
            disabled={busy}
          />
        )}

        {(awaitingLink || (isConnecting && !isConnected)) && (
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={onCancel}
          >
            Cancel
          </button>
        )}
      </div>
      {error && <p className="plaid-connect-error">{error}</p>}
    </div>
  )
}
