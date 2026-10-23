/**
 * API配置文件
 * 包含API基础URL和AI问答功能所需的API参数
 */

// API基础URL配置
export const apiConfig = {
  // 后端API基础URL
  baseURL: 'http://127.0.0.1:8000',
}

export const aiChatConfig = {
  // 后端 AI 问答 SSE 接口
  chatEndpoint: `${apiConfig.baseURL}/api/ai/chat`,

  // 后端 AI 历史提问接口
  historyEndpoint: `${apiConfig.baseURL}/api/ai/chat/history`
}
