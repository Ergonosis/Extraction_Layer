import { useCallback, useEffect, useState } from 'react'

import {
  type BillingInvoice,
  type BillingSummary,
  createBillingPortalSession,
  createBillingSetupSession,
  fetchBillingInvoices,
  fetchBillingSummary,
} from '../api/billing'
import { userFacingApiError } from '../api/errors'
import { useToast } from '../context/ToastContext'
import './BillingPage.css'

const STATUS_LABELS: Record<string, string> = {
  setup_required: 'Setup required',
  active: 'Active',
  past_due: 'Past due',
  suspended: 'Suspended',
  canceled: 'Canceled',
}

function planLabel(summary: BillingSummary): string {
  const parts: string[] = []
  if (summary.flat_enabled) parts.push('Flat monthly')
  if (summary.exports_enabled) parts.push('Exports')
  if (summary.api_calls_enabled) parts.push('API calls')
  return parts.length ? parts.join(' · ') : 'Not configured yet'
}

function statusBadgeClass(status: string): string {
  if (status === 'active') return 'billing-badge billing-badge-ok'
  if (status === 'past_due' || status === 'setup_required') return 'billing-badge billing-badge-warn'
  if (status === 'suspended' || status === 'canceled') return 'billing-badge billing-badge-danger'
  return 'billing-badge billing-badge-muted'
}

function daysLeft(suspendAfter: string | null | undefined): number | null {
  if (!suspendAfter) return null
  const end = new Date(suspendAfter).getTime()
  if (Number.isNaN(end)) return null
  return Math.max(0, Math.ceil((end - Date.now()) / (24 * 60 * 60 * 1000)))
}

/** Stripe amounts are minor units (cents). */
function formatMoney(amount: number | null | undefined, currency = 'usd'): string {
  if (amount == null || Number.isNaN(amount)) return '—'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency.toUpperCase() }).format(
      amount / 100,
    )
  } catch {
    return `${(amount / 100).toFixed(2)} ${currency}`
  }
}

function usageLine(used: number, enabled: boolean, included: number): { value: string; hint: string | null } {
  if (!enabled) return { value: String(used), hint: 'Not billed' }
  if (included > 0) return { value: `${used} / ${included}`, hint: 'included' }
  return { value: String(used), hint: null }
}

