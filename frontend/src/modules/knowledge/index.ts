import { defineOpsModule } from '../registry'
import KnowledgeView from './KnowledgeView.vue'

export default defineOpsModule({
  id: 'knowledge',
  title: 'Knowledge',
  order: 4,
  icon: 'document-text-outline',
  routePath: 'knowledge',
  view: KnowledgeView,
})
