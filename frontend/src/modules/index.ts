// ★ 模块注册入口（PRD §20.4）：新增模块 = 下面加一行 import
import './overview'
import './server'
import './page'
import './knowledge'
import './redis'
import './mq'
import './device'
import './ssh'
import './database'
import './logs'
import './netdiag'

export { getModules } from './registry'
