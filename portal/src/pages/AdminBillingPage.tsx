import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'

import {
  type AdminDispute,
  type AdminOrgDetail,
  type AdminOrgListItem,
  fetchAdminBillingOrg,
  fetchAdminBillingOrgs,
  fetchAdminDisputes,
  refundAdminBillingOrg,
  resumeAdminBillingOrg,
  saveAdminBillingOrg,
} from '../api/adminBilling'
import { userFacingApiError } from '../api/errors'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import './AdminBillingPage.css'

type FormState = {
  flat_enabled: boolean
  exports_enabled: boolean
  api_calls_enabled: boolean
  included_exports: number
  included_api_calls: number
  terms_markdown: string
  stripe_flat_price_id: string
  stripe_exports_price_id: string
  stripe_api_calls_price_id: string
}

const emptyForm = (): FormState => ({
  flat_enabled: false,
  exports_enabled: false,
  api_calls_enabled: false,
  included_exports: 0,
  included_api_calls: 0,
  terms_markdown: '',
  stripe_flat_price_id: '',
  stripe_exports_price_id: '',
  stripe_api_calls_price_id: '',
})

function formFromDetail(detail: AdminOrgDetail): FormState {
  const b = detail.billing
  if (!b) return emptyForm()
  return {
    flat_enabled: b.flat_enabled,
    exports_enabled: b.exports_enabled,
    api_calls_enabled: b.api_calls_enabled,
    included_exports: b.included_exports,
    included_api_calls: b.included_api_calls,
    terms_markdown: b.terms_markdown ?? '',
    stripe_flat_price_id: b.stripe_flat_price_id ?? '',
    stripe_exports_price_id: b.stripe_exports_price_id ?? '',
    stripe_api_calls_price_id: b.stripe_api_calls_price_id ?? '',
  }
}

