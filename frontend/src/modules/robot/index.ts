import { defineOpsModule } from '../registry'
import RobotView from './RobotView.vue'

export default defineOpsModule({
  id: 'robot',
  title: 'Robot',
  order: 4,
  icon: 'walk-outline',
  routePath: 'robot',
  view: RobotView,
})
