import { api } from './client'

export type IntegrationPermission = {
  scope: string
  label: string
  is_active: boolean
}

export type IntegrationStatus =
  | 'not_connected'
  | 'connecting'
  | 'connected'
  | 'reauth_required'
  | 'error'

export type Integration = {
  provider: 'plaid' | 'msgraph' | string
  label: string
  status: IntegrationStatus | string
  connected_account: string | null
  connected_at: string | null
  updated_at: string | null
  permissions: IntegrationPermission[]
}

export async function fetchIntegrations(): Promise<Integration[]> {
  const { data } = await api.get<{ integrations: Integration[] }>('/api/integrations/')
  return data.integrations
}
