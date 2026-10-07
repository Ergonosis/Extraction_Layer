import { api, clearCsrfToken } from './client'

export type Organization = {
  id: number
  name: string
  ms_tenant_id: string
}

export type AuthUser = {
  id: number
  email: string
  display_name: string
  created_at: string | null
  organization: Organization
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  try {
    const { data } = await api.get<AuthUser>('/api/auth/me')
    return data
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 401) return null
    throw err
  }
}

export async function logout(): Promise<void> {
  await api.post('/api/auth/logout')
  clearCsrfToken()
}

/** Full-page redirect into the Flask → Microsoft SSO flow. */
export function startMicrosoftLogin(redirectPath = '/connections'): void {
  const params = new URLSearchParams({ redirect: redirectPath })
  window.location.assign(`/api/auth/login?${params.toString()}`)
}