export function BillingPage() {
  const { pushToast } = useToast()
  const [summary, setSummary] = useState<BillingSummary | null>(null)
  const [invoices, setInvoices] = useState<BillingInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [nextSummary, nextInvoices] = await Promise.all([fetchBillingSummary(), fetchBillingInvoices()])
      setSummary(nextSummary)
      setInvoices(nextInvoices)
      setError(null)
    } catch (err) {
      setError(userFacingApiError(err, 'Could not load billing.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [nextSummary, nextInvoices] = await Promise.all([fetchBillingSummary(), fetchBillingInvoices()])
        if (cancelled) return
        setSummary(nextSummary)
        setInvoices(nextInvoices)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setError(userFacingApiError(err, 'Could not load billing.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const onSetupCard = async () => {
    setBusy(true)
    try {
      const { url, mock } = await createBillingSetupSession()
      if (mock) {
        pushToast({
          kind: 'info',
          message: 'Stripe Checkout is mocked until a Stripe account is connected. URL logged for now.',
        })
        console.info('Mock Checkout URL:', url)
        await load()
        return
      }
      window.location.assign(url)
    } catch (err) {
      pushToast({ kind: 'error', message: userFacingApiError(err, 'Could not start card setup.') })
    } finally {
      setBusy(false)
    }
  }

  const onManageCard = async () => {
    setBusy(true)
    try {
      const { url, mock } = await createBillingPortalSession()
      if (mock) {
        pushToast({ kind: 'info', message: 'Stripe Customer Portal is mocked until Stripe is connected.' })
        console.info('Mock Portal URL:', url)
        return
      }
      window.location.assign(url)
    } catch (err) {
      pushToast({ kind: 'error', message: userFacingApiError(err, 'Could not open billing portal.') })
    } finally {
      setBusy(false)
    }
  }

  if (loading && !summary) {
    return (
      <div className='billing-page'>
        <p className='billing-loading' role='status'>
          Loading billing…
        </p>
      </div>
    )
  }

  const graceDays = daysLeft(summary?.suspend_after)
  const showPastDue = summary?.status === 'past_due'
  const showSuspended = summary?.entitlement === 'suspended' || summary?.status === 'suspended'
  const statusText = summary ? STATUS_LABELS[summary.status] || summary.status : 'Unknown'
  const exportsUsage = usageLine(
    summary?.usage?.exports ?? 0,
    Boolean(summary?.exports_enabled),
    summary?.included_exports ?? 0,
  )
  const apiUsage = usageLine(
    summary?.usage?.api_calls ?? 0,
    Boolean(summary?.api_calls_enabled),
    summary?.included_api_calls ?? 0,
  )
  const currency = summary?.upcoming_invoice?.currency || 'usd'

  return (
    <div className='billing-page'>
      <header className='billing-header'>
        <h1>Billing</h1>
        <p>View your plan, usage, and invoices. Cards are handled by Stripe—never on this site.</p>
      </header>

      {error ?
        <p className='billing-error'>{error}</p>
      : null}

      {showPastDue ?
        <div className='billing-banner billing-banner-warn' role='status'>
          Payment failed. Update your card
          {graceDays != null ? ` within ${graceDays} day(s)` : ''} to keep full access.
        </div>
      : null}

      {showSuspended ?
        <div className='billing-banner billing-banner-danger' role='alert'>
          Access to paid features is suspended. Update your payment method or contact Ergonosis.
        </div>
      : null}

      {summary?.mock ?
        <div className='billing-banner billing-banner-mock' role='alert'>
          <p className='billing-banner-mock-title'>Stripe off — mock mode</p>
          <p className='billing-banner-mock-body'>
            Billing is running in mock mode. No real charges or tax will be applied.
          </p>
        </div>
      : null}

      {summary ?
        <div className='billing-grid'>
          <article className='billing-card'>
            <header className='billing-card-header'>
              <h2>Your plan</h2>
              <span className={statusBadgeClass(summary.status)}>{statusText}</span>
            </header>
            <div className='billing-card-body'>
              <dl className='billing-meta'>
                <div>
                  <dt>Meters</dt>
                  <dd>{planLabel(summary)}</dd>
                </div>
                <div>
                  <dt>Card on file</dt>
                  <dd>{summary.pm_last4 ? `${summary.pm_brand || 'Card'} ···· ${summary.pm_last4}` : 'None yet'}</dd>
                </div>
                <div>
                  <dt>Terms</dt>
                  <dd>
                    {summary.terms_markdown ?
                      <pre className='billing-terms-body'>{summary.terms_markdown}</pre>
                    : 'Your Ergonosis admin has not published terms yet.'}
                  </dd>
                </div>
              </dl>
            </div>
            <div className='billing-card-actions'>
              <button type='button' className='btn-primary' disabled={busy} onClick={() => void onSetupCard()}>
                Add or update card
              </button>
              <button
                type='button'
                className='btn-secondary'
                disabled={busy || !summary.stripe_customer_id}
                onClick={() => void onManageCard()}
              >
                Stripe customer portal
              </button>
            </div>
          </article>

          <article className='billing-card'>
            <header className='billing-card-header'>
              <h2>Usage this period</h2>
            </header>
            <div className='billing-card-body'>
              <ul className='billing-stat-list'>
                <li>
                  <div>
                    <span className='billing-stat-label'>Exports</span>
                    {exportsUsage.hint ?
                      <span className='billing-stat-hint'>{exportsUsage.hint}</span>
                    : null}
                  </div>
                  <strong className='billing-stat-value'>{exportsUsage.value}</strong>
                </li>
                <li>
                  <div>
                    <span className='billing-stat-label'>API calls</span>
                    {apiUsage.hint ?
                      <span className='billing-stat-hint'>{apiUsage.hint}</span>
                    : null}
                  </div>
                  <strong className='billing-stat-value'>{apiUsage.value}</strong>
                </li>
              </ul>
            </div>
          </article>

          <article className='billing-card'>
            <header className='billing-card-header'>
              <h2>Next invoice</h2>
            </header>
            <div className='billing-card-body'>
              {summary.upcoming_invoice?.note ?
                <p className='billing-muted'>{summary.upcoming_invoice.note}</p>
              : null}
              <dl className='billing-totals'>
                <div>
                  <dt>Subtotal</dt>
                  <dd>{formatMoney(summary.upcoming_invoice?.subtotal, currency)}</dd>
                </div>
                <div>
                  <dt>Tax</dt>
                  <dd>{formatMoney(summary.upcoming_invoice?.tax, currency)}</dd>
                </div>
                <div className='billing-total-row'>
                  <dt>Total</dt>
                  <dd>{formatMoney(summary.upcoming_invoice?.total, currency)}</dd>
                </div>
              </dl>
            </div>
          </article>

          <article className='billing-card'>
            <header className='billing-card-header'>
              <h2>Invoices</h2>
            </header>
            <div className='billing-card-body'>
              {invoices.length === 0 ?
                <p className='billing-muted'>No invoices yet.</p>
              : <ul className='billing-invoice-list'>
                  {invoices.map(inv => (
                    <li key={inv.id}>
                      <div className='billing-invoice-main'>
                        <span className='billing-invoice-id'>{inv.id}</span>
                        <span className='billing-badge billing-badge-muted'>{inv.status || 'unknown'}</span>
                      </div>
                      <div className='billing-invoice-side'>
                        <strong>{formatMoney(inv.total ?? null, inv.currency || currency)}</strong>
                        {inv.hosted_invoice_url ?
                          <a href={inv.hosted_invoice_url} target='_blank' rel='noreferrer'>
                            View
                          </a>
                        : null}
                      </div>
                    </li>
                  ))}
                </ul>
              }
            </div>
          </article>
        </div>
      : null}
    </div>
  )
}
