import parentConfig from '../.prettierrc.mjs'

const plugins = (
  await Promise.all([
    import('@sroussey/prettier-plugin-organize-imports').catch(e =>
      console.error('❌ @sroussey/prettier-plugin-organize-imports\n', e),
    ),
    import('prettier-plugin-tailwindcss').catch(e =>
      console.error('❌ prettier-plugin-tailwindcss\n', e),
    ),
  ])
).filter(it => it)

export default {
  ...parentConfig,
  plugins: [...(parentConfig.plugins ?? []), ...plugins],
  tailwindAttributes: ['/cls$/i', 'clsName'],
  tailwindFunctions: ['/twMerge/i', '/clsx?/', 'cva', 'cn'],
}