export function AdminBillingPage() {
  const { user } = useAuth()
  const { pushToast } = useToast()
  const [orgs, setOrgs] = useState<AdminOrgListItem[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AdminOrgDetail | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [disputes, setDisputes] = useState<AdminDispute[]>([])
  const [hasOpenDispute, setHasOpenDispute] = useState(false)
  const [disputesMock, setDisputesMock] = useState(true)
  const [refundInvoiceId, setRefundInvoiceId] = useState('')

  const loadOrgs = useCallback(async () => {
    try {
      const rows = await fetchAdminBillingOrgs()
      setOrgs(rows)
      setError(null)
    } catch (err) {
      setError(userFacingApiError(err, 'Could not load organizations.'))
    } finally {
      setLoadingList(false)
    }
  }, [])

  useEffect(() => {
    if (!user?.is_platform_admin) return
    let cancelled = false
    void (async () => {
      try {
        const rows = await fetchAdminBillingOrgs()
        if (cancelled) return
        setOrgs(rows)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setError(userFacingApiError(err, 'Could not load organizations.'))
      } finally {
        if (!cancelled) setLoadingList(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user?.is_platform_admin])

  const selectOrg = async (organizationId: number) => {
    setSelectedId(organizationId)
    setLoadingDetail(true)
    setDisputes([])
    try {
      const [next, disputePayload] = await Promise.all([
        fetchAdminBillingOrg(organizationId),
        fetchAdminDisputes(organizationId).catch(() => null),
      ])
      setDetail(next)
      setForm(formFromDetail(next))
      if (disputePayload) {
        setDisputes(disputePayload.disputes ?? [])
        setHasOpenDispute(Boolean(disputePayload.has_open_dispute))
        setDisputesMock(Boolean(disputePayload.mock))
      }
      setError(null)
    } catch (err) {
      setError(userFacingApiError(err, 'Could not load organization billing.'))
    } finally {
      setLoadingDetail(false)
    }
  }

  const formatDisputeMoney = (amount?: number | null, currency?: string | null) => {
    if (amount == null) return '—'
    const cur = (currency || 'usd').toUpperCase()
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur }).format(amount / 100)
    } catch {
      return `${(amount / 100).toFixed(2)} ${cur}`
    }
  }

  const formatUnix = (ts?: number | null) => {
    if (ts == null) return '—'
    return new Date(ts * 1000).toLocaleString()
  }

  const onSave = async () => {
    if (selectedId == null) return
    setBusy(true)
    try {
      const next = await saveAdminBillingOrg(selectedId, {
        flat_enabled: form.flat_enabled,
        exports_enabled: form.exports_enabled,
        api_calls_enabled: form.api_calls_enabled,
        included_exports: form.included_exports,
        included_api_calls: form.included_api_calls,
        terms_markdown: form.terms_markdown || null,
        stripe_flat_price_id: form.stripe_flat_price_id || null,
        stripe_exports_price_id: form.stripe_exports_price_id || null,
        stripe_api_calls_price_id: form.stripe_api_calls_price_id || null,
      })
      setDetail(next)
      setForm(formFromDetail(next))
      await loadOrgs()
      pushToast({ kind: 'success', message: 'Billing plan saved.' })
    } catch (err) {
      pushToast({ kind: 'error', message: userFacingApiError(err, 'Could not save billing plan.') })
    } finally {
      setBusy(false)
    }
  }

  const onResume = async () => {
    if (selectedId == null) return
    setBusy(true)
    try {
      const next = await resumeAdminBillingOrg(selectedId)
      setDetail(next)
      await loadOrgs()
      pushToast({ kind: 'success', message: 'Organization entitlement resumed.' })
    } catch (err) {
      pushToast({ kind: 'error', message: userFacingApiError(err, 'Could not resume organization.') })
    } finally {
      setBusy(false)
    }
  }

  const onRefund = async () => {
    if (selectedId == null) return
    const invoiceId = refundInvoiceId.trim()
    if (!invoiceId) {
      pushToast({ kind: 'error', message: 'Enter a Stripe invoice id to refund.' })
      return
    }
    setBusy(true)
    try {
      const result = await refundAdminBillingOrg(selectedId, invoiceId)
      pushToast({
        kind: 'info',
        message: result.mock ? 'Mock refund recorded (no Stripe charge refunded).' : 'Refund submitted.',
      })
    } catch (err) {
      pushToast({ kind: 'error', message: userFacingApiError(err, 'Could not refund.') })
    } finally {
      setBusy(false)
    }
  }

  if (!user?.is_platform_admin) {
    return <Navigate to='/connections' replace />
  }

  return (
    <div className='admin-billing-page'>
      <header className='admin-billing-header'>
        <h1>Admin Billing</h1>
        <p>Configure customer plans. Cards and tax stay in Stripe (mocked until connected).</p>
      </header>

      {error ?
        <p className='admin-billing-error'>{error}</p>
      : null}

      <div className='admin-billing-layout'>
        <section className='admin-billing-list' aria-label='Organizations'>
          <h2>Organizations</h2>
          {loadingList ?
            <p className='admin-billing-muted'>Loading…</p>
          : null}
          {!loadingList && orgs.length === 0 ?
            <p className='admin-billing-muted'>No organizations yet.</p>
          : null}
          <ul>
            {orgs.map(org => (
              <li key={org.organization_id}>
                <button
                  type='button'
                  className={
                    selectedId === org.organization_id ? 'admin-org-btn admin-org-btn-active' : 'admin-org-btn'
                  }
                  onClick={() => void selectOrg(org.organization_id)}
                >
                  <span className='admin-org-name'>{org.name}</span>
                  <span className='admin-org-meta'>
                    {org.billing_status} · {org.entitlement}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className='admin-billing-detail' aria-label='Plan editor'>
          {!selectedId ?
            <p className='admin-billing-muted'>Select an organization to edit billing.</p>
          : null}
          {loadingDetail ?
            <p className='admin-billing-muted'>Loading plan…</p>
          : null}
          {selectedId && detail && !loadingDetail ?
            <>
              <h2>{detail.name}</h2>
              <p className='admin-billing-muted'>
                Status: {detail.billing?.status ?? 'setup_required'} · Entitlement:{' '}
                {detail.billing?.entitlement ?? 'enabled'} · Usage: {detail.usage.exports} exports /{' '}
                {detail.usage.api_calls} API calls
              </p>

              <fieldset className='admin-billing-fieldset' disabled={busy}>
                <legend>Meters</legend>
                <label className='admin-check'>
                  <input
                    type='checkbox'
                    checked={form.flat_enabled}
                    onChange={e => setForm(f => ({ ...f, flat_enabled: e.target.checked }))}
                  />
                  Flat monthly
                </label>
                <label className='admin-check'>
                  <input
                    type='checkbox'
                    checked={form.exports_enabled}
                    onChange={e => setForm(f => ({ ...f, exports_enabled: e.target.checked }))}
                  />
                  Bill successful exports
                </label>
                <label className='admin-check'>
                  <input
                    type='checkbox'
                    checked={form.api_calls_enabled}
                    onChange={e => setForm(f => ({ ...f, api_calls_enabled: e.target.checked }))}
                  />
                  Bill API calls
                </label>
              </fieldset>

              <div className='admin-billing-grid'>
                <label>
                  Included exports
                  <input
                    type='number'
                    min={0}
                    value={form.included_exports}
                    onChange={e => setForm(f => ({ ...f, included_exports: Number(e.target.value) || 0 }))}
                  />
                </label>
                <label>
                  Included API calls
                  <input
                    type='number'
                    min={0}
                    value={form.included_api_calls}
                    onChange={e => setForm(f => ({ ...f, included_api_calls: Number(e.target.value) || 0 }))}
                  />
                </label>
              </div>

              <label className='admin-billing-block'>
                Stripe flat price id (optional)
                <input
                  type='text'
                  value={form.stripe_flat_price_id}
                  onChange={e => setForm(f => ({ ...f, stripe_flat_price_id: e.target.value }))}
                  placeholder='price_…'
                />
              </label>
              <label className='admin-billing-block'>
                Stripe exports price id (optional)
                <input
                  type='text'
                  value={form.stripe_exports_price_id}
                  onChange={e => setForm(f => ({ ...f, stripe_exports_price_id: e.target.value }))}
                  placeholder='price_…'
                />
              </label>
              <label className='admin-billing-block'>
                Stripe API calls price id (optional)
                <input
                  type='text'
                  value={form.stripe_api_calls_price_id}
                  onChange={e => setForm(f => ({ ...f, stripe_api_calls_price_id: e.target.value }))}
                  placeholder='price_…'
                />
              </label>

              <label className='admin-billing-block'>
                Terms (shown on customer Billing page)
                <textarea
                  rows={6}
                  value={form.terms_markdown}
                  onChange={e => setForm(f => ({ ...f, terms_markdown: e.target.value }))}
                  placeholder='Monthly platform fee + usage…'
                />
              </label>

              <div className='admin-disputes'>
                <h3>Disputes</h3>
                <p className='admin-billing-muted'>
                  Local flag: {hasOpenDispute ? 'open dispute on file' : 'no open dispute flag'}
                  {disputesMock ? ' · Mock mode (no live disputes)' : ''}
                </p>
                {disputes.length === 0 ?
                  <p className='admin-billing-muted'>No Stripe disputes returned for this customer.</p>
                : <ul className='admin-dispute-list'>
                    {disputes.map(d => (
                      <li key={d.id}>
                        <div className='admin-dispute-row'>
                          <strong>{d.status || 'unknown'}</strong>
                          <span>{formatDisputeMoney(d.amount, d.currency)}</span>
                          <span>{d.reason || '—'}</span>
                          <span>Opened {formatUnix(d.created)}</span>
                          {d.evidence_due_by ?
                            <span>Evidence due {formatUnix(d.evidence_due_by)}</span>
                          : null}
                          {d.dashboard_url ?
                            <a href={d.dashboard_url} target='_blank' rel='noreferrer'>
                              Open in Stripe
                            </a>
                          : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                }
              </div>

              <div className='admin-billing-actions'>
                <button type='button' className='admin-btn' disabled={busy} onClick={() => void onSave()}>
                  Save plan
                </button>
                <button
                  type='button'
                  className='admin-btn admin-btn-secondary'
                  disabled={busy}
                  onClick={() => void onResume()}
                >
                  Resume access
                </button>
                <label className='admin-refund-field'>
                  Invoice id
                  <input
                    type='text'
                    value={refundInvoiceId}
                    placeholder='in_…'
                    disabled={busy}
                    onChange={e => setRefundInvoiceId(e.target.value)}
                  />
                </label>
                <button
                  type='button'
                  className='admin-btn admin-btn-secondary'
                  disabled={busy}
                  onClick={() => void onRefund()}
                >
                  Record mock refund
                </button>
              </div>
            </>
          : null}
        </section>
      </div>
    </div>
  )
}
