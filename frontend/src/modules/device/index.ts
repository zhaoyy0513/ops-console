import { defineOpsModule } from '../registry'
import DeviceView from './DeviceView.vue'

export default defineOpsModule({
  id: 'device',
  title: 'Device',
  order: 6,
  icon: 'walk-outline',
  routePath: 'device',
  view: DeviceView,
})
