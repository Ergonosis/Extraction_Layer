import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'

const MUTATING = new Set(['post', 'put', 'delete', 'patch'])

type RetryConfig = InternalAxiosRequestConfig & { _csrfRetry?: boolean }

let csrfToken: string | null = null
let csrfPromise: Promise<string> | null = null

async function fetchCsrfToken(client: AxiosInstance): Promise<string> {
  const { data } = await client.get<{ csrf_token: string }>('/api/auth/csrf-token')
  csrfToken = data.csrf_token
  return csrfToken
}

export async function ensureCsrfToken(
  client: AxiosInstance = api,
  force = false,
): Promise<string> {
  if (!force && csrfToken) return csrfToken
  if (force) {
    csrfToken = null
  }
  if (!csrfPromise) {
    csrfPromise = fetchCsrfToken(client).finally(() => {
      csrfPromise = null
    })
  }
  return csrfPromise
}

export function clearCsrfToken(): void {
  csrfToken = null
}

export const api: AxiosInstance = axios.create({
  baseURL: '/',
  withCredentials: true,
  timeout: 8000,
  headers: { Accept: 'application/json' },
})

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const method = (config.method || 'get').toLowerCase()
  if (MUTATING.has(method)) {
    const token = await ensureCsrfToken(api)
    config.headers.set('X-CSRF-Token', token)
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ error?: string }>) => {
    const config = error.config as RetryConfig | undefined
    const isCsrf =
      error.response?.status === 403 &&
      (error.response.data?.error || '').toLowerCase().includes('csrf')

    if (isCsrf && config && !config._csrfRetry) {
      config._csrfRetry = true
      clearCsrfToken()
      const token = await ensureCsrfToken(api, true)
      config.headers = config.headers ?? {}
      config.headers.set?.('X-CSRF-Token', token)
      if (!config.headers.set) {
        ;(config.headers as Record<string, string>)['X-CSRF-Token'] = token
      }
      return api.request(config)
    }
    return Promise.reject(error)
  },
)
