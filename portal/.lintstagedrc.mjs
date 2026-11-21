import { bunFmtSupportedExts, jsExts } from '../.lintstagedrc.mjs'

export default {
  [`**/*.{${bunFmtSupportedExts.filter(x => !jsExts.includes(x)).join(',')}}`]: 'bun fmt',
  [`**/*.{${jsExts.join(',')}}`]: [
    // () => `${getNpxCmd().split(' ', 1)[0]} run build`,
    // () => `git add -- ${join(__dirname, 'dist')}`,
    'bash -c \'bun run lint:fix --quiet "$@" || true\' --', // Auto-fix may generate unformatted code
    'bun fmt',
    'bun run lint:fix --quiet',
  ],
  // [`**/*.{${jsExts.join(',')}}`]: 'bun test'
}
