import { getNpxCmd } from './.lintstagedrc.mjs'

export default { 'pre-commit': `${getNpxCmd()} lint-staged -v` }
