import { cva, type VariantProps } from 'class-variance-authority'

export { default as Badge } from './Badge.vue'

export const badgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap font-medium [&_svg]:size-3',
  {
    variants: {
      variant: {
        default: 'bg-primary/15 text-primary',
        secondary: 'bg-secondary text-secondary-foreground',
        outline: 'border border-border text-foreground',
        success: 'bg-[var(--ops-healthy)]/15 text-[var(--ops-healthy)]',
        warning: 'bg-[var(--ops-warning)]/15 text-[var(--ops-warning)]',
        critical: 'bg-[var(--ops-critical)]/15 text-[var(--ops-critical)]',
      },
      size: {
        default: 'rounded-md px-2 py-0.5 text-xs',
        sm: 'rounded px-1.5 py-0 text-[11px]',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export type BadgeVariants = VariantProps<typeof badgeVariants>
