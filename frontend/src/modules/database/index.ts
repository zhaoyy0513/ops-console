import { defineOpsModule } from '../registry'
import DatabaseView from './DatabaseView.vue'

export default defineOpsModule({
  id: 'database',
  title: 'Database',
  order: 8,
  icon: 'server-outline',
  routePath: 'database',
  view: DatabaseView,
})
