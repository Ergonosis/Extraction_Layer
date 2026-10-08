import { spawnSync } from 'child_process'

export let getNpxCmd = () => {
  const isWin = process.platform === 'win32'
  const NPX_CMD_LIST = ['bun x --bun', 'pnpm dlx', 'yarn dlx', 'npm x']
  let detectedCmd = ''

  for (const npxCmd of NPX_CMD_LIST) {
    try {
      let bin = npxCmd.split(' ', 1)[0]
      if (isWin && bin !== 'bun') {
        bin += '.cmd'
      }

      const result = spawnSync(bin, ['--version'], {
        encoding: 'utf-8',
        shell: true,
      })

      if (result.status === 0) {
        detectedCmd = npxCmd
        break
      }
    } catch {}
  }

  if (!detectedCmd) {
    detectedCmd = NPX_CMD_LIST[NPX_CMD_LIST.length - 1]
  }

  getNpxCmd = () => detectedCmd

  return detectedCmd
}

export default { '**/*.{*js*,*ts*,md,yaml}': `${getNpxCmd()} prettier --write` }
