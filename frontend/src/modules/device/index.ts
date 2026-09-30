import { defineOpsModule } from '../registry'
import DeviceView from './DeviceView.vue'

export default defineOpsModule({
  id: 'device',
  title: 'Device',
  order: 4,
  icon: 'walk-outline',
  routePath: 'device',
  view: DeviceView,
})
