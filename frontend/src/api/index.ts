import axios from 'axios'

/** 统一 axios 实例：所有模块经此调用后端（PRD §20.1 api/）。 */
const instance = axios.create({ baseURL: '/api', timeout: 15000 })

// 操作人别名随所有请求携带（oplog 溯源用；别名在操作日志页设置，存 localStorage）
instance.interceptors.request.use((config) => {
  const user = localStorage.getItem('ops-user')
  if (user) config.headers['X-Ops-User'] = user
  return config
})

instance.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    // 后端错误：业务包络 {message} 或 HTTPException {detail}（PRD §28）
    let message: string = error.response?.data?.message
      ?? error.response?.data?.detail
      ?? error.message
      ?? '请求失败'
    if (typeof message !== 'string') message = JSON.stringify(message)
    if (error.code === 'ECONNABORTED') message = '请求超时'
    return Promise.reject(new Error(message))
  },
)

/** 拦截器已解包 resp.data，这里按真实返回类型收敛签名。 */
const api = instance as unknown as {
  get<T = unknown>(url: string, config?: { timeout?: number }): Promise<T>
  post<T = unknown>(url: string, data?: unknown, config?: { timeout?: number }): Promise<T>
  put<T = unknown>(url: string, data?: unknown, config?: { timeout?: number }): Promise<T>
  delete<T = unknown>(url: string): Promise<T>
}

export default api
