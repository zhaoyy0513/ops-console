// ★ 模块注册入口（PRD §20.4）：新增模块 = 下面加一行 import
import './demo'
import './server'
import './redis'
import './mq'
import './robot'

export { getModules } from './registry'
