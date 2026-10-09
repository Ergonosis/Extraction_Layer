import { api } from './client'
import type { Integration } from './integrations'

export type MsGraphConnectResponse = {
  authorize_url: string
  scopes: string[]
  integration: Integration
}

export type MsGraphIntegrationResponse = {
  integration: Integration
}

export async function msgraphConnect(
  scopes?: string[],
): Promise<MsGraphConnectResponse> {
  const { data } = await api.post<MsGraphConnectResponse>('/api/msgraph/connect', {
    scopes,
  })
  return data
}

export async function msgraphDisconnect(): Promise<MsGraphIntegrationResponse> {
  const { data } = await api.post<MsGraphIntegrationResponse>('/api/msgraph/disconnect')
  return data
}

export async function msgraphCancel(): Promise<MsGraphIntegrationResponse> {
  const { data } = await api.post<MsGraphIntegrationResponse>('/api/msgraph/cancel')
  return data
}

export async function msgraphStatus(): Promise<MsGraphIntegrationResponse> {
  const { data } = await api.get<MsGraphIntegrationResponse>('/api/msgraph/status')
  return data
}

export type MsGraphAvailablePermission = {
  scope: string
  label: string
  is_active: boolean
}

export type MsGraphAvailableResponse = {
  permissions: MsGraphAvailablePermission[]
  connected: boolean
}

export type MsGraphPermissionsUpdateResponse = {
  consent_required: boolean
  redirect_url?: string
  integration: Integration
}

export async function msgraphPermissionsAvailable(): Promise<MsGraphAvailableResponse> {
  const { data } = await api.get<MsGraphAvailableResponse>(
    '/api/msgraph/permissions/available',
  )
  return data
}

export async function msgraphUpdatePermissions(
  scopes: string[],
): Promise<MsGraphPermissionsUpdateResponse> {
  const { data } = await api.put<MsGraphPermissionsUpdateResponse>(
    '/api/msgraph/permissions',
    { scopes },
  )
  return data
}
