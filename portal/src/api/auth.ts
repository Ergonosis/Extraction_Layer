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

export async function fetchDevLoginStatus(): Promise<boolean> {
  try {
    const { data } = await api.get<{ dev_login_enabled?: boolean }>('/api/auth/dev-status')
    return Boolean(data.dev_login_enabled)
  } catch {
    return false
  }
}

/** LOCAL ONLY — requires ENABLE_DEV_LOGIN on the API. */
export async function devLogin(): Promise<AuthUser> {
  const { data } = await api.post<{ user: AuthUser; warning?: string }>('/api/auth/dev-login')
  if (data.warning) {
    // eslint-disable-next-line no-console
    console.warn(`[SECURITY] ${data.warning}`)
  }
  return data.user
}
