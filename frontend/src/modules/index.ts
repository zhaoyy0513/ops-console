// ★ 模块注册入口（PRD §20.4）：新增模块 = 下面加一行 import
import './overview'
import './server'
import './redis'
import './mq'
import './robot'
import './ssh'
import './database'

export { getModules } from './registry'
