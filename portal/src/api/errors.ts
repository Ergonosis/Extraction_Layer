import { isAxiosError } from 'axios'

/** Short, user-safe copy for common API failure statuses. Never expose stack traces. */
const STATUS_MESSAGES: Record<number, string> = {
  400: 'That request was invalid. Check your input and try again.',
  401: 'Your session expired. Sign in again to continue.',
  403: 'You do not have permission to do that.',
  404: 'That action is not available. Refresh the page or restart the API.',
  429: 'Too many requests. Wait a moment and try again.',
  500: 'Something went wrong on the server. Try again later.',
  502: 'The service is temporarily unavailable. Try again later.',
  503: 'This integration is not configured or temporarily unavailable.',
}

function isSafeApiMessage(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > 160) return false
  if (/traceback|exception|stack|sqlalchemy|psycopg|fernet|secret|token=/i.test(trimmed)) {
    return false
  }
  return true
}

/**
 * Map Axios / network failures to user-facing copy.
 * Prefer fixed status messages; allow short API `error` strings for 400 only.
 */
export function userFacingApiError(err: unknown, fallback: string): string {
  if (!isAxiosError(err)) return fallback

  if (!err.response) {
    return 'Could not reach the API. Is the server running?'
  }

  const status = err.response.status
  const apiError = (err.response.data as { error?: unknown } | undefined)?.error

  if (status === 400 && isSafeApiMessage(apiError)) {
    return apiError
  }

  return STATUS_MESSAGES[status] ?? fallback
}
