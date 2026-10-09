import { useEffect, useMemo, useState } from 'react'
import { userFacingApiError } from '../api/errors'
import {
  msgraphPermissionsAvailable,
  msgraphUpdatePermissions,
} from '../api/msgraph'
import type { Integration, IntegrationPermission } from '../api/integrations'
import { useToast } from '../context/ToastContext'
import './PermissionSelector.css'

type Props = {
  integration: Integration
  onUpdated: (next: Integration) => void
  /** When not connected, selected scopes are used by Connect instead of PUT. */
  onSelectionChange?: (scopes: string[]) => void
}

function initialSelected(permissions: IntegrationPermission[]): Set<string> {
  return new Set(permissions.filter((p) => p.is_active).map((p) => p.scope))
}

export function PermissionSelector({
  integration,
  onUpdated,
  onSelectionChange,
}: Props) {
  const { pushToast } = useToast()
  const [rows, setRows] = useState<IntegrationPermission[]>(
    () => integration.permissions,
  )
  const [selected, setSelected] = useState<Set<string>>(() =>
    initialSelected(integration.permissions),
  )
  const [busy, setBusy] = useState(false)
  const [loadingAvailable, setLoadingAvailable] = useState(false)

  const isConnected = integration.status === 'connected'
  const isConnecting = integration.status === 'connecting'
  const canEdit = !isConnecting

  useEffect(() => {
    setRows(integration.permissions)
    setSelected(initialSelected(integration.permissions))
  }, [integration.permissions, integration.status, integration.updated_at])

  useEffect(() => {
    let cancelled = false
    setLoadingAvailable(true)
    void (async () => {
      try {
        const data = await msgraphPermissionsAvailable()
        if (cancelled) return
        setRows(data.permissions)
        setSelected(new Set(data.permissions.filter((p) => p.is_active).map((p) => p.scope)))
      } catch {
        // Fall back to integration.permissions already in state.
      } finally {
        if (!cancelled) setLoadingAvailable(false)
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
  }

  const onSave = async () => {
    if (!isConnected) return
    setBusy(true)
    try {
      const result = await msgraphUpdatePermissions([...selected])
      onUpdated(result.integration)
      if (result.consent_required && result.redirect_url) {
        pushToast({
          kind: 'info',
          message: 'Redirecting to Microsoft to consent to new permissions…',
        })
        window.location.assign(result.redirect_url)
        return
      }
      setRows(result.integration.permissions)
      setSelected(initialSelected(result.integration.permissions))
      pushToast({ kind: 'success', message: 'Permissions updated.' })
    } catch (err) {
      pushToast({
        kind: 'error',
        message: userFacingApiError(err, 'Could not update permissions.'),
      })
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
      {loadingAvailable && (
        <p className="permission-selector-info" role="status">
          Loading permissions…
        </p>
      )}
      <ul className="permission-selector-list">
        {rows.map((perm) => {
          const checked = selected.has(perm.scope)
          return (
            <li key={perm.scope}>
              <label className="permission-selector-item">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!canEdit || busy || loadingAvailable}
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
          disabled={!canEdit || busy || !dirty || loadingAvailable}
          onClick={() => void onSave()}
        >
          {busy ? 'Saving…' : 'Save permissions'}
        </button>
      )}
    </div>
  )
}
