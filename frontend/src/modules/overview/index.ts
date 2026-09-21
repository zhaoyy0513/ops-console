import { defineOpsModule } from '../registry'
import OverviewView from './OverviewView.vue'

export default defineOpsModule({
  id: 'overview',
  title: 'Overview',
  order: 1,
  icon: 'grid-outline',
  routePath: 'overview',
  view: OverviewView,
})
