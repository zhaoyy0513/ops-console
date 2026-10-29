import { defineOpsModule } from '../registry'
import LogsView from './LogsView.vue'

export default defineOpsModule({
  id: 'logs',
  title: 'Logs',
  order: 11,
  icon: 'document-text-outline',
  routePath: 'logs',
  view: LogsView,
})
