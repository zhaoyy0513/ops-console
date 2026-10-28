import { defineOpsModule } from '../registry'
import DatabaseView from './DatabaseView.vue'

export default defineOpsModule({
  id: 'database',
  title: 'Database',
  order: 9,
  icon: 'server-outline',
  routePath: 'database',
  view: DatabaseView,
})
