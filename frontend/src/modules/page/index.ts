import { defineOpsModule } from '../registry'
import PageView from './PageView.vue'

export default defineOpsModule({
  id: 'page',
  title: 'Page',
  order: 3,
  icon: 'document-text-outline',
  routePath: 'page',
  view: PageView,
})
