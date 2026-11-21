import { api } from './client'

export type AdminOrgListItem = {
  organization_id: number
  name: string
  ms_tenant_id: string
  billing_status: string
  entitlement: string
}

export type AdminOrgDetail = {
  organization_id: number
  name: string
  ms_tenant_id: string
  billing: {
    organization_id: number
    status: string
    entitlement: string
    flat_enabled: boolean
    exports_enabled: boolean
    api_calls_enabled: boolean
    included_exports: number
    included_api_calls: number
    terms_markdown: string | null
    stripe_flat_price_id?: string | null
    stripe_exports_price_id?: string | null
    stripe_api_calls_price_id?: string | null
  } | null
  usage: { exports: number; api_calls: number }
}

export type AdminPlanPayload = {
  flat_enabled?: boolean
  exports_enabled?: boolean
  api_calls_enabled?: boolean
  included_exports?: number
  included_api_calls?: number
  terms_markdown?: string | null
  stripe_flat_price_id?: string | null
  stripe_exports_price_id?: string | null
  stripe_api_calls_price_id?: string | null
}

export async function fetchAdminBillingOrgs(): Promise<AdminOrgListItem[]> {
  const { data } = await api.get<{ organizations: AdminOrgListItem[] }>('/api/admin/billing/orgs')
  return data.organizations ?? []
}

export async function fetchAdminBillingOrg(organizationId: number): Promise<AdminOrgDetail> {
  const { data } = await api.get<AdminOrgDetail>(`/api/admin/billing/orgs/${organizationId}`)
  return data
}

export async function saveAdminBillingOrg(organizationId: number, payload: AdminPlanPayload): Promise<AdminOrgDetail> {
  const { data } = await api.post<AdminOrgDetail>(`/api/admin/billing/orgs/${organizationId}`, payload)
  return data
}

export async function resumeAdminBillingOrg(organizationId: number): Promise<AdminOrgDetail> {
  const { data } = await api.post<AdminOrgDetail>(`/api/admin/billing/orgs/${organizationId}/resume`)
  return data
}

export async function refundAdminBillingOrg(
  organizationId: number,
  invoiceId?: string,
): Promise<{ ok: boolean; mock?: boolean }> {
  const { data } = await api.post<{ ok: boolean; mock?: boolean }>(`/api/admin/billing/orgs/${organizationId}/refund`, {
    invoice_id: invoiceId ?? null,
  })
  return data
}

export type AdminDispute = {
  id: string
  amount?: number | null
  currency?: string | null
  reason?: string | null
  status?: string | null
  created?: number | null
  evidence_due_by?: number | null
  charge_id?: string | null
  dashboard_url?: string | null
}

export type AdminDisputesResponse = {
  organization_id: number
  has_open_dispute: boolean
  dispute_opened_at?: string | null
  disputes: AdminDispute[]
  mock?: boolean
}

export async function fetchAdminDisputes(organizationId: number): Promise<AdminDisputesResponse> {
  const { data } = await api.get<AdminDisputesResponse>(`/api/admin/billing/orgs/${organizationId}/disputes`)
  return data
}
