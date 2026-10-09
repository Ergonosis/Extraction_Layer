import { api } from './client'
import type { Integration } from './integrations'

export type PlaidConnectResponse = {
  link_token: string
  expiration?: string
  integration: Integration
}

export type PlaidIntegrationResponse = {
  integration: Integration
}

export async function plaidConnect(): Promise<PlaidConnectResponse> {
  const { data } = await api.post<PlaidConnectResponse>('/api/plaid/connect')
  return data
}

export async function plaidExchange(publicToken: string): Promise<PlaidIntegrationResponse> {
  const { data } = await api.post<PlaidIntegrationResponse>('/api/plaid/exchange', {
    public_token: publicToken,
  })
  return data
}

export async function plaidDisconnect(): Promise<PlaidIntegrationResponse> {
  const { data } = await api.post<PlaidIntegrationResponse>('/api/plaid/disconnect')
  return data
}

/** Abandon in-progress Link; clears stuck `connecting` without wiping credentials. */
export async function plaidCancel(): Promise<PlaidIntegrationResponse> {
  const { data } = await api.post<PlaidIntegrationResponse>('/api/plaid/cancel')
  return data
}

export async function plaidStatus(): Promise<PlaidIntegrationResponse> {
  const { data } = await api.get<PlaidIntegrationResponse>('/api/plaid/status')
  return data
}
