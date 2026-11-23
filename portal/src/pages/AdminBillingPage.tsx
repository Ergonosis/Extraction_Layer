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
  flat_amount_usd: string
  exports_unit_amount_usd: string
  api_calls_unit_amount_usd: string
}

const emptyForm = (): FormState => ({
  flat_enabled: false,
  exports_enabled: false,
  api_calls_enabled: false,
  included_exports: 0,
  included_api_calls: 0,
  terms_markdown: '',
  flat_amount_usd: '',
  exports_unit_amount_usd: '',
  api_calls_unit_amount_usd: '',
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
    flat_amount_usd: b.flat_amount_usd ?? '',
    exports_unit_amount_usd: b.exports_unit_amount_usd ?? '',
    api_calls_unit_amount_usd: b.api_calls_unit_amount_usd ?? '',
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
        flat_amount_usd: form.flat_amount_usd || null,
        exports_unit_amount_usd: form.exports_unit_amount_usd || null,
        api_calls_unit_amount_usd: form.api_calls_unit_amount_usd || null,
      })
      setDetail(next)
      setForm(formFromDetail(next))
      await loadOrgs()
      const created =
        next.billing?.stripe_flat_price_id
        || next.billing?.stripe_exports_price_id
        || next.billing?.stripe_api_calls_price_id
      pushToast({
        kind: 'success',
        message: created ? 'Billing plan saved. Stripe prices created/updated.' : 'Billing plan saved.',
      })
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
        <p>
          Enter USD prices here, enable the meters that apply, then Save plan. We create matching Products/Prices in
          Stripe and keep the linked price ids for Checkout.
        </p>
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

              <fieldset className='admin-billing-fieldset' disabled={busy}>
                <legend>USD prices (creates Stripe Prices on save)</legend>
                <p className='admin-billing-muted'>
                  Type dollar amounts (e.g. 100 or 2.50). Saving creates Stripe catalog prices and stores the resulting{' '}
                  <code>price_…</code> ids automatically.
                </p>
                <label className='admin-billing-block'>
                  Flat / platform fee (USD per month)
                  <input
                    type='text'
                    inputMode='decimal'
                    value={form.flat_amount_usd}
                    onChange={e => setForm(f => ({ ...f, flat_amount_usd: e.target.value }))}
                    placeholder='100.00'
                  />
                  {detail.billing?.stripe_flat_price_id ?
                    <span className='admin-billing-muted'>
                      Linked Stripe price: {detail.billing.stripe_flat_price_id}
                    </span>
                  : null}
                </label>
                <label className='admin-billing-block'>
                  Exports (USD per export)
                  <input
                    type='text'
                    inputMode='decimal'
                    value={form.exports_unit_amount_usd}
                    onChange={e => setForm(f => ({ ...f, exports_unit_amount_usd: e.target.value }))}
                    placeholder='2.00'
                  />
                  {detail.billing?.stripe_exports_price_id ?
                    <span className='admin-billing-muted'>
                      Linked Stripe price: {detail.billing.stripe_exports_price_id}
                    </span>
                  : null}
                </label>
                <label className='admin-billing-block'>
                  API calls (USD per call)
                  <input
                    type='text'
                    inputMode='decimal'
                    value={form.api_calls_unit_amount_usd}
                    onChange={e => setForm(f => ({ ...f, api_calls_unit_amount_usd: e.target.value }))}
                    placeholder='0.01'
                  />
                  {detail.billing?.stripe_api_calls_price_id ?
                    <span className='admin-billing-muted'>
                      Linked Stripe price: {detail.billing.stripe_api_calls_price_id}
                    </span>
                  : null}
                </label>
              </fieldset>

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
