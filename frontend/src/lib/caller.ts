import { ref } from 'vue'

/** 操作人别名（无用户管理下的轻量身份）：localStorage 持久化，
 *  axios 拦截器统一随 X-Ops-User 头携带，后端 oplog 落库。
 *  MAC 地址跨路由不可见，别名 + IP 是内网溯源的可行组合。 */
const KEY = 'ops-user'

export const opsUser = ref(localStorage.getItem(KEY) ?? '')

export function setOpsUser(name: string) {
  opsUser.value = name.trim()
  if (opsUser.value) localStorage.setItem(KEY, opsUser.value)
  else localStorage.removeItem(KEY)
}
