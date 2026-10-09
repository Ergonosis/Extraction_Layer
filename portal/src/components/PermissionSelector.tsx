import { useEffect, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'
import {
  msgraphPermissionsAvailable,
  msgraphUpdatePermissions,
} from '../api/msgraph'
import type { Integration, IntegrationPermission } from '../api/integrations'
import './PermissionSelector.css'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
  /** When not connected, selected scopes are used by Connect instead of PUT. */
  onSelectionChange?: (scopes: string[]) => void
}

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const apiError = err.response?.data?.error
    if (typeof apiError === 'string' && apiError) return apiError
    if (!err.response) return 'Could not reach the API. Is Flask running on :5000?'
  }
  return fallback
}

function initialSelected(permissions: IntegrationPermission[]): Set<string> {
  return new Set(permissions.filter((p) => p.is_active).map((p) => p.scope))
}

export function PermissionSelector({
  integration,
  onUpdated,
  onSelectionChange,
}: Props) {
  const [rows, setRows] = useState<IntegrationPermission[]>(
    () => integration.permissions,
  )
  const [selected, setSelected] = useState<Set<string>>(() =>
    initialSelected(integration.permissions),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const isConnected = integration.status === 'connected'
  const isConnecting = integration.status === 'connecting'
  const canEdit = !isConnecting

  useEffect(() => {
    setRows(integration.permissions)
    setSelected(initialSelected(integration.permissions))
  }, [integration.permissions, integration.status, integration.updated_at])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await msgraphPermissionsAvailable()
        if (cancelled) return
        setRows(data.permissions)
        setSelected(new Set(data.permissions.filter((p) => p.is_active).map((p) => p.scope)))
      } catch {
        // Fall back to integration.permissions already in state.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [integration.status])

  useEffect(() => {
    onSelectionChange?.([...selected])
  }, [selected, onSelectionChange])

  const dirty = useMemo(() => {
    const active = new Set(rows.filter((p) => p.is_active).map((p) => p.scope))
    if (active.size !== selected.size) return true
    for (const s of selected) {
      if (!active.has(s)) return true
    }
    return false
  }, [rows, selected])

  const toggle = (scope: string) => {
    if (!canEdit || busy) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(scope)) next.delete(scope)
      else next.add(scope)
      return next
    })
    setError(null)
    setInfo(null)
  }

  const onSave = async () => {
    if (!isConnected) return
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const result = await msgraphUpdatePermissions([...selected])
      onUpdated(result.integration)
      if (result.consent_required && result.redirect_url) {
        setInfo('Redirecting to Microsoft to consent to new permissions…')
        window.location.assign(result.redirect_url)
        return
      }
      setRows(result.integration.permissions)
      setSelected(initialSelected(result.integration.permissions))
      setInfo('Permissions updated.')
    } catch (err) {
      setError(errorMessage(err, 'Could not update permissions.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="permission-selector">
      <p className="permission-selector-hint">
        {isConnected
          ? 'New permissions require Microsoft consent. Turning a permission off only disables it here (no Microsoft revoke).'
          : 'Choose permissions to request when you connect.'}
      </p>
      <ul className="permission-selector-list">
        {rows.map((perm) => {
          const checked = selected.has(perm.scope)
          return (
            <li key={perm.scope}>
              <label className="permission-selector-item">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!canEdit || busy}
                  onChange={() => toggle(perm.scope)}
                />
                <span className="permission-selector-label">{perm.label}</span>
                <span className={checked ? 'perm-on' : 'perm-off'}>
                  {checked ? 'On' : 'Off'}
                </span>
              </label>
            </li>
          )
        })}
      </ul>
      {isConnected && (
        <button
          type="button"
          className="btn-primary"
          disabled={!canEdit || busy || !dirty}
          onClick={() => void onSave()}
        >
          {busy ? 'Saving…' : 'Save permissions'}
        </button>
      )}
      {info && <p className="permission-selector-info">{info}</p>}
      {error && <p className="plaid-connect-error">{error}</p>}
    </div>
  )
}
