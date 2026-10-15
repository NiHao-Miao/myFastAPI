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
  // OpenAI API地址（实测有效：www.autodl.art/api/v1/chat/completions）
  apiEndpoint: 'https://www.autodl.art/api/v1/chat/completions',
  
  // API Key (由开发人员指定)
  apiKey: 'XXXXXXXXX',
  
  // 使用的模型
  model: 'DeepSeek-V4.1-Flash'
}
