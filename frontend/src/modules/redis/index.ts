import { defineOpsModule } from '../registry'
import RedisView from './RedisView.vue'

export default defineOpsModule({
  id: 'redis',
  title: 'Redis',
  order: 5,
  icon: 'server-outline',
  routePath: 'redis',
  view: RedisView,
})
