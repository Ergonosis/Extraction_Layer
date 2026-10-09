import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { usePlaidLink, type PlaidLinkOnSuccess } from 'react-plaid-link'
import { userFacingApiError } from '../api/errors'
import {
  plaidCancel,
  plaidConnect,
  plaidDisconnect,
  plaidExchange,
} from '../api/plaid'
import type { Integration } from '../api/integrations'
import { useToast } from '../context/ToastContext'
import { ConfirmDialog } from './ConfirmDialog'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
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
  const { pushToast } = useToast()
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const exchangeSucceededRef = useRef(false)
  const clearedStuckRef = useRef(false)

  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isConnecting = integration.status === 'connecting'
  const awaitingLink = Boolean(linkToken)
  const canDisconnect = isConnected || needsReauth

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
      try {
        if (!publicToken) {
          pushToast({
            kind: 'error',
            message: 'Plaid did not return a public token.',
          })
          exchangeSucceededRef.current = false
          await resetToNotConnected()
          return
        }
        const { integration: next } = await plaidExchange(publicToken)
        onUpdated(next)
        clearLocalLink()
        pushToast({ kind: 'success', message: 'Plaid connected.' })
      } catch (err) {
        exchangeSucceededRef.current = false
        pushToast({
          kind: 'error',
          message: userFacingApiError(err, 'Could not finish Plaid connection.'),
        })
        await resetToNotConnected()
      } finally {
        setBusy(false)
      }
    },
    [clearLocalLink, onUpdated, pushToast, resetToNotConnected],
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
      pushToast({
        kind: 'error',
        message: userFacingApiError(
          err,
          mode === 'reconnect' ? 'Could not reconnect Plaid.' : 'Could not start Plaid Link.',
        ),
      })
      setBusy(false)
      await resetToNotConnected()
    }
  }

  const onDisconnectConfirmed = async () => {
    setBusy(true)
    clearLocalLink()
    try {
      const { integration: next } = await plaidDisconnect()
      onUpdated(next)
      setConfirmOpen(false)
      pushToast({ kind: 'success', message: 'Plaid disconnected.' })
    } catch (err) {
      pushToast({
        kind: 'error',
        message: userFacingApiError(err, 'Could not disconnect Plaid.'),
      })
    } finally {
      setBusy(false)
    }
  }

  const onCancel = () => {
    void resetToNotConnected()
  }

  return (
    <div className="plaid-connect">
      <div className="integration-card-actions">
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
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={() => void beginLink('reconnect')}
          >
            {busy ? 'Working…' : 'Reconnect'}
          </button>
        )}
        {!awaitingLink && canDisconnect && (
          <button
            type="button"
            className="btn-danger"
            disabled={busy}
            onClick={() => setConfirmOpen(true)}
          >
            Disconnect
          </button>
        )}

        {linkToken && (
          <PlaidLinkControls
            key={linkToken}
            token={linkToken}
            onSuccess={onSuccess}
            onExit={onLinkExit}
            disabled={busy}
          />
        )}

        {(awaitingLink || (isConnecting && !isConnected && !needsReauth)) && (
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

      <ConfirmDialog
        open={confirmOpen}
        title="Disconnect Plaid?"
        message="This removes the stored bank link for your organization. You can connect again later."
        confirmLabel="Disconnect"
        busy={busy}
        onCancel={() => {
          if (!busy) setConfirmOpen(false)
        }}
        onConfirm={() => void onDisconnectConfirmed()}
      />
    </div>
  )
}
