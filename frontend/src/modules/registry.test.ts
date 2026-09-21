import { describe, expect, it } from 'vitest'
import { defineOpsModule, getModules } from './registry'
import type { OpsModule } from './registry'

const view = { render: () => null } as unknown as OpsModule['view']

describe('module registry', () => {
  it('sorts registered modules by order', () => {
    defineOpsModule({ id: 'b', title: 'B', order: 2, icon: '', routePath: 'b', view })
    defineOpsModule({ id: 'a', title: 'A', order: 1, icon: '', routePath: 'a', view })
    expect(getModules().map((m) => m.id)).toEqual(['a', 'b'])
  })
})
