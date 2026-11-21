import { api } from './client'

export type BillingSummary = {
  organization_id: number
  status: string
  entitlement: string
  flat_enabled: boolean
  exports_enabled: boolean
  api_calls_enabled: boolean
  included_exports: number
  included_api_calls: number
  terms_markdown: string | null
  past_due_since?: string | null
  suspend_after?: string | null
  has_open_dispute?: boolean
  pm_brand?: string | null
  pm_last4?: string | null
  stripe_customer_id?: string | null
  usage?: { exports: number; api_calls: number }
  upcoming_invoice?: {
    currency?: string
    subtotal?: number | null
    tax?: number | null
    total?: number | null
    lines?: Array<{ description?: string | null; amount?: number | null; quantity?: number | null }>
    note?: string | null
  } | null
  mock?: boolean
}

export type BillingInvoice = {
  id: string
  status?: string
  total?: number
  currency?: string
  hosted_invoice_url?: string | null
}

export async function fetchBillingSummary(): Promise<BillingSummary> {
  const { data } = await api.get<BillingSummary>('/api/billing/summary')
  return data
}

export async function fetchBillingInvoices(): Promise<BillingInvoice[]> {
  const { data } = await api.get<{ invoices: BillingInvoice[] }>('/api/billing/invoices')
  return data.invoices ?? []
}

export async function createBillingSetupSession(): Promise<{ url: string; mock?: boolean }> {
  const { data } = await api.post<{ url: string; mock?: boolean }>('/api/billing/setup-session')
  return data
}

export async function createBillingPortalSession(): Promise<{ url: string; mock?: boolean }> {
  const { data } = await api.post<{ url: string; mock?: boolean }>('/api/billing/portal-session')
  return data
}
