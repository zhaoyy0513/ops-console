import { defineOpsModule } from '../registry'
import SshView from './SshView.vue'

export default defineOpsModule({
  id: 'ssh',
  title: 'SSH',
  order: 7,
  icon: 'terminal-outline',
  routePath: 'ssh',
  view: SshView,
})
