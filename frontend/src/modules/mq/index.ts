import { defineOpsModule } from '../registry'
import MqView from './MqView.vue'

export default defineOpsModule({
  id: 'mq',
  title: 'ActiveMQ',
  order: 5,
  icon: 'swap-horizontal-outline',
  routePath: 'mq',
  view: MqView,
})
