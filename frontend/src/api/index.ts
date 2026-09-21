import axios from 'axios'

/** 统一 axios 实例：所有模块经此调用后端（PRD §20.1 api/）。 */
const api = axios.create({ baseURL: '/api', timeout: 15000 })

api.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    // 后端统一错误包络 { success, error_code, message, resource }（PRD §28）
    const message: string = error.response?.data?.message ?? error.message ?? '请求失败'
    return Promise.reject(new Error(message))
  },
)

export default api
