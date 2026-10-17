import { useEffect, useState } from 'react'
import { userFacingApiError } from '../api/errors'
import {
  msgraphCancel,
  msgraphConnect,
  msgraphDisconnect,
  msgraphExport,
} from '../api/msgraph'
import type { Integration } from '../api/integrations'
import { useToast } from '../context/ToastContext'
import { ConfirmDialog } from './ConfirmDialog'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
  /** Scopes chosen in PermissionSelector for the initial Connect redirect. */
  connectScopes?: string[]
}

export function MSGraphConnect({ integration, onUpdated, connectScopes }: Props) {
  const { pushToast } = useToast()
  const [busy, setBusy] = useState(false)
  const [extractBusy, setExtractBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const isConnected = integration.status === 'connected'
  const needsReauth = integration.status === 'reauth_required'
  const isConnecting = integration.status === 'connecting'
  const canDisconnect = isConnected || needsReauth
  const actionsLocked = busy || extractBusy

  // Do not auto-cancel `connecting` on mount — an in-flight Microsoft redirect
  // must survive remounts / StrictMode. User can Cancel explicitly.

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('msgraph_error') === '1') {
      pushToast({
        kind: 'error',
        message: 'Microsoft Graph consent failed or was cancelled.',
      })
      params.delete('msgraph_error')
      const next = params.toString()
      const url = next ? `${window.location.pathname}?${next}` : window.location.pathname
      window.history.replaceState({}, '', url)
    }
  }, [pushToast])

  const beginConnect = async (mode: 'connect' | 'reconnect') => {
    setBusy(true)
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
      pushToast({
        kind: 'error',
        message: userFacingApiError(
          err,
          mode === 'reconnect'
            ? 'Could not reconnect Microsoft Graph.'
            : 'Could not start Microsoft Graph connect.',
        ),
      })
      setBusy(false)
      try {
        const { integration: next } = await msgraphCancel()
        onUpdated(next)
      } catch {
        // ignore
      }
    }
  }

  const onDisconnectConfirmed = async () => {
    setBusy(true)
    try {
      const { integration: next } = await msgraphDisconnect()
      onUpdated(next)
      setConfirmOpen(false)
      pushToast({ kind: 'success', message: 'Microsoft Graph disconnected.' })
    } catch (err) {
      pushToast({
        kind: 'error',
        message: userFacingApiError(err, 'Could not disconnect Microsoft Graph.'),
      })
    } finally {
      setBusy(false)
    }
  }

  const onCancel = async () => {
    setBusy(true)
    try {
      const { integration: next } = await msgraphCancel()
      onUpdated(next)
    } catch (err) {
      pushToast({
        kind: 'error',
        message: userFacingApiError(err, 'Could not cancel Microsoft Graph connect.'),
      })
    } finally {
      setBusy(false)
    }
  }

  const onExtract = async () => {
    if (!isConnected || extractBusy) return
    setExtractBusy(true)
    try {
      const end = new Date()
      const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000)
      const result = await msgraphExport({
        include_profile: true,
        include_mail: true,
        include_calendar: true,
        max_pages: 1,
        start_datetime: start.toISOString(),
        end_datetime: end.toISOString(),
      })
      const profileBit = result.profile ? 'profile' : 'no profile'
      pushToast({
        kind: 'success',
        message: `Graph extract: ${profileBit}, ${result.mail_count} mail, ${result.calendar_count} events`,
      })
    } catch (err) {
      pushToast({
        kind: 'error',
        message: userFacingApiError(err, 'Could not extract Microsoft Graph data.'),
      })
    } finally {
      setExtractBusy(false)
    }
  }

  return (
    <div className="plaid-connect">
      <div className="integration-card-actions">
        {!isConnected && !needsReauth && !isConnecting && (
          <button
            type="button"
            className="btn-primary"
            disabled={actionsLocked}
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
              disabled={actionsLocked}
              onClick={() => void beginConnect('connect')}
            >
              {busy ? 'Working…' : 'Try again'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={actionsLocked}
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
            disabled={actionsLocked}
            onClick={() => void beginConnect('reconnect')}
          >
            {busy ? 'Working…' : 'Reconnect'}
          </button>
        )}
        {isConnected && (
          <button
            type="button"
            className="btn-secondary"
            disabled={actionsLocked}
            onClick={() => void beginConnect('reconnect')}
          >
            {busy ? 'Working…' : 'Reconnect'}
          </button>
        )}
        {canDisconnect && (
          <button
            type="button"
            className="btn-danger"
            disabled={actionsLocked}
            onClick={() => setConfirmOpen(true)}
          >
            Disconnect
          </button>
        )}
      </div>

      {isConnected && (
        <div className="integration-card-actions integration-card-actions-extract">
          <button
            type="button"
            className="btn-primary"
            disabled={!isConnected || extractBusy || busy}
            onClick={() => void onExtract()}
          >
            {extractBusy ? 'Extracting…' : 'Extract'}
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Disconnect Microsoft Graph?"
        message="This removes stored Microsoft tokens for your organization. You can connect again later."
        confirmLabel="Disconnect"
        busy={actionsLocked}
        onCancel={() => {
          if (!actionsLocked) setConfirmOpen(false)
        }}
        onConfirm={() => void onDisconnectConfirmed()}
      />
    </div>
  )
}
