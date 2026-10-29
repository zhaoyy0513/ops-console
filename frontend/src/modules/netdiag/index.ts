import { defineOpsModule } from '../registry'
import NetdiagView from './NetdiagView.vue'

export default defineOpsModule({
  id: 'netdiag',
  title: 'Netdiag',
  order: 10,
  icon: 'git-network-outline',
  routePath: 'netdiag',
  view: NetdiagView,
})
