const handleJsFile = [
  // () => `${getNpxCmd().split(' ', 1)[0]} run build`,
  // () => `git add -- ${join(__dirname, 'dist')}`,
  'bash -c \'bun run lint:fix --quiet "$@" || true\' --', // Auto-fix may generate unformatted code
  'bun fmt',
  'bun run lint:fix --quiet',
]

export default { '**/*.{,[mc]}[jt]s': handleJsFile, '**/*.[jt]sx': handleJsFile }
