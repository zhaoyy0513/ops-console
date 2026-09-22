import axios from 'axios'

/** 统一 axios 实例：所有模块经此调用后端（PRD §20.1 api/）。 */
const instance = axios.create({ baseURL: '/api', timeout: 10000 })

instance.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    // 后端统一错误包络 { success, error_code, message, resource }（PRD §28）
    let message: string = error.response?.data?.message ?? error.message ?? '请求失败'
    if (error.code === 'ECONNABORTED') message = '请求超时'
    return Promise.reject(new Error(message))
  },
)

/** 拦截器已解包 resp.data，这里按真实返回类型收敛签名。 */
const api = instance as unknown as {
  get<T = unknown>(url: string): Promise<T>
  post<T = unknown>(url: string, data?: unknown): Promise<T>
  put<T = unknown>(url: string, data?: unknown): Promise<T>
  delete<T = unknown>(url: string): Promise<T>
}

export default api
