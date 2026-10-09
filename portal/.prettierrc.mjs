import parentConfig from '../.prettierrc.mjs'

export default {
  ...parentConfig,
  plugins: [
    ...(parentConfig.plugins ?? []),
    'prettier-plugin-organize-imports',
    'prettier-plugin-tailwindcss',
  ],
  tailwindAttributes: ['/cls$/i', 'clsName'],
  tailwindFunctions: ['/twMerge/i', '/clsx?/', 'cva', 'cn'],
}
