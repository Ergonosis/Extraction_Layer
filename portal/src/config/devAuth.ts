/**
 * LOCAL ONLY UI auth bypass.
 * Set VITE_DEV_BYPASS_AUTH=true in portal/.env.local — NEVER in production builds.
 */
export const DEV_UI_BYPASS_AUTH =
  import.meta.env.VITE_DEV_BYPASS_AUTH === 'true' ||
  import.meta.env.VITE_DEV_BYPASS_AUTH === '1'

export const DEV_MOCK_USER = {
  id: -1,
  email: 'dev-bypass@localhost',
  display_name: 'UI Bypass User',
  created_at: null,
  organization: {
    id: -1,
    name: 'UI Bypass Org',
    ms_tenant_id: 'ui-bypass',
  },
} as const

if (DEV_UI_BYPASS_AUTH) {
  // eslint-disable-next-line no-console
  console.warn(
    '[SECURITY] VITE_DEV_BYPASS_AUTH is enabled — AuthGuard is bypassed. ' +
      'NEVER ship a production build with this flag.',
  )
}
