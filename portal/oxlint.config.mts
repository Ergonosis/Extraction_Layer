import { defineConfig } from 'oxlint'
import configSchema from './node_modules/oxlint/configuration_schema.json' with { type: 'json' }

export default defineConfig({
  plugins: [
    'react', // requires 'oxc-transform-react' package
    'typescript',
    'oxc',
  ],
  options: {
    typeAware: true, // requires 'oxlint-tsgolint' package
    typeCheck: true, // requires 'oxlint-tsgolint' package
  },
  rules: {
    eqeqeq: ['error', 'smart'],
    'react/rules-of-hooks': 'error',
    // Existing connect/auth effects sync props or kick off async refresh on mount.
    'react/set-state-in-effect': 'off',
    'react/only-export-components': ['warn', { allowConstantExport: true }],
    'typescript/only-throw-error': 'error',
    'unicorn/no-array-for-each': 'error',
    ...Object.keys(configSchema.definitions.DummyRuleMap.properties)
      .filter(
        rule =>
          rule.includes('/prefer-')
          && !rule.includes('prefer-readonly-parameter-types'),
      )
      .reduce((rules, rule) => Object.assign(rules, { [rule]: 'warn' }), {}),
  },
  categories: { correctness: 'error', perf: 'warn' },
})
