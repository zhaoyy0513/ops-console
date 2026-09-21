import { defineOpsModule } from '../registry'
import DemoView from './DemoView.vue'

export default defineOpsModule({
  id: 'demo',
  title: 'Demo',
  order: 99,
  icon: 'cube-outline',
  routePath: 'demo',
  view: DemoView,
})
