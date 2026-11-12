import { type SubmitEvent, useState } from 'react'

const inputClassName = 'w-full min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2.5'

type UploadResult = { status: 'ok'; uri: string; row_count: number; trigger_started: boolean }

export function FileUploadPage() {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [triggerRequested, setTriggerRequested] = useState(false)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (uploading) return

    const form = new FormData(event.currentTarget)
    const file = form.get('file')
    const tokenValue = form.get('token')
    const token = typeof tokenValue === 'string' ? tokenValue.trim() : ''
    setError(null)
    setResult(null)

    if (!(file instanceof File) || !file.name || file.size === 0) {
      setError('Choose a non-empty CSV file.')
      return
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Choose a file with the .csv extension.')
      return
    }
    if (!token) {
      setError('Enter the MCP server access token.')
      return
    }

    const trigger = form.get('trigger') === 'on'
    const url = new URL('/upload', __UNIFICATION_MCP_SERVER_URL__)
    const csvType = form.get('type')
    url.searchParams.set('type', typeof csvType === 'string' ? csvType : '')
    url.searchParams.set('trigger', String(trigger))
    const body = new FormData()
    body.append('file', file)
    setTriggerRequested(trigger)
    setUploading(true)

    try {
      const response = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : `Upload failed (HTTP ${response.status}).`)
      }
      if (
        data?.status !== 'ok'
        || typeof data.uri !== 'string'
        || typeof data.row_count !== 'number'
        || typeof data.trigger_started !== 'boolean'
      ) {
        throw new Error('The server returned an unexpected upload response.')
      }
      setResult(data)
    } catch (err) {
      setError(
        err instanceof TypeError ? 'Could not reach the upload server. Check the host and connection.'
        : err instanceof Error ? err.message
        : 'Upload failed. Try again.',
      )
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className='max-w-180'>
      <header>
        <h1 className='mb-2 text-[1.75rem] font-bold text-slate-900'>File Upload</h1>
        <p className='text-base text-slate-500'>Upload a CSV file to the data pipeline.</p>
      </header>

      <form className='mt-6 rounded-xl border border-slate-200 bg-white p-6' onSubmit={handleSubmit}>
        <fieldset
          className='grid min-w-0 gap-3 border-0 p-0 **:focus-visible:outline-2 **:focus-visible:outline-offset-2 **:focus-visible:outline-blue-600'
          disabled={uploading}
        >
          <label className='font-semibold' htmlFor='upload-type'>
            Data type
          </label>
          <select className={inputClassName} id='upload-type' name='type' defaultValue='crm'>
            <option value='crm'>CRM</option>
            <option value='bd-txn'>BD transactions</option>
            <option value='bd-accts'>BD accounts</option>
            <option value='bd-hold'>BD holdings</option>
          </select>

          <label className='font-semibold' htmlFor='upload-file'>
            CSV file
          </label>
          <input className={inputClassName} id='upload-file' name='file' type='file' accept='.csv,text/csv' required />

          <label className='font-semibold' htmlFor='upload-token'>
            MCP server Access token
          </label>
          <input
            className={inputClassName}
            id='upload-token'
            name='token'
            type='password'
            autoComplete='off'
            required
          />

          <label className='my-2 flex items-center gap-2 font-semibold'>
            <input name='trigger' type='checkbox' />
            Run pipeline after upload
          </label>

          <button
            className='cursor-pointer justify-self-start rounded-md bg-blue-600 px-5 py-2.5 font-semibold text-white disabled:cursor-wait disabled:opacity-60'
            type='submit'
          >
            {uploading ? 'Uploading…' : 'Upload CSV'}
          </button>
        </fieldset>
      </form>

      {error && (
        <p className='mt-4 text-red-700' role='alert'>
          {error}
        </p>
      )}
      {result && (
        <div className='mt-4 rounded-lg bg-emerald-50 p-4 wrap-anywhere text-emerald-800 [&_p]:mb-1' role='status'>
          <p>Uploaded {result.row_count.toLocaleString()} rows.</p>
          <p>{result.uri}</p>
          {triggerRequested && (
            <p>{result.trigger_started ? 'Pipeline started.' : 'File uploaded, but the pipeline did not start.'}</p>
          )}
        </div>
      )}
    </div>
  )
}
