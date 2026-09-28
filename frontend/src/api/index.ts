import axios from 'axios'

/** 统一 axios 实例：所有模块经此调用后端（PRD §20.1 api/）。 */
const instance = axios.create({ baseURL: '/api', timeout: 10000 })

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
