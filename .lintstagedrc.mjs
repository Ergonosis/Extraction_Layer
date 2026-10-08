import { spawnSync } from 'child_process'

let npxCmdCache = ''
export function getNpxCmd() {
  if (npxCmdCache) return npxCmdCache
  const NPX_CMD_LIST = ['bun x --bun', 'pnpm dlx', 'yarn dlx', 'npm x']
  for (const npxCmd of NPX_CMD_LIST) {
    try {
      const result = spawnSync(npxCmd.split(' ', 1)[0], ['--version'], {
        encoding: 'utf-8',
        shell: true,
      })
      if (result.status === 0) {
        npxCmdCache = npxCmd
        break
      }
    } catch {
      npxCmdCache = NPX_CMD_LIST[NPX_CMD_LIST.length - 1]
    }
  }
  return npxCmdCache
}

export default { '**/*.{*js*,*ts*,md,yaml}': `${getNpxCmd()} prettier --write` }
