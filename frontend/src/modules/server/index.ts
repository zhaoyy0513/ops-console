import { defineOpsModule } from '../registry'
import ServerView from './ServerView.vue'

export default defineOpsModule({
  id: 'server',
  title: 'Server',
  order: 2,
  icon: 'desktop-outline',
  routePath: 'server',
  view: ServerView,
})
